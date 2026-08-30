"""One-shot durable consumer for accepted Human Gate requests.

The worker is intentionally a narrow command handler rather than a second
business orchestrator.  It loads a decision from the durable Human Gate,
rejects anything that is not an accepted request, and delegates execution to
the FGCN application command.  That command owns scope checks, the transaction,
and request-id idempotency.

There is no process loop or scheduler here yet.  A queue adapter can call this
handler from a future ``workflow_worker`` process; the handler is already
safe to retry after a crash because the owning command replays by the durable
``NamedActionRequest.request_id``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from backend.domains.service.domain.errors import ServiceConflictError
from backend.intelligence.human_gate import (
    GateStatus,
    HumanGateError,
    HumanTask,
    HumanTaskClaim,
)
from backend.platform.audit import AuditRecorder

from .admission import DEFAULT_ASYNC_PROVIDER_ADMISSION, AsyncProviderAdmissionQuery
from .application import FGCNAssignmentRepository, execute_task_assignment_named_action
from .contracts import TaskAssignment


class HumanTaskReader(Protocol):
    """The read capability used for the preflight lifecycle check."""

    async def get(self, task_id: str) -> HumanTask: ...


class HumanTaskClaimer(HumanTaskReader, Protocol):
    """Durable claim/ack seam owned by the Human Gate persistence adapter."""

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


async def consume_accepted_human_task(
    gate: HumanTaskClaimer,
    repo: FGCNAssignmentRepository,
    task_id: str,
    *,
    recorder: AuditRecorder,
    claim_owner: str,
    provider_admission: AsyncProviderAdmissionQuery = DEFAULT_ASYNC_PROVIDER_ADMISSION,
    lease_ttl: timedelta = timedelta(minutes=5),
    claimed_at: datetime | None = None,
    completed_at: datetime | None = None,
    accepted_at: datetime | None = None,
) -> TaskAssignment:
    """Consume one accepted HumanTask and execute its FGCN Named Action.

    A rejected, escalated, open, or expired task has no executable business
    command and is refused.  The worker first durably claims the accepted
    request and commits that claim.  If the process dies after the FGCN
    command has committed, a later worker can take over after the lease expires
    and the request id makes the retry return the same assignment without a
    second assignment or audit event.
    """

    task = await gate.get(task_id)
    if task.status is not GateStatus.DECIDED or task.action_request is None:
        raise ServiceConflictError("fgcn_human_task_has_no_accepted_action")

    try:
        claimed = await gate.claim_accepted(
            task_id,
            claim_owner=claim_owner,
            lease_ttl=lease_ttl,
            recorder=recorder,
            now=claimed_at,
        )
        await gate.flush_audit(recorder)
        await gate.commit()
    except HumanGateError as exc:
        await gate.rollback()
        if exc.code in {"TASK_ALREADY_CLAIMED", "TASK_CLAIM_LOST"}:
            raise ServiceConflictError("fgcn_human_task_already_claimed") from exc
        raise
    except BaseException:
        await gate.rollback()
        raise

    action_request = claimed.task.action_request
    if action_request is None:  # pragma: no cover - HumanTaskClaim enforces this
        raise ServiceConflictError("fgcn_human_task_has_no_accepted_action")
    assignment = await execute_task_assignment_named_action(
        repo,
        action_request,
        recorder=recorder,
        provider_admission=provider_admission,
        accepted_at=accepted_at,
    )

    try:
        await gate.complete_claim(
            task_id,
            claim_owner=claim_owner,
            recorder=recorder,
            now=completed_at,
        )
        await gate.flush_audit(recorder)
        await gate.commit()
    except BaseException:
        # The assignment command has already committed.  Keeping the claim on
        # a completion/audit failure is safe: a later lease takeover replays
        # the request id and can finish the acknowledgement.
        await gate.rollback()
        raise
    return assignment


__all__ = ["HumanTaskClaimer", "HumanTaskReader", "consume_accepted_human_task"]
