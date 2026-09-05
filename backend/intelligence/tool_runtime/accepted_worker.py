"""Restart-safe worker for accepted Human Gate Named Actions.

The worker claims an accepted HumanTask, records a durable attempt, dispatches
through the explicit ``AcceptedNamedActionDispatcher`` and acknowledges the
claim only after the owning domain handler returns.  A crash between the
domain commit and the delivery acknowledgement is safe because the domain
command remains idempotent on ``request_id`` and the delivery ledger records
the replay state.  Permanent failures can be terminally marked in the same
ledger; transient failures leave the Human Gate lease to expire for takeover.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from backend.intelligence.human_gate import GateStatus, HumanTask, HumanTaskClaim
from backend.intelligence.human_gate.contracts import NamedActionRequest
from backend.intelligence.tool_runtime.accepted_delivery import (
    AcceptedActionDeliveryStatus,
    AcceptedActionDeliveryStore,
)
from backend.intelligence.tool_runtime.accepted_dispatch import (
    AcceptedActionDispatchError,
    AcceptedNamedActionDispatcher,
    ActionExecutionReceipt,
)
from backend.platform.audit import AuditRecorder


class AcceptedActionWorkerError(RuntimeError):
    """Base worker lifecycle error."""


class PermanentAcceptedActionError(AcceptedActionWorkerError):
    """A failure that must not be retried."""


class AcceptedActionWorkerStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RETRY = "retry"
    DEAD_LETTERED = "dead_lettered"


@dataclass(frozen=True, slots=True)
class AcceptedActionDeliveryResult:
    task_id: str
    request_id: str
    status: AcceptedActionWorkerStatus
    attempts: int
    receipt: ActionExecutionReceipt | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AcceptedActionWorkerReport:
    """Outcome of one bounded queue poll."""

    results: tuple[AcceptedActionDeliveryResult, ...]

    @property
    def pulled(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return sum(item.status is AcceptedActionWorkerStatus.SUCCEEDED for item in self.results)

    @property
    def retried(self) -> int:
        return sum(item.status is AcceptedActionWorkerStatus.RETRY for item in self.results)

    @property
    def dead_lettered(self) -> int:
        return sum(
            item.status is AcceptedActionWorkerStatus.DEAD_LETTERED for item in self.results
        )


@dataclass(frozen=True, slots=True)
class AcceptedActionSchedulerReport:
    """Summary of a bounded set of queue passes."""

    passes: tuple[AcceptedActionWorkerReport, ...]

    @property
    def pulled(self) -> int:
        return sum(item.pulled for item in self.passes)

    @property
    def succeeded(self) -> int:
        return sum(item.succeeded for item in self.passes)

    @property
    def retried(self) -> int:
        return sum(item.retried for item in self.passes)

    @property
    def dead_lettered(self) -> int:
        return sum(item.dead_lettered for item in self.passes)


class AcceptedActionGate(Protocol):
    async def get(self, task_id: str) -> HumanTask: ...

    async def claim_accepted(
        self,
        task_id: str,
        *,
        claim_owner: str,
        lease_ttl: timedelta,
        recorder: AuditRecorder,
        now: datetime | None = None,
    ) -> HumanTaskClaim: ...

    async def complete_claim(
        self,
        task_id: str,
        *,
        claim_owner: str,
        recorder: AuditRecorder,
        now: datetime | None = None,
    ) -> HumanTask: ...

    async def flush_audit(self, recorder: AuditRecorder) -> int: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class AcceptedActionQueue(Protocol):
    async def pending_accepted_task_ids(self, *, limit: int = 100) -> tuple[str, ...]: ...


class AcceptedNamedActionWorker:
    """One-shot, bounded worker; scheduling and queue polling stay external."""

    def __init__(
        self,
        gate: AcceptedActionGate,
        delivery: AcceptedActionDeliveryStore,
        dispatcher: AcceptedNamedActionDispatcher,
        *,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._gate = gate
        self._delivery = delivery
        self._dispatcher = dispatcher
        self._max_attempts = max_attempts

    async def consume(
        self,
        task_id: str,
        *,
        claim_owner: str,
        lease_ttl: timedelta = timedelta(minutes=5),
        claimed_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> AcceptedActionDeliveryResult:
        task = await self._gate.get(task_id)
        request = _accepted_request(task)

        previous = await self._delivery.get(request.request_id)
        if previous is not None and previous.status is AcceptedActionDeliveryStatus.DEAD_LETTERED:
            return AcceptedActionDeliveryResult(
                task_id=task_id,
                request_id=request.request_id,
                status=AcceptedActionWorkerStatus.DEAD_LETTERED,
                attempts=previous.attempts,
                error=previous.last_error,
            )

        try:
            claim_recorder = AuditRecorder()
            claimed = await self._gate.claim_accepted(
                task_id,
                claim_owner=claim_owner,
                lease_ttl=lease_ttl,
                recorder=claim_recorder,
                now=claimed_at,
            )
            claim_request = _accepted_request(claimed.task)
            if claim_request != request:
                raise AcceptedActionWorkerError("ACCEPTED_REQUEST_CHANGED_DURING_CLAIM")
            await self._gate.flush_audit(claim_recorder)
            await self._gate.commit()
        except BaseException:
            await self._gate.rollback()
            raise

        try:
            attempt = await self._delivery.begin_attempt(request, now=claimed_at)
            await self._delivery.commit()
        except BaseException:
            await self._delivery.rollback()
            raise
        if attempt.status is AcceptedActionDeliveryStatus.DEAD_LETTERED:
            return AcceptedActionDeliveryResult(
                task_id=task_id,
                request_id=request.request_id,
                status=AcceptedActionWorkerStatus.DEAD_LETTERED,
                attempts=attempt.attempts,
                error=attempt.last_error,
            )

        if attempt.status is AcceptedActionDeliveryStatus.SUCCEEDED:
            receipt = ActionExecutionReceipt(
                request_id=request.request_id,
                action_name=request.action_name,
                result_ref=attempt.result_ref,
            )
        else:
            try:
                receipt = await self._dispatcher.dispatch(
                    request,
                    tenant_id=request.scope.tenant_id,
                    family_id=request.scope.family_id,
                )
            except Exception as error:  # noqa: BLE001 - worker classifies failures
                reason = _error_text(error)
                permanent = isinstance(
                    error, (PermanentAcceptedActionError, AcceptedActionDispatchError)
                )
                if not permanent and attempt.attempts < self._max_attempts:
                    return AcceptedActionDeliveryResult(
                        task_id=task_id,
                        request_id=request.request_id,
                        status=AcceptedActionWorkerStatus.RETRY,
                        attempts=attempt.attempts,
                        error=reason,
                    )
                try:
                    dead = await self._delivery.mark_dead_lettered(request, error=reason)
                    await self._delivery.commit()
                except BaseException:
                    await self._delivery.rollback()
                    raise
                return AcceptedActionDeliveryResult(
                    task_id=task_id,
                    request_id=request.request_id,
                    status=AcceptedActionWorkerStatus.DEAD_LETTERED,
                    attempts=dead.attempts,
                    error=reason,
                )
            try:
                succeeded = await self._delivery.mark_succeeded(request, receipt)
                await self._delivery.commit()
            except BaseException:
                await self._delivery.rollback()
                raise
            attempt = succeeded

        try:
            completion_recorder = AuditRecorder()
            await self._gate.complete_claim(
                task_id,
                claim_owner=claim_owner,
                recorder=completion_recorder,
                now=completed_at,
            )
            await self._gate.flush_audit(completion_recorder)
            await self._gate.commit()
        except BaseException:
            # The domain and delivery ledger are already committed.  The live
            # claim will expire and a takeover will replay/complete safely.
            await self._gate.rollback()
            raise
        return AcceptedActionDeliveryResult(
            task_id=task_id,
            request_id=request.request_id,
            status=AcceptedActionWorkerStatus.SUCCEEDED,
            attempts=attempt.attempts,
            receipt=receipt,
        )

    async def run_once(
        self,
        queue: AcceptedActionQueue,
        *,
        claim_owner: str,
        limit: int = 100,
        lease_ttl: timedelta = timedelta(minutes=5),
        claimed_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> AcceptedActionWorkerReport:
        """Poll and process a bounded batch, isolating per-task failures."""

        if limit < 0:
            raise ValueError("limit must be non-negative")
        task_ids = await queue.pending_accepted_task_ids(limit=limit)
        results: list[AcceptedActionDeliveryResult] = []
        for task_id in task_ids:
            try:
                results.append(
                    await self.consume(
                        task_id,
                        claim_owner=claim_owner,
                        lease_ttl=lease_ttl,
                        claimed_at=claimed_at,
                        completed_at=completed_at,
                    )
                )
            except Exception as error:  # noqa: BLE001 - one bad task must not stop the poll
                request_id = task_id
                try:
                    task = await self._gate.get(task_id)
                    if task.action_request is not None:
                        request_id = task.action_request.request_id
                except Exception:  # noqa: BLE001 - preserve the original queue error
                    pass
                results.append(
                    AcceptedActionDeliveryResult(
                        task_id=task_id,
                        request_id=request_id,
                        status=AcceptedActionWorkerStatus.RETRY,
                        attempts=0,
                        error=_error_text(error),
                    )
                )
        return AcceptedActionWorkerReport(results=tuple(results))


class AcceptedActionScheduler:
    """Run bounded queue passes without becoming an unbounded daemon.

    A deployment scheduler may invoke this method repeatedly.  Within one
    invocation we stop when the queue is empty or when a pass contains no
    retryable result; terminal receipts are therefore not re-polled forever.
    ``max_polls`` remains a hard bound for a permanently busy queue.
    """

    def __init__(self, worker: AcceptedNamedActionWorker, queue: AcceptedActionQueue) -> None:
        self._worker = worker
        self._queue = queue

    async def run_until_idle(
        self,
        *,
        claim_owner: str,
        limit: int = 100,
        max_polls: int = 10,
        lease_ttl: timedelta = timedelta(minutes=5),
        claimed_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> AcceptedActionSchedulerReport:
        if max_polls < 1:
            raise ValueError("max_polls must be positive")
        reports: list[AcceptedActionWorkerReport] = []
        for _ in range(max_polls):
            report = await self._worker.run_once(
                self._queue,
                claim_owner=claim_owner,
                limit=limit,
                lease_ttl=lease_ttl,
                claimed_at=claimed_at,
                completed_at=completed_at,
            )
            reports.append(report)
            if report.pulled == 0 or report.retried == 0:
                break
        return AcceptedActionSchedulerReport(passes=tuple(reports))


def _accepted_request(task: HumanTask | HumanTaskClaim) -> NamedActionRequest:
    task_value = task.task if isinstance(task, HumanTaskClaim) else task
    if task_value.status is not GateStatus.DECIDED or task_value.action_request is None:
        raise AcceptedActionWorkerError("ACCEPTED_ACTION_REQUIRED")
    return task_value.action_request


def _error_text(error: BaseException) -> str:
    text = str(error).strip()
    return text or type(error).__name__


__all__ = [
    "AcceptedActionDeliveryResult",
    "AcceptedActionWorkerReport",
    "AcceptedActionWorkerStatus",
    "AcceptedActionQueue",
    "AcceptedActionScheduler",
    "AcceptedActionSchedulerReport",
    "AcceptedActionGate",
    "AcceptedActionWorkerError",
    "AcceptedNamedActionWorker",
    "PermanentAcceptedActionError",
]
