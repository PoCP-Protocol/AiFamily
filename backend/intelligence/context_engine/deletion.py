"""Retryable, tenant-scoped deletion worker for Context Broker projections.

This module is an application adapter, not a second persistence layer.  The
worker owns command/job/audit lifecycle only and delegates actual deletion to
an injected port (``ContextBroker.delete_subject`` in test/dev).  A completed
job therefore means that the injected port completed its contract; the worker
does not invent external-provider deletion receipts or silently delete data
outside that port.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol


class DeletionContractError(ValueError):
    """Base error for deletion commands and worker access."""


class DeletionScopeError(DeletionContractError):
    """Raised when a deletion job is accessed from another tenant."""


class DeletionStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DeletionEventType(StrEnum):
    REQUESTED = "DELETION_REQUESTED"
    ATTEMPTED = "DELETION_ATTEMPTED"
    COMPLETED = "DELETION_COMPLETED"
    FAILED = "DELETION_FAILED"


class SubjectDeletionPort(Protocol):
    """Port implemented by a context/projection store.

    Implementations must only return after their own deletion contract has
    completed.  A provider that cannot confirm deletion must raise, leaving the
    job ``FAILED`` rather than making the worker claim external completion.
    """

    def delete_subject(self, tenant_id: str, subject_id: str) -> int:
        """Delete projections for one tenant-scoped subject and return a count."""


@dataclass(frozen=True, slots=True)
class SubjectDeletionCommand:
    """An auditable, idempotent request to erase a subject's AI projections."""

    command_id: str
    tenant_id: str
    family_id: str
    subject_id: str
    deletion_ref: str
    requested_by: str
    idempotency_key: str
    correlation_id: str
    causation_id: str
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for name, value in (
            ("command_id", self.command_id),
            ("tenant_id", self.tenant_id),
            ("family_id", self.family_id),
            ("subject_id", self.subject_id),
            ("deletion_ref", self.deletion_ref),
            ("requested_by", self.requested_by),
            ("idempotency_key", self.idempotency_key),
            ("correlation_id", self.correlation_id),
            ("causation_id", self.causation_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise DeletionContractError(f"{name} is required")
        if self.requested_at.tzinfo is None:
            raise DeletionContractError("requested_at requires a timezone")


@dataclass(frozen=True, slots=True)
class DeletionJob:
    """Current state of one deletion command; only the worker may transition it."""

    command: SubjectDeletionCommand
    status: DeletionStatus = DeletionStatus.PENDING
    attempts: int = 0
    deleted_count: int = 0
    error_code: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.command, SubjectDeletionCommand):
            raise DeletionContractError("DELETION_COMMAND_REQUIRED")
        if not isinstance(self.status, DeletionStatus):
            raise DeletionContractError("DELETION_STATUS_UNSUPPORTED")
        if self.attempts < 0 or self.deleted_count < 0:
            raise DeletionContractError("DELETION_COUNTER_INVALID")
        if self.updated_at.tzinfo is None:
            raise DeletionContractError("updated_at requires a timezone")
        if self.status is DeletionStatus.COMPLETED and self.error_code is not None:
            raise DeletionContractError("completed deletion cannot carry an error")


@dataclass(frozen=True, slots=True)
class DeletionAuditEvent:
    """Safe audit projection; it never stores subject content or provider errors."""

    audit_id: str
    event_type: DeletionEventType
    command_id: str
    tenant_id: str
    family_id: str
    subject_id: str
    deletion_ref: str
    correlation_id: str
    causation_id: str
    attempt: int
    occurred_at: datetime
    deleted_count: int = 0
    error_code: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("audit_id", self.audit_id),
            ("command_id", self.command_id),
            ("tenant_id", self.tenant_id),
            ("family_id", self.family_id),
            ("subject_id", self.subject_id),
            ("deletion_ref", self.deletion_ref),
            ("correlation_id", self.correlation_id),
            ("causation_id", self.causation_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise DeletionContractError(f"{name} is required")
        if not isinstance(self.event_type, DeletionEventType):
            raise DeletionContractError("DELETION_EVENT_TYPE_UNSUPPORTED")
        if self.attempt < 0 or self.deleted_count < 0:
            raise DeletionContractError("DELETION_COUNTER_INVALID")
        if self.occurred_at.tzinfo is None:
            raise DeletionContractError("occurred_at requires a timezone")


class SubjectDeletionWorker:
    """Tenant-isolated state machine around an injected deletion port."""

    def __init__(
        self,
        storage: SubjectDeletionPort,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(getattr(storage, "delete_subject", None)):
            raise DeletionContractError("SUBJECT_DELETION_PORT_REQUIRED")
        self._storage = storage
        self._clock = clock or (lambda: datetime.now(UTC))
        self._jobs: dict[tuple[str, str], DeletionJob] = {}
        self._audit: list[DeletionAuditEvent] = []

    @property
    def audit_events(self) -> tuple[DeletionAuditEvent, ...]:
        return tuple(self._audit)

    def submit(self, command: SubjectDeletionCommand) -> DeletionJob:
        """Create a PENDING job, returning the existing job on replay."""

        if not isinstance(command, SubjectDeletionCommand):
            raise DeletionContractError("DELETION_COMMAND_REQUIRED")
        key = (command.tenant_id, command.idempotency_key)
        existing = self._jobs.get(key)
        if existing is not None:
            if existing.command != command:
                raise DeletionContractError("IDEMPOTENCY_CONFLICT")
            return existing
        now = self._now()
        job = DeletionJob(command=command, updated_at=now)
        self._jobs[key] = job
        self._record(job, DeletionEventType.REQUESTED, attempt=0, occurred_at=now)
        return job

    def get(self, *, tenant_id: str, idempotency_key: str) -> DeletionJob:
        """Read a job only through its tenant-scoped idempotency key."""

        job = self._jobs.get((tenant_id, idempotency_key))
        if job is None:
            raise DeletionContractError("DELETION_JOB_NOT_FOUND")
        return job

    def execute(self, *, tenant_id: str, idempotency_key: str) -> DeletionJob:
        """Run or safely replay one job; FAILED jobs are retryable."""

        job = self.get(tenant_id=tenant_id, idempotency_key=idempotency_key)
        if job.status is DeletionStatus.COMPLETED:
            return job
        attempt = job.attempts + 1
        now = self._now()
        job = replace(
            job,
            status=DeletionStatus.PENDING,
            attempts=attempt,
            error_code=None,
            updated_at=now,
        )
        self._jobs[(tenant_id, idempotency_key)] = job
        self._record(job, DeletionEventType.ATTEMPTED, attempt=attempt, occurred_at=now)
        try:
            deleted_count = self._storage.delete_subject(
                job.command.tenant_id,
                job.command.subject_id,
            )
            if not isinstance(deleted_count, int) or deleted_count < 0:
                raise TypeError("invalid deletion count")
        except Exception:
            failed = replace(
                job,
                status=DeletionStatus.FAILED,
                error_code="STORAGE_DELETE_FAILED",
                updated_at=self._now(),
            )
            self._jobs[(tenant_id, idempotency_key)] = failed
            self._record(
                failed,
                DeletionEventType.FAILED,
                attempt=attempt,
                occurred_at=failed.updated_at,
                error_code=failed.error_code,
            )
            return failed
        completed = replace(
            job,
            status=DeletionStatus.COMPLETED,
            deleted_count=deleted_count,
            updated_at=self._now(),
        )
        self._jobs[(tenant_id, idempotency_key)] = completed
        self._record(
            completed,
            DeletionEventType.COMPLETED,
            attempt=attempt,
            occurred_at=completed.updated_at,
            deleted_count=deleted_count,
        )
        return completed

    def _record(
        self,
        job: DeletionJob,
        event_type: DeletionEventType,
        *,
        attempt: int,
        occurred_at: datetime,
        deleted_count: int = 0,
        error_code: str | None = None,
    ) -> None:
        command = job.command
        self._audit.append(
            DeletionAuditEvent(
                audit_id=f"audit:{command.tenant_id}:{command.command_id}:{len(self._audit) + 1}",
                event_type=event_type,
                command_id=command.command_id,
                tenant_id=command.tenant_id,
                family_id=command.family_id,
                subject_id=command.subject_id,
                deletion_ref=command.deletion_ref,
                correlation_id=command.correlation_id,
                causation_id=command.causation_id,
                attempt=attempt,
                occurred_at=occurred_at,
                deleted_count=deleted_count,
                error_code=error_code,
            )
        )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise DeletionContractError("worker clock must return timezone-aware datetime")
        return now


# Short aliases keep the adapter convenient for callers while retaining the
# explicit subject scope in the canonical class names above.
DeletionCommand = SubjectDeletionCommand
DeletionWorker = SubjectDeletionWorker


__all__ = [
    "DeletionCommand",
    "DeletionAuditEvent",
    "DeletionContractError",
    "DeletionEventType",
    "DeletionJob",
    "DeletionScopeError",
    "DeletionStatus",
    "DeletionWorker",
    "SubjectDeletionCommand",
    "SubjectDeletionPort",
    "SubjectDeletionWorker",
]
