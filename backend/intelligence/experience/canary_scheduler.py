"""Restart-safe bounded scheduler for family-experience canary supervision."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol, cast

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.evaluation.deployment import (
    DeploymentOperation,
    DeploymentPhase,
    DeploymentReceipt,
)
from backend.intelligence.evaluation.release_catalog import (
    ReleaseCandidate,
    ReleaseCandidateStatus,
)

from .canary_alerts import CanaryAlertingSupervisor
from .canary_supervision import (
    CanaryHealth,
    CanaryRollbackBlockedError,
    CanarySupervisionError,
)


class CanaryJobStatus(StrEnum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CanaryJobOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    RESCHEDULED = "RESCHEDULED"
    RETRY = "RETRY"
    FAILED = "FAILED"


class CanarySchedulerBase(DeclarativeBase):
    """Metadata-only durable scheduler boundary."""


class CanaryJobRow(CanarySchedulerBase):
    __tablename__ = "ai_family_experience_canary_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'LEASED', 'COMPLETED', 'FAILED')",
            name="ck_ai_family_experience_canary_job_status",
        ),
        Index(
            "ix_ai_family_experience_canary_jobs_due",
            "environment",
            "status",
            "due_at",
        ),
    )

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(256), nullable=False)
    candidate_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    rollback_control_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supervision_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(256), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rollback_receipt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class CanaryJob:
    job_id: str
    candidate: ReleaseCandidate
    canary_receipt: DeploymentReceipt
    rollback_control_id: str | None
    supervision_key: str
    status: CanaryJobStatus
    due_at: datetime
    attempts: int
    lease_owner: str | None
    lease_until: datetime | None
    assessment_id: str | None
    rollback_receipt_id: str | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _validate_job(self)


@dataclass(frozen=True, slots=True)
class CanaryJobResult:
    job_id: str
    outcome: CanaryJobOutcome
    assessment_id: str | None
    rollback_receipt_id: str | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class CanarySchedulerReport:
    results: tuple[CanaryJobResult, ...]

    @property
    def claimed(self) -> int:
        return len(self.results)


class CanaryJobStore(Protocol):
    async def enqueue(self, job: CanaryJob) -> CanaryJob: ...

    async def get(self, job_id: str) -> CanaryJob | None: ...

    async def claim_due(
        self,
        *,
        environment: str,
        worker_id: str,
        now: datetime,
        lease_ttl: timedelta,
        limit: int,
    ) -> tuple[CanaryJob, ...]: ...

    async def complete(
        self,
        job_id: str,
        *,
        worker_id: str,
        assessment_id: str,
        rollback_receipt_id: str | None,
        now: datetime,
    ) -> CanaryJob: ...

    async def reschedule(
        self,
        job_id: str,
        *,
        worker_id: str,
        due_at: datetime,
        assessment_id: str | None,
        error_code: str | None,
        now: datetime,
    ) -> CanaryJob: ...

    async def fail(
        self,
        job_id: str,
        *,
        worker_id: str,
        assessment_id: str | None,
        error_code: str,
        now: datetime,
    ) -> CanaryJob: ...


class InMemoryCanaryJobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, CanaryJob] = {}

    async def enqueue(self, job: CanaryJob) -> CanaryJob:
        existing = self.jobs.get(job.job_id)
        if existing is not None and not _same_job_request(existing, job):
            raise CanarySupervisionError("CANARY_JOB_CONFLICT")
        self.jobs[job.job_id] = existing or job
        return existing or job

    async def get(self, job_id: str) -> CanaryJob | None:
        return self.jobs.get(job_id)

    async def claim_due(
        self,
        *,
        environment: str,
        worker_id: str,
        now: datetime,
        lease_ttl: timedelta,
        limit: int,
    ) -> tuple[CanaryJob, ...]:
        _validate_claim(environment, worker_id, now, lease_ttl, limit)
        eligible = [
            job
            for job in self.jobs.values()
            if job.candidate.environment == environment
            and job.due_at <= now
            and (
                job.status is CanaryJobStatus.PENDING
                or (
                    job.status is CanaryJobStatus.LEASED
                    and job.lease_until is not None
                    and job.lease_until <= now
                )
            )
        ]
        claimed: list[CanaryJob] = []
        for job in sorted(eligible, key=lambda item: (item.due_at, item.job_id))[:limit]:
            updated = replace(
                job,
                status=CanaryJobStatus.LEASED,
                attempts=job.attempts + 1,
                lease_owner=worker_id,
                lease_until=now + lease_ttl,
                updated_at=now,
            )
            self.jobs[job.job_id] = updated
            claimed.append(updated)
        return tuple(claimed)

    async def complete(self, job_id: str, **kwargs) -> CanaryJob:
        return self._terminal(job_id, status=CanaryJobStatus.COMPLETED, **kwargs)

    async def reschedule(self, job_id: str, **kwargs) -> CanaryJob:
        job = self._leased(job_id, kwargs["worker_id"])
        updated = replace(
            job,
            status=CanaryJobStatus.PENDING,
            due_at=_aware(kwargs["due_at"]),
            lease_owner=None,
            lease_until=None,
            assessment_id=kwargs["assessment_id"],
            last_error_code=kwargs["error_code"],
            updated_at=_aware(kwargs["now"]),
        )
        self.jobs[job_id] = updated
        return updated

    async def fail(self, job_id: str, **kwargs) -> CanaryJob:
        return self._terminal(job_id, status=CanaryJobStatus.FAILED, **kwargs)

    def _terminal(self, job_id: str, *, status: CanaryJobStatus, **kwargs) -> CanaryJob:
        job = self._leased(job_id, kwargs["worker_id"])
        updated = replace(
            job,
            status=status,
            lease_owner=None,
            lease_until=None,
            assessment_id=kwargs["assessment_id"],
            rollback_receipt_id=kwargs.get("rollback_receipt_id"),
            last_error_code=kwargs.get("error_code"),
            updated_at=_aware(kwargs["now"]),
        )
        self.jobs[job_id] = updated
        return updated

    def _leased(self, job_id: str, worker_id: str) -> CanaryJob:
        job = self.jobs.get(job_id)
        if job is None:
            raise CanarySupervisionError("CANARY_JOB_NOT_FOUND")
        if job.status is not CanaryJobStatus.LEASED or job.lease_owner != worker_id:
            raise CanarySupervisionError("CANARY_JOB_LEASE_MISMATCH")
        return job


class SqlAlchemyCanaryJobStore:
    """Session-per-operation SQL queue; claims commit before network calls."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def enqueue(self, job: CanaryJob) -> CanaryJob:
        async with self._session_factory() as session, session.begin():
            row = await session.scalar(
                select(CanaryJobRow).where(
                    (CanaryJobRow.job_id == job.job_id)
                    | (CanaryJobRow.supervision_key == job.supervision_key)
                )
            )
            if row is not None:
                existing = _stored(row)
                if not _same_job_request(existing, job):
                    raise CanarySupervisionError("CANARY_JOB_CONFLICT")
                return existing
            session.add(_row(job))
        return job

    async def get(self, job_id: str) -> CanaryJob | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(CanaryJobRow).where(CanaryJobRow.job_id == job_id)
            )
            return None if row is None else _stored(row)

    async def claim_due(
        self,
        *,
        environment: str,
        worker_id: str,
        now: datetime,
        lease_ttl: timedelta,
        limit: int,
    ) -> tuple[CanaryJob, ...]:
        _validate_claim(environment, worker_id, now, lease_ttl, limit)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                select(CanaryJobRow)
                .where(
                    CanaryJobRow.environment == environment,
                    CanaryJobRow.due_at <= now,
                    or_(
                        CanaryJobRow.status == CanaryJobStatus.PENDING.value,
                        and_(
                            CanaryJobRow.status == CanaryJobStatus.LEASED.value,
                            CanaryJobRow.lease_until <= now,
                        ),
                    ),
                )
                .order_by(CanaryJobRow.due_at, CanaryJobRow.job_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = tuple(result.scalars())
            for row in rows:
                row.status = CanaryJobStatus.LEASED.value
                row.attempts += 1
                row.lease_owner = worker_id
                row.lease_until = now + lease_ttl
                row.updated_at = now
            await session.flush()
            return tuple(_stored(row) for row in rows)

    async def complete(self, job_id: str, **kwargs) -> CanaryJob:
        return await self._terminal(job_id, status=CanaryJobStatus.COMPLETED, **kwargs)

    async def reschedule(self, job_id: str, **kwargs) -> CanaryJob:
        async with self._session_factory() as session, session.begin():
            row = await self._leased_row(session, job_id, kwargs["worker_id"])
            row.status = CanaryJobStatus.PENDING.value
            row.due_at = _aware(kwargs["due_at"])
            row.lease_owner = None
            row.lease_until = None
            row.assessment_id = kwargs["assessment_id"]
            row.last_error_code = kwargs["error_code"]
            row.updated_at = _aware(kwargs["now"])
            await session.flush()
            return _stored(row)

    async def fail(self, job_id: str, **kwargs) -> CanaryJob:
        return await self._terminal(job_id, status=CanaryJobStatus.FAILED, **kwargs)

    async def _terminal(
        self, job_id: str, *, status: CanaryJobStatus, **kwargs
    ) -> CanaryJob:
        async with self._session_factory() as session, session.begin():
            row = await self._leased_row(session, job_id, kwargs["worker_id"])
            row.status = status.value
            row.lease_owner = None
            row.lease_until = None
            row.assessment_id = kwargs["assessment_id"]
            row.rollback_receipt_id = kwargs.get("rollback_receipt_id")
            row.last_error_code = kwargs.get("error_code")
            row.updated_at = _aware(kwargs["now"])
            await session.flush()
            return _stored(row)

    async def _leased_row(
        self, session: AsyncSession, job_id: str, worker_id: str
    ) -> CanaryJobRow:
        row = await session.scalar(
            select(CanaryJobRow)
            .where(CanaryJobRow.job_id == job_id)
            .with_for_update()
        )
        if row is None:
            raise CanarySupervisionError("CANARY_JOB_NOT_FOUND")
        if row.status != CanaryJobStatus.LEASED.value or row.lease_owner != worker_id:
            raise CanarySupervisionError("CANARY_JOB_LEASE_MISMATCH")
        return row


@dataclass(frozen=True, slots=True)
class CanaryScheduler:
    jobs: CanaryJobStore
    supervisor: CanaryAlertingSupervisor
    environment: str
    worker_id: str
    lease_ttl: timedelta = timedelta(minutes=2)
    retry_delay: timedelta = timedelta(minutes=1)
    max_attempts: int = 3
    clock: Callable[[], datetime] | None = None

    def __post_init__(self) -> None:
        if not self.environment or not self.worker_id or self.worker_id.startswith("ai:"):
            raise CanarySupervisionError("CANARY_SCHEDULER_IDENTITY_INVALID")
        if self.lease_ttl.total_seconds() <= 0 or self.retry_delay.total_seconds() <= 0:
            raise CanarySupervisionError("CANARY_SCHEDULER_INTERVAL_INVALID")
        if (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or self.max_attempts < 1
        ):
            raise CanarySupervisionError("CANARY_SCHEDULER_MAX_ATTEMPTS_INVALID")

    async def run_scheduled_tick(self, *, limit: int = 100) -> CanarySchedulerReport:
        now = self._now()
        claimed = await self.jobs.claim_due(
            environment=self.environment,
            worker_id=self.worker_id,
            now=now,
            lease_ttl=self.lease_ttl,
            limit=limit,
        )
        results = [await self._run(job) for job in claimed]
        return CanarySchedulerReport(tuple(results))

    async def _run(self, job: CanaryJob) -> CanaryJobResult:
        now = self._now()
        try:
            result = await self.supervisor.supervise(
                job.candidate,
                job.canary_receipt,
                rollback_control_id=job.rollback_control_id,
                idempotency_key=job.supervision_key,
            )
        except CanaryRollbackBlockedError as error:
            await self.jobs.fail(
                job.job_id,
                worker_id=self.worker_id,
                assessment_id=error.assessment.assessment_id,
                error_code=error.code,
                now=now,
            )
            return CanaryJobResult(
                job.job_id,
                CanaryJobOutcome.FAILED,
                error.assessment.assessment_id,
                None,
                error.code,
            )
        except Exception as error:
            code = _error_code(error)
            if job.attempts >= self.max_attempts:
                await self.jobs.fail(
                    job.job_id,
                    worker_id=self.worker_id,
                    assessment_id=None,
                    error_code=code,
                    now=now,
                )
                outcome = CanaryJobOutcome.FAILED
            else:
                await self.jobs.reschedule(
                    job.job_id,
                    worker_id=self.worker_id,
                    due_at=now + self.retry_delay,
                    assessment_id=None,
                    error_code=code,
                    now=now,
                )
                outcome = CanaryJobOutcome.RETRY
            return CanaryJobResult(job.job_id, outcome, None, None, code)
        if result.assessment.health is CanaryHealth.INSUFFICIENT_DATA:
            await self.jobs.reschedule(
                job.job_id,
                worker_id=self.worker_id,
                due_at=now + self.retry_delay,
                assessment_id=result.assessment.assessment_id,
                error_code=None,
                now=now,
            )
            return CanaryJobResult(
                job.job_id,
                CanaryJobOutcome.RESCHEDULED,
                result.assessment.assessment_id,
                None,
                None,
            )
        rollback_receipt_id = (
            None if result.rollback_receipt is None else result.rollback_receipt.receipt_id
        )
        await self.jobs.complete(
            job.job_id,
            worker_id=self.worker_id,
            assessment_id=result.assessment.assessment_id,
            rollback_receipt_id=rollback_receipt_id,
            now=now,
        )
        return CanaryJobResult(
            job.job_id,
            CanaryJobOutcome.COMPLETED,
            result.assessment.assessment_id,
            rollback_receipt_id,
            None,
        )

    def _now(self) -> datetime:
        return _aware(self.clock() if self.clock is not None else datetime.now(UTC))


def build_canary_job(
    *,
    candidate: ReleaseCandidate,
    canary_receipt: DeploymentReceipt,
    rollback_control_id: str | None,
    supervision_key: str,
    due_at: datetime,
    created_at: datetime,
) -> CanaryJob:
    payload = {
        "candidate_id": candidate.candidate_id,
        "environment": candidate.environment,
        "receipt_id": canary_receipt.receipt_id,
        "rollback_control_id": rollback_control_id,
        "supervision_key": supervision_key,
    }
    return CanaryJob(
        job_id=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        candidate=candidate,
        canary_receipt=canary_receipt,
        rollback_control_id=rollback_control_id,
        supervision_key=supervision_key,
        status=CanaryJobStatus.PENDING,
        due_at=_aware(due_at),
        attempts=0,
        lease_owner=None,
        lease_until=None,
        assessment_id=None,
        rollback_receipt_id=None,
        last_error_code=None,
        created_at=_aware(created_at),
        updated_at=_aware(created_at),
    )


def _validate_job(job: CanaryJob) -> None:
    if not isinstance(job.candidate, ReleaseCandidate) or not isinstance(
        job.canary_receipt, DeploymentReceipt
    ):
        raise CanarySupervisionError("CANARY_JOB_SNAPSHOT_REQUIRED")
    if (
        job.candidate.environment != job.canary_receipt.environment
        or job.candidate.candidate_id != job.canary_receipt.candidate_id
    ):
        raise CanarySupervisionError("CANARY_JOB_SCOPE_MISMATCH")
    if job.candidate.status is not ReleaseCandidateStatus.APPROVED:
        raise CanarySupervisionError("CANARY_JOB_CANDIDATE_NOT_APPROVED")
    if (
        job.canary_receipt.operation is not DeploymentOperation.APPLY
        or job.canary_receipt.phase is not DeploymentPhase.CANARY
    ):
        raise CanarySupervisionError("CANARY_JOB_RECEIPT_INVALID")
    if not job.job_id or not job.supervision_key:
        raise CanarySupervisionError("CANARY_JOB_IDENTITY_REQUIRED")
    _aware(job.due_at)
    _aware(job.created_at)
    _aware(job.updated_at)
    if job.attempts < 0:
        raise CanarySupervisionError("CANARY_JOB_ATTEMPTS_INVALID")
    if job.status is CanaryJobStatus.LEASED:
        if not job.lease_owner or job.lease_until is None:
            raise CanarySupervisionError("CANARY_JOB_LEASE_REQUIRED")
        _aware(job.lease_until)
    elif job.lease_owner is not None or job.lease_until is not None:
        raise CanarySupervisionError("CANARY_JOB_LEASE_STATE_INVALID")


def _validate_claim(
    environment: str,
    worker_id: str,
    now: datetime,
    lease_ttl: timedelta,
    limit: int,
) -> None:
    if not environment or not worker_id or worker_id.startswith("ai:"):
        raise CanarySupervisionError("CANARY_WORKER_IDENTITY_INVALID")
    _aware(now)
    if lease_ttl.total_seconds() <= 0:
        raise CanarySupervisionError("CANARY_LEASE_TTL_INVALID")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 0 <= limit <= 1000:
        raise CanarySupervisionError("CANARY_JOB_LIMIT_INVALID")


def _same_job_request(left: CanaryJob, right: CanaryJob) -> bool:
    return (
        left.job_id == right.job_id
        and left.candidate == right.candidate
        and left.canary_receipt == right.canary_receipt
        and left.rollback_control_id == right.rollback_control_id
        and left.supervision_key == right.supervision_key
        and left.due_at == right.due_at
        and left.created_at == right.created_at
    )


def _row(job: CanaryJob) -> CanaryJobRow:
    return CanaryJobRow(
        job_id=job.job_id,
        environment=job.candidate.environment,
        candidate_id=job.candidate.candidate_id,
        candidate_snapshot=_candidate_payload(job.candidate),
        receipt_id=job.canary_receipt.receipt_id,
        receipt_snapshot=_receipt_payload(job.canary_receipt),
        rollback_control_id=job.rollback_control_id,
        supervision_key=job.supervision_key,
        status=job.status.value,
        due_at=job.due_at,
        attempts=job.attempts,
        lease_owner=job.lease_owner,
        lease_until=job.lease_until,
        assessment_id=job.assessment_id,
        rollback_receipt_id=job.rollback_receipt_id,
        last_error_code=job.last_error_code,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _stored(row: CanaryJobRow) -> CanaryJob:
    try:
        status = CanaryJobStatus(row.status)
    except ValueError as exc:
        raise CanarySupervisionError("PERSISTED_CANARY_JOB_STATUS_INVALID") from exc
    return CanaryJob(
        job_id=row.job_id,
        candidate=_candidate_from_payload(row.candidate_snapshot),
        canary_receipt=_receipt_from_payload(row.receipt_snapshot),
        rollback_control_id=row.rollback_control_id,
        supervision_key=row.supervision_key,
        status=status,
        due_at=_db_time(row.due_at),
        attempts=row.attempts,
        lease_owner=row.lease_owner,
        lease_until=None if row.lease_until is None else _db_time(row.lease_until),
        assessment_id=row.assessment_id,
        rollback_receipt_id=row.rollback_receipt_id,
        last_error_code=row.last_error_code,
        created_at=_db_time(row.created_at),
        updated_at=_db_time(row.updated_at),
    )


def _candidate_payload(candidate: ReleaseCandidate) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "environment": candidate.environment,
        "decision_id": candidate.decision_id,
        "provider_id": candidate.provider_id,
        "model": candidate.model,
        "model_version": candidate.model_version,
        "report_ref": candidate.report_ref,
        "status": candidate.status.value,
        "last_control_id": candidate.last_control_id,
        "rollback_target_candidate_id": candidate.rollback_target_candidate_id,
        "registered_at": candidate.registered_at.isoformat(),
        "updated_at": candidate.updated_at.isoformat(),
    }


def _receipt_payload(receipt: DeploymentReceipt) -> dict[str, object]:
    return {
        "receipt_id": receipt.receipt_id,
        "operation": receipt.operation.value,
        "phase": receipt.phase.value,
        "idempotency_key": receipt.idempotency_key,
        "candidate_id": receipt.candidate_id,
        "environment": receipt.environment,
        "control_id": receipt.control_id,
        "actor_id": receipt.actor_id,
        "rollout_percent": receipt.rollout_percent,
        "external_ref": receipt.external_ref,
        "created_at": receipt.created_at.isoformat(),
    }


def _candidate_from_payload(payload: dict[str, object]) -> ReleaseCandidate:
    return ReleaseCandidate(
        candidate_id=_string(payload, "candidate_id"),
        environment=_string(payload, "environment"),
        decision_id=_string(payload, "decision_id"),
        provider_id=_string(payload, "provider_id"),
        model=_string(payload, "model"),
        model_version=_string(payload, "model_version"),
        report_ref=_string(payload, "report_ref"),
        status=ReleaseCandidateStatus(_string(payload, "status")),
        last_control_id=cast(str | None, payload.get("last_control_id")),
        rollback_target_candidate_id=cast(
            str | None, payload.get("rollback_target_candidate_id")
        ),
        registered_at=datetime.fromisoformat(_string(payload, "registered_at")),
        updated_at=datetime.fromisoformat(_string(payload, "updated_at")),
    )


def _receipt_from_payload(payload: dict[str, object]) -> DeploymentReceipt:
    return DeploymentReceipt(
        receipt_id=_string(payload, "receipt_id"),
        operation=DeploymentOperation(_string(payload, "operation")),
        phase=DeploymentPhase(_string(payload, "phase")),
        idempotency_key=_string(payload, "idempotency_key"),
        candidate_id=_string(payload, "candidate_id"),
        environment=_string(payload, "environment"),
        control_id=_string(payload, "control_id"),
        actor_id=_string(payload, "actor_id"),
        rollout_percent=_integer(payload, "rollout_percent"),
        external_ref=_string(payload, "external_ref"),
        created_at=datetime.fromisoformat(_string(payload, "created_at")),
    )


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise CanarySupervisionError("PERSISTED_CANARY_JOB_SNAPSHOT_INVALID")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise CanarySupervisionError("PERSISTED_CANARY_JOB_SNAPSHOT_INVALID")
    return value


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanarySupervisionError("CANARY_JOB_TIME_MUST_BE_AWARE")
    return value


def _db_time(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _error_code(error: Exception) -> str:
    if error.args and isinstance(error.args[0], str) and error.args[0].strip():
        return error.args[0][:128]
    return type(error).__name__.upper()[:128]


__all__ = [
    "CanaryJob",
    "CanaryJobOutcome",
    "CanaryJobResult",
    "CanaryJobRow",
    "CanaryJobStatus",
    "CanaryJobStore",
    "CanaryScheduler",
    "CanarySchedulerBase",
    "CanarySchedulerReport",
    "InMemoryCanaryJobStore",
    "SqlAlchemyCanaryJobStore",
    "build_canary_job",
]
