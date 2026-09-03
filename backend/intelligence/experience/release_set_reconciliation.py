"""Bounded, restart-safe reconciliation for uncertain ReleaseSet deployments."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal, Protocol

from .release_set_deployment import (
    FamilyExperienceReleaseSetDeploymentService,
    ReleaseSetDeploymentAcknowledgement,
    ReleaseSetReconciliationLease,
    ReleaseSetTransitionClaim,
    ReleaseSetTransitionCoordinator,
)
from .release_set_persistence import FamilyExperienceReleaseSetReader

ExternalTransitionState = Literal["PENDING", "APPLIED", "ABSENT", "FAILED"]


class ReleaseSetReconciliationError(ValueError):
    """The reconciliation boundary is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class ExternalTransitionObservation:
    state: ExternalTransitionState
    acknowledgement: ReleaseSetDeploymentAcknowledgement | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.state not in {"PENDING", "APPLIED", "ABSENT", "FAILED"}:
            raise ReleaseSetReconciliationError("EXTERNAL_TRANSITION_STATE_INVALID")
        if self.state == "APPLIED":
            if self.acknowledgement is None or self.error_code is not None:
                raise ReleaseSetReconciliationError(
                    "APPLIED_TRANSITION_ACKNOWLEDGEMENT_REQUIRED"
                )
        elif self.acknowledgement is not None:
            raise ReleaseSetReconciliationError(
                "NON_APPLIED_TRANSITION_ACKNOWLEDGEMENT_FORBIDDEN"
            )
        if self.state == "FAILED" and not (self.error_code and self.error_code.strip()):
            raise ReleaseSetReconciliationError("FAILED_TRANSITION_ERROR_REQUIRED")


class ReleaseSetTransitionObserver(Protocol):
    async def observe(
        self,
        transition: ReleaseSetTransitionClaim,
    ) -> ExternalTransitionObservation: ...


class ReconciliationOutcome(StrEnum):
    COMMITTED = "COMMITTED"
    RESCHEDULED = "RESCHEDULED"
    ESCALATED = "ESCALATED"
    RETRY = "RETRY"


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    transition_id: str
    outcome: ReconciliationOutcome
    attempt: int
    receipt_id: str | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    results: tuple[ReconciliationResult, ...]

    @property
    def claimed(self) -> int:
        return len(self.results)


@dataclass(frozen=True, slots=True)
class ReleaseSetReconciliationScheduler:
    environment: str
    worker_id: str
    transitions: ReleaseSetTransitionCoordinator
    release_sets: FamilyExperienceReleaseSetReader
    observer: ReleaseSetTransitionObserver
    deployment: FamilyExperienceReleaseSetDeploymentService
    stale_after: timedelta = timedelta(minutes=2)
    lease_ttl: timedelta = timedelta(seconds=30)
    retry_base: timedelta = timedelta(seconds=30)
    retry_max: timedelta = timedelta(minutes=30)
    limit: int = 20
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if not self.environment.strip() or not self.worker_id.strip():
            raise ReleaseSetReconciliationError("RECONCILIATION_IDENTITY_REQUIRED")
        for dependency, method_name in (
            (self.transitions, "claim_reconcilable"),
            (self.transitions, "reschedule_reconciliation"),
            (self.release_sets, "get"),
            (self.observer, "observe"),
        ):
            if not callable(getattr(dependency, method_name, None)):
                raise ReleaseSetReconciliationError(
                    f"RECONCILIATION_{method_name.upper()}_REQUIRED"
                )
        if (
            self.stale_after < timedelta(0)
            or self.lease_ttl <= timedelta(0)
            or self.retry_base <= timedelta(0)
            or self.retry_max < self.retry_base
        ):
            raise ReleaseSetReconciliationError("RECONCILIATION_DURATION_INVALID")
        if not 1 <= self.limit <= 100:
            raise ReleaseSetReconciliationError("RECONCILIATION_LIMIT_INVALID")

    async def run_once(self) -> ReconciliationReport:
        now = self._now()
        leases = await self.transitions.claim_reconcilable(
            environment=self.environment,
            worker_id=self.worker_id,
            now=now,
            stale_after=self.stale_after,
            lease_ttl=self.lease_ttl,
            limit=self.limit,
        )
        results = []
        for lease in leases:
            results.append(await self._reconcile(lease, now))
        return ReconciliationReport(tuple(results))

    async def _reconcile(
        self,
        lease: ReleaseSetReconciliationLease,
        now: datetime,
    ) -> ReconciliationResult:
        transition = lease.transition
        try:
            source = await self.release_sets.get(transition.source_release_set_id)
            target = (
                await self.release_sets.get(transition.target_release_set_id)
                if transition.target_release_set_id is not None
                else None
            )
            if source is None or (
                transition.target_release_set_id is not None and target is None
            ):
                return await self._reschedule(
                    lease,
                    now,
                    ReconciliationOutcome.ESCALATED,
                    "RELEASE_SET_SNAPSHOT_MISSING",
                )
            stored_acknowledgement = transition.acknowledgement()
            observation = (
                ExternalTransitionObservation(
                    state="APPLIED",
                    acknowledgement=stored_acknowledgement,
                )
                if stored_acknowledgement is not None
                else await self.observer.observe(transition)
            )
            if observation.state == "APPLIED":
                receipt = await self.deployment.reconcile(
                    source,
                    observation.acknowledgement,  # type: ignore[arg-type]
                    idempotency_key=transition.idempotency_key,
                    target=target,
                )
                return ReconciliationResult(
                    transition_id=transition.transition_id,
                    outcome=ReconciliationOutcome.COMMITTED,
                    attempt=lease.attempt,
                    receipt_id=receipt.receipt_id,
                    error_code=None,
                )
            if observation.state == "PENDING":
                return await self._reschedule(
                    lease,
                    now,
                    ReconciliationOutcome.RESCHEDULED,
                    "EXTERNAL_TRANSITION_PENDING",
                )
            code = observation.error_code or f"EXTERNAL_TRANSITION_{observation.state}"
            return await self._reschedule(
                lease,
                now,
                ReconciliationOutcome.ESCALATED,
                code,
            )
        except Exception as error:  # noqa: BLE001 - worker records sanitized type only
            return await self._reschedule(
                lease,
                now,
                ReconciliationOutcome.RETRY,
                type(error).__name__,
            )

    async def _reschedule(
        self,
        lease: ReleaseSetReconciliationLease,
        now: datetime,
        outcome: ReconciliationOutcome,
        error_code: str,
    ) -> ReconciliationResult:
        delay = min(
            self.retry_base * (2 ** min(lease.attempt - 1, 16)),
            self.retry_max,
        )
        await self.transitions.reschedule_reconciliation(
            lease,
            next_reconcile_at=now + delay,
            error_code=error_code,
        )
        return ReconciliationResult(
            transition_id=lease.transition.transition_id,
            outcome=outcome,
            attempt=lease.attempt,
            receipt_id=None,
            error_code=error_code[:128],
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReleaseSetReconciliationError("RECONCILIATION_TIME_MUST_BE_AWARE")
        return value


__all__ = [
    "ExternalTransitionObservation",
    "ReconciliationOutcome",
    "ReconciliationReport",
    "ReconciliationResult",
    "ReleaseSetReconciliationError",
    "ReleaseSetReconciliationScheduler",
    "ReleaseSetTransitionObserver",
]
