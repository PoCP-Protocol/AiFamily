"""Durable deletion queue contracts and an explicit synthetic adapter.

The existing :mod:`deletion` worker is a useful deterministic unit-test
adapter, but its in-memory job dictionary cannot survive a process restart.
This module moves the *queue boundary* behind a port.  ``InMemoryDurable...``
is intentionally only a test/dev adapter; it is not a claim that PostgreSQL,
an outbox, or an external projection store has been wired.

Production wiring must provide a transactional implementation of
``DurableDeletionStore`` and one ``ProjectionDeletionPort`` for every
projection kind (text, media, vector, cache, and derived projections).  A job
is completed only after every port returns a correlated, confirmed receipt.
Provider errors are reduced to stable error codes and never copied into the
audit trail.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import RLock
from typing import Protocol

from .deletion import SubjectDeletionCommand


class DurableDeletionError(ValueError):
    """Base error for the durable deletion adapter contract."""


class DurableDeletionScopeError(DurableDeletionError):
    """Raised when a job or receipt crosses its tenant boundary."""


class DurableDeletionStatus(StrEnum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    RETRYABLE = "RETRYABLE"
    COMPLETED = "COMPLETED"
    DEAD_LETTER = "DEAD_LETTER"


class ProjectionKind(StrEnum):
    """External and derived stores covered by the deletion obligation."""

    TEXT = "TEXT"
    MEDIA = "MEDIA"
    VECTOR = "VECTOR"
    CACHE = "CACHE"
    DERIVED = "DERIVED"


REQUIRED_PROJECTION_KINDS = frozenset(ProjectionKind)


class DurableDeletionEventType(StrEnum):
    REQUESTED = "DELETION_REQUESTED"
    CLAIMED = "DELETION_CLAIMED"
    PROJECTION_CONFIRMED = "PROJECTION_DELETION_CONFIRMED"
    RETRY_SCHEDULED = "DELETION_RETRY_SCHEDULED"
    COMPLETED = "DELETION_COMPLETED"
    DEAD_LETTERED = "DELETION_DEAD_LETTERED"


def _require_aware(name: str, value: datetime) -> None:
    if value.tzinfo is None:
        raise DurableDeletionError(f"{name} requires a timezone")


@dataclass(frozen=True, slots=True)
class ProjectionDeletionReceipt:
    """Provider-neutral proof returned by one projection adapter."""

    receipt_id: str
    projection: ProjectionKind
    tenant_id: str
    subject_id: str
    command_id: str
    correlation_id: str
    causation_id: str
    deleted_count: int
    confirmed: bool
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for name, value in (
            ("receipt_id", self.receipt_id),
            ("tenant_id", self.tenant_id),
            ("subject_id", self.subject_id),
            ("command_id", self.command_id),
            ("correlation_id", self.correlation_id),
            ("causation_id", self.causation_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise DurableDeletionError(f"{name} is required")
        try:
            projection = ProjectionKind(self.projection)
        except ValueError as exc:
            raise DurableDeletionError("PROJECTION_KIND_UNSUPPORTED") from exc
        object.__setattr__(self, "projection", projection)
        if not isinstance(self.confirmed, bool):
            raise DurableDeletionError("PROJECTION_CONFIRMATION_INVALID")
        if self.deleted_count < 0:
            raise DurableDeletionError("DELETION_COUNTER_INVALID")
        _require_aware("completed_at", self.completed_at)


class ProjectionDeletionPort(Protocol):
    """Port for one independently deletable text/media/index projection."""

    projection: ProjectionKind

    def delete_subject(self, command: SubjectDeletionCommand) -> ProjectionDeletionReceipt:
        """Delete one tenant/subject projection and return confirmed proof."""


@dataclass(frozen=True, slots=True)
class DurableDeletionJob:
    """Persistable queue state; no content or provider payload is retained."""

    command: SubjectDeletionCommand
    status: DurableDeletionStatus = DurableDeletionStatus.PENDING
    attempts: int = 0
    deleted_count: int = 0
    receipts: tuple[ProjectionDeletionReceipt, ...] = ()
    last_error_code: str | None = None
    available_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not isinstance(self.command, SubjectDeletionCommand):
            raise DurableDeletionError("DELETION_COMMAND_REQUIRED")
        try:
            status = DurableDeletionStatus(self.status)
        except ValueError as exc:
            raise DurableDeletionError("DELETION_STATUS_UNSUPPORTED") from exc
        object.__setattr__(self, "status", status)
        if self.attempts < 0 or self.deleted_count < 0:
            raise DurableDeletionError("DELETION_COUNTER_INVALID")
        for name, value in (("available_at", self.available_at), ("updated_at", self.updated_at)):
            _require_aware(name, value)
        if self.lease_expires_at is not None:
            _require_aware("lease_expires_at", self.lease_expires_at)
        for receipt in self.receipts:
            if not isinstance(receipt, ProjectionDeletionReceipt):
                raise DurableDeletionError("PROJECTION_RECEIPT_REQUIRED")
            if receipt.tenant_id != self.command.tenant_id:
                raise DurableDeletionScopeError("CROSS_TENANT_DELETION_RECEIPT")
            if receipt.subject_id != self.command.subject_id:
                raise DurableDeletionError("DELETION_SUBJECT_MISMATCH")
            if receipt.command_id != self.command.command_id:
                raise DurableDeletionError("DELETION_COMMAND_MISMATCH")
            if receipt.correlation_id != self.command.correlation_id:
                raise DurableDeletionError("DELETION_CORRELATION_MISMATCH")
        if self.status is DurableDeletionStatus.LEASED:
            if not self.lease_owner or self.lease_expires_at is None:
                raise DurableDeletionError("DELETION_LEASE_REQUIRED")
        elif self.lease_owner is not None or self.lease_expires_at is not None:
            raise DurableDeletionError("DELETION_LEASE_MUST_BE_CLEARED")
        if self.status is DurableDeletionStatus.COMPLETED and self.last_error_code is not None:
            raise DurableDeletionError("completed deletion cannot carry an error")


@dataclass(frozen=True, slots=True)
class DurableDeletionAuditEvent:
    """Minimal audit event with correlation, not content."""

    audit_id: str
    event_type: DurableDeletionEventType
    tenant_id: str
    family_id: str
    subject_id: str
    command_id: str
    deletion_ref: str
    correlation_id: str
    causation_id: str
    attempt: int
    occurred_at: datetime
    projection: ProjectionKind | None = None
    receipt_id: str | None = None
    deleted_count: int = 0
    error_code: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("audit_id", self.audit_id),
            ("tenant_id", self.tenant_id),
            ("family_id", self.family_id),
            ("subject_id", self.subject_id),
            ("command_id", self.command_id),
            ("deletion_ref", self.deletion_ref),
            ("correlation_id", self.correlation_id),
            ("causation_id", self.causation_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise DurableDeletionError(f"{name} is required")
        if self.attempt < 0 or self.deleted_count < 0:
            raise DurableDeletionError("DELETION_COUNTER_INVALID")
        _require_aware("occurred_at", self.occurred_at)
        try:
            event_type = DurableDeletionEventType(self.event_type)
        except ValueError as exc:
            raise DurableDeletionError("DELETION_EVENT_TYPE_UNSUPPORTED") from exc
        object.__setattr__(self, "event_type", event_type)
        if self.projection is not None:
            try:
                object.__setattr__(self, "projection", ProjectionKind(self.projection))
            except ValueError as exc:
                raise DurableDeletionError("PROJECTION_KIND_UNSUPPORTED") from exc


@dataclass(frozen=True, slots=True)
class DeadLetterEntry:
    """Terminal queue record retaining only safe retry metadata."""

    tenant_id: str
    command_id: str
    idempotency_key: str
    error_code: str
    attempts: int
    dead_lettered_at: datetime
    correlation_id: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.tenant_id,
                self.command_id,
                self.idempotency_key,
                self.error_code,
                self.correlation_id,
            )
        ):
            raise DurableDeletionError("DEAD_LETTER_FIELD_REQUIRED")
        if self.attempts < 0:
            raise DurableDeletionError("DELETION_COUNTER_INVALID")
        _require_aware("dead_lettered_at", self.dead_lettered_at)


class DurableDeletionStore(Protocol):
    """Transactional queue/outbox port to be implemented by production storage."""

    def enqueue(self, command: SubjectDeletionCommand, *, now: datetime) -> DurableDeletionJob: ...

    def get(self, *, tenant_id: str, idempotency_key: str) -> DurableDeletionJob: ...

    def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_ttl: timedelta,
        tenant_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> DurableDeletionJob | None: ...

    def save(self, job: DurableDeletionJob) -> DurableDeletionJob: ...

    def append_audit(self, event: DurableDeletionAuditEvent) -> None: ...

    def audits(self, *, tenant_id: str | None = None) -> tuple[DurableDeletionAuditEvent, ...]: ...

    def dead_letter(
        self,
        job: DurableDeletionJob,
        *,
        error_code: str,
        now: datetime,
    ) -> DeadLetterEntry: ...

    def dead_letters(self, *, tenant_id: str | None = None) -> tuple[DeadLetterEntry, ...]: ...


class InMemoryDurableDeletionStore:
    """Synthetic restart-capable adapter; replace with Postgres/outbox in production."""

    production_ready = False

    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str], DurableDeletionJob] = {}
        self._audit: list[DurableDeletionAuditEvent] = []
        self._dead_letters: list[DeadLetterEntry] = []
        self._lock = RLock()

    def enqueue(self, command: SubjectDeletionCommand, *, now: datetime) -> DurableDeletionJob:
        _require_aware("now", now)
        key = (command.tenant_id, command.idempotency_key)
        with self._lock:
            current = self._jobs.get(key)
            if current is not None:
                if current.command != command:
                    raise DurableDeletionError("IDEMPOTENCY_CONFLICT")
                return current
            job = DurableDeletionJob(command=command, available_at=now, updated_at=now)
            self._jobs[key] = job
            return job

    def get(self, *, tenant_id: str, idempotency_key: str) -> DurableDeletionJob:
        with self._lock:
            job = self._jobs.get((tenant_id, idempotency_key))
            if job is None:
                raise DurableDeletionError("DELETION_JOB_NOT_FOUND")
            return job

    def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_ttl: timedelta,
        tenant_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> DurableDeletionJob | None:
        if not worker_id.strip():
            raise DurableDeletionError("DELETION_WORKER_ID_REQUIRED")
        _require_aware("now", now)
        if lease_ttl <= timedelta(0):
            raise DurableDeletionError("DELETION_LEASE_TTL_INVALID")
        with self._lock:
            candidates = self._jobs.items()
            for key, job in candidates:
                if tenant_id is not None and key[0] != tenant_id:
                    continue
                if idempotency_key is not None and key[1] != idempotency_key:
                    continue
                lease_expired = (
                    job.status is DurableDeletionStatus.LEASED
                    and job.lease_expires_at is not None
                    and job.lease_expires_at <= now
                )
                ready = (
                    job.status
                    in (
                        DurableDeletionStatus.PENDING,
                        DurableDeletionStatus.RETRYABLE,
                    )
                    and job.available_at <= now
                )
                if not ready and not lease_expired:
                    continue
                leased = replace(
                    job,
                    status=DurableDeletionStatus.LEASED,
                    lease_owner=worker_id,
                    lease_expires_at=now + lease_ttl,
                    updated_at=now,
                )
                self._jobs[key] = leased
                return leased
        return None

    def save(self, job: DurableDeletionJob) -> DurableDeletionJob:
        key = (job.command.tenant_id, job.command.idempotency_key)
        with self._lock:
            current = self._jobs.get(key)
            if current is None:
                raise DurableDeletionError("DELETION_JOB_NOT_FOUND")
            if current.command != job.command:
                raise DurableDeletionError("DELETION_COMMAND_MISMATCH")
            self._jobs[key] = job
            return job

    def append_audit(self, event: DurableDeletionAuditEvent) -> None:
        with self._lock:
            self._audit.append(event)

    def audits(self, *, tenant_id: str | None = None) -> tuple[DurableDeletionAuditEvent, ...]:
        with self._lock:
            events = self._audit
            if tenant_id is not None:
                events = [item for item in events if item.tenant_id == tenant_id]
            return tuple(events)

    def dead_letter(
        self,
        job: DurableDeletionJob,
        *,
        error_code: str,
        now: datetime,
    ) -> DeadLetterEntry:
        _require_aware("now", now)
        entry = DeadLetterEntry(
            tenant_id=job.command.tenant_id,
            command_id=job.command.command_id,
            idempotency_key=job.command.idempotency_key,
            error_code=error_code,
            attempts=job.attempts,
            dead_lettered_at=now,
            correlation_id=job.command.correlation_id,
        )
        with self._lock:
            key = (job.command.tenant_id, job.command.idempotency_key)
            self._jobs[key] = replace(
                job,
                status=DurableDeletionStatus.DEAD_LETTER,
                last_error_code=error_code,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=now,
            )
            self._dead_letters.append(entry)
        return entry

    def dead_letters(self, *, tenant_id: str | None = None) -> tuple[DeadLetterEntry, ...]:
        with self._lock:
            entries = self._dead_letters
            if tenant_id is not None:
                entries = [item for item in entries if item.tenant_id == tenant_id]
            return tuple(entries)


class DurableDeletionWorker:
    """Lease, execute and retry deletion commands through injected ports."""

    def __init__(
        self,
        store: DurableDeletionStore,
        projections: Iterable[ProjectionDeletionPort],
        *,
        clock: Callable[[], datetime] | None = None,
        lease_ttl: timedelta = timedelta(minutes=5),
        retry_delay: timedelta = timedelta(minutes=1),
        max_attempts: int = 3,
        required_projection_kinds: frozenset[ProjectionKind] = REQUIRED_PROJECTION_KINDS,
    ) -> None:
        if not callable(getattr(store, "enqueue", None)) or not callable(
            getattr(store, "claim", None)
        ):
            raise DurableDeletionError("DURABLE_DELETION_STORE_REQUIRED")
        if lease_ttl <= timedelta(0) or retry_delay < timedelta(0):
            raise DurableDeletionError("DELETION_TIMING_INVALID")
        if max_attempts < 1:
            raise DurableDeletionError("DELETION_MAX_ATTEMPTS_INVALID")
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_ttl = lease_ttl
        self._retry_delay = retry_delay
        self._max_attempts = max_attempts
        self._required = frozenset(required_projection_kinds)
        self._projections = tuple(projections)
        kinds: list[ProjectionKind] = []
        for port in self._projections:
            try:
                kind = ProjectionKind(port.projection)
            except (AttributeError, ValueError) as exc:
                raise DurableDeletionError("PROJECTION_KIND_REQUIRED") from exc
            if kind in kinds:
                raise DurableDeletionError("DUPLICATE_PROJECTION_PORT")
            kinds.append(kind)
        if set(kinds) != self._required:
            raise DurableDeletionError("REQUIRED_PROJECTION_PORTS_MISSING")

    @property
    def audit_events(self) -> tuple[DurableDeletionAuditEvent, ...]:
        return self._store.audits()

    @property
    def dead_letter_entries(self) -> tuple[DeadLetterEntry, ...]:
        return self._store.dead_letters()

    def submit(self, command: SubjectDeletionCommand) -> DurableDeletionJob:
        if not isinstance(command, SubjectDeletionCommand):
            raise DurableDeletionError("DELETION_COMMAND_REQUIRED")
        now = self._now()
        job = self._store.enqueue(command, now=now)
        if not any(
            event.command_id == command.command_id
            and event.event_type is DurableDeletionEventType.REQUESTED
            for event in self._store.audits(tenant_id=command.tenant_id)
        ):
            self._audit(job, DurableDeletionEventType.REQUESTED, now=now)
        return job

    def get(self, *, tenant_id: str, idempotency_key: str) -> DurableDeletionJob:
        job = self._store.get(tenant_id=tenant_id, idempotency_key=idempotency_key)
        if job.command.tenant_id != tenant_id:
            raise DurableDeletionScopeError("CROSS_TENANT_DELETION_JOB")
        return job

    def run_once(self, worker_id: str = "deletion-worker") -> DurableDeletionJob | None:
        now = self._now()
        claimed = self._store.claim(
            worker_id=worker_id,
            now=now,
            lease_ttl=self._lease_ttl,
        )
        if claimed is None:
            return None
        return self._process(claimed, worker_id=worker_id)

    def execute(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        worker_id: str = "deletion-worker",
    ) -> DurableDeletionJob:
        current = self.get(tenant_id=tenant_id, idempotency_key=idempotency_key)
        if current.status in (DurableDeletionStatus.COMPLETED, DurableDeletionStatus.DEAD_LETTER):
            return current
        claimed = self._store.claim(
            worker_id=worker_id,
            now=self._now(),
            lease_ttl=self._lease_ttl,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
        )
        if claimed is None:
            return self.get(tenant_id=tenant_id, idempotency_key=idempotency_key)
        return self._process(claimed, worker_id=worker_id)

    process_next = run_once

    def _process(self, claimed: DurableDeletionJob, *, worker_id: str) -> DurableDeletionJob:
        now = self._now()
        if claimed.lease_owner != worker_id:
            raise DurableDeletionError("DELETION_LEASE_OWNER_MISMATCH")
        job = replace(
            claimed,
            attempts=claimed.attempts + 1,
            updated_at=now,
        )
        self._store.save(job)
        self._audit(job, DurableDeletionEventType.CLAIMED, now=now)
        existing = {receipt.projection for receipt in job.receipts}
        receipts = list(job.receipts)
        try:
            for port in self._projections:
                kind = ProjectionKind(port.projection)
                if kind in existing:
                    continue
                receipt = port.delete_subject(job.command)
                self._validate_receipt(receipt, job.command, kind)
                receipts.append(receipt)
                existing.add(kind)
                job = replace(job, receipts=tuple(receipts), updated_at=self._now())
                self._store.save(job)
                self._audit(
                    job,
                    DurableDeletionEventType.PROJECTION_CONFIRMED,
                    now=job.updated_at,
                    projection=receipt.projection,
                    receipt_id=receipt.receipt_id,
                    deleted_count=receipt.deleted_count,
                )
        except Exception:
            error_code = "PROJECTION_DELETE_FAILED"
            failed = replace(
                job,
                status=DurableDeletionStatus.RETRYABLE,
                last_error_code=error_code,
                available_at=self._now() + self._retry_delay,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=self._now(),
            )
            if failed.attempts >= self._max_attempts:
                self._store.dead_letter(failed, error_code=error_code, now=failed.updated_at)
                dead = self._store.get(
                    tenant_id=failed.command.tenant_id,
                    idempotency_key=failed.command.idempotency_key,
                )
                self._audit(
                    dead,
                    DurableDeletionEventType.DEAD_LETTERED,
                    now=dead.updated_at,
                    error_code=error_code,
                )
                return dead
            self._store.save(failed)
            self._audit(
                failed,
                DurableDeletionEventType.RETRY_SCHEDULED,
                now=failed.updated_at,
                error_code=error_code,
            )
            return failed
        completed = replace(
            job,
            status=DurableDeletionStatus.COMPLETED,
            deleted_count=sum(receipt.deleted_count for receipt in receipts),
            last_error_code=None,
            lease_owner=None,
            lease_expires_at=None,
            updated_at=self._now(),
        )
        self._store.save(completed)
        self._audit(
            completed,
            DurableDeletionEventType.COMPLETED,
            now=completed.updated_at,
            deleted_count=completed.deleted_count,
        )
        return completed

    @staticmethod
    def _validate_receipt(
        receipt: ProjectionDeletionReceipt,
        command: SubjectDeletionCommand,
        expected_kind: ProjectionKind,
    ) -> None:
        if not isinstance(receipt, ProjectionDeletionReceipt):
            raise DurableDeletionError("PROJECTION_RECEIPT_REQUIRED")
        if receipt.projection is not expected_kind:
            raise DurableDeletionError("PROJECTION_KIND_MISMATCH")
        if not receipt.confirmed:
            raise DurableDeletionError("UNCONFIRMED_PROJECTION_RECEIPT")
        if receipt.tenant_id != command.tenant_id:
            raise DurableDeletionScopeError("CROSS_TENANT_DELETION_RECEIPT")
        if receipt.subject_id != command.subject_id or receipt.command_id != command.command_id:
            raise DurableDeletionError("DELETION_RECEIPT_SCOPE_MISMATCH")
        if (
            receipt.correlation_id != command.correlation_id
            or receipt.causation_id != command.causation_id
        ):
            raise DurableDeletionError("DELETION_RECEIPT_CORRELATION_MISMATCH")

    def _audit(
        self,
        job: DurableDeletionJob,
        event_type: DurableDeletionEventType,
        *,
        now: datetime,
        projection: ProjectionKind | None = None,
        receipt_id: str | None = None,
        deleted_count: int = 0,
        error_code: str | None = None,
    ) -> None:
        self._store.append_audit(
            DurableDeletionAuditEvent(
                audit_id=(
                    f"audit:{job.command.tenant_id}:{job.command.command_id}:"
                    f"{len(self._store.audits(tenant_id=job.command.tenant_id)) + 1}"
                ),
                event_type=event_type,
                tenant_id=job.command.tenant_id,
                family_id=job.command.family_id,
                subject_id=job.command.subject_id,
                command_id=job.command.command_id,
                deletion_ref=job.command.deletion_ref,
                correlation_id=job.command.correlation_id,
                causation_id=job.command.causation_id,
                attempt=job.attempts,
                occurred_at=now,
                projection=projection,
                receipt_id=receipt_id,
                deleted_count=deleted_count,
                error_code=error_code,
            )
        )

    def _now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise DurableDeletionError("worker clock must return timezone-aware datetime")
        return now


__all__ = [
    "DeadLetterEntry",
    "DurableDeletionAuditEvent",
    "DurableDeletionError",
    "DurableDeletionEventType",
    "DurableDeletionJob",
    "DurableDeletionScopeError",
    "DurableDeletionStatus",
    "DurableDeletionStore",
    "DurableDeletionWorker",
    "InMemoryDurableDeletionStore",
    "ProjectionDeletionPort",
    "ProjectionDeletionReceipt",
    "ProjectionKind",
    "REQUIRED_PROJECTION_KINDS",
]
