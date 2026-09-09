"""Lease-based scheduling boundary for feedback regression batches.

The scheduler owns job lifecycle only.  It does not fetch family data, call a
model provider, or promote a release; ``FeedbackRegressionWorker`` remains the
only execution dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.experience.run_http import RunScope

from .feedback_regression import (
    FeedbackRegressionBatch,
    FeedbackRegressionWorker,
    FeedbackRegressionWorkerResult,
)


class FeedbackJobStatus(StrEnum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FeedbackSchedulerBase(DeclarativeBase):
    """Metadata boundary for restart-safe feedback regression jobs."""


class FeedbackRegressionJobRow(FeedbackSchedulerBase):
    __tablename__ = "ai_feedback_regression_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'LEASED', 'COMPLETED', 'FAILED')",
            name="ck_ai_feedback_regression_job_status",
        ),
    )

    job_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    batch_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    case_version: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(256), nullable=False)
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(256), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class FeedbackRegressionJob:
    job_id: str
    batch: FeedbackRegressionBatch
    due_at: datetime
    status: FeedbackJobStatus = FeedbackJobStatus.PENDING
    attempts: int = 0
    lease_owner: str | None = None
    lease_until: datetime | None = None
    last_error: str | None = None


class FeedbackRegressionJobStore(Protocol):
    async def enqueue(self, job: FeedbackRegressionJob) -> FeedbackRegressionJob: ...

    async def get(self, job_id: str) -> FeedbackRegressionJob | None: ...

    async def claim_due(
        self, *, worker_id: str, now: datetime, lease_ttl: timedelta, limit: int
    ) -> tuple[FeedbackRegressionJob, ...]: ...

    async def complete(
        self, job_id: str, *, worker_id: str, now: datetime
    ) -> FeedbackRegressionJob: ...

    async def retry(
        self,
        job_id: str,
        *,
        worker_id: str,
        due_at: datetime,
        error: str,
        now: datetime,
    ) -> FeedbackRegressionJob: ...


class InMemoryFeedbackRegressionJobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, FeedbackRegressionJob] = {}

    async def enqueue(self, job: FeedbackRegressionJob) -> FeedbackRegressionJob:
        existing = self.jobs.get(job.job_id)
        if existing is not None and existing.batch != job.batch:
            raise ValueError("FEEDBACK_JOB_CONFLICT")
        self.jobs[job.job_id] = existing or job
        return existing or job

    async def get(self, job_id: str) -> FeedbackRegressionJob | None:
        return self.jobs.get(job_id)

    async def claim_due(self, *, worker_id: str, now: datetime, lease_ttl: timedelta, limit: int):
        if not worker_id.strip() or lease_ttl <= timedelta(0) or limit < 1:
            raise ValueError("FEEDBACK_JOB_CLAIM_INVALID")
        now = _aware(now)
        eligible = [
            job
            for job in self.jobs.values()
            if job.due_at <= now
            and (
                job.status is FeedbackJobStatus.PENDING
                or job.status is FeedbackJobStatus.LEASED
                and job.lease_until is not None
                and _aware(job.lease_until) <= now
            )
        ]
        claimed = []
        for job in sorted(eligible, key=lambda item: (item.due_at, item.job_id))[:limit]:
            updated = replace(
                job,
                status=FeedbackJobStatus.LEASED,
                attempts=job.attempts + 1,
                lease_owner=worker_id,
                lease_until=now + lease_ttl,
            )
            self.jobs[job.job_id] = updated
            claimed.append(updated)
        return tuple(claimed)

    async def complete(self, job_id: str, *, worker_id: str, now: datetime):
        job = self._leased(job_id, worker_id)
        updated = replace(
            job, status=FeedbackJobStatus.COMPLETED, lease_owner=None, lease_until=None
        )
        self.jobs[job_id] = updated
        return updated

    async def retry(
        self, job_id: str, *, worker_id: str, due_at: datetime, error: str, now: datetime
    ):
        job = self._leased(job_id, worker_id)
        updated = replace(
            job,
            status=FeedbackJobStatus.PENDING,
            due_at=_aware(due_at),
            lease_owner=None,
            lease_until=None,
            last_error=error[:256],
        )
        self.jobs[job_id] = updated
        return updated

    def _leased(self, job_id: str, worker_id: str) -> FeedbackRegressionJob:
        job = self.jobs.get(job_id)
        if (
            job is None
            or job.status is not FeedbackJobStatus.LEASED
            or job.lease_owner != worker_id
        ):
            raise ValueError("FEEDBACK_JOB_LEASE_INVALID")
        return job


class SqlAlchemyFeedbackRegressionJobStore:
    """Session-per-operation durable queue with row-level lease claims."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def enqueue(self, job: FeedbackRegressionJob) -> FeedbackRegressionJob:
        now = _aware(datetime.now(UTC))
        async with self._session_factory() as session, session.begin():
            row = await session.get(FeedbackRegressionJobRow, job.job_id)
            if row is not None:
                existing = _stored(row)
                if existing.batch != job.batch:
                    raise ValueError("FEEDBACK_JOB_CONFLICT")
                return existing
            session.add(_row(job, now))
        return job

    async def get(self, job_id: str) -> FeedbackRegressionJob | None:
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("FEEDBACK_JOB_ID_REQUIRED")
        async with self._session_factory() as session:
            row = await session.get(FeedbackRegressionJobRow, job_id)
            return None if row is None else _stored(row)

    async def claim_due(
        self, *, worker_id: str, now: datetime, lease_ttl: timedelta, limit: int
    ) -> tuple[FeedbackRegressionJob, ...]:
        if not worker_id.strip() or lease_ttl <= timedelta(0) or limit < 1:
            raise ValueError("FEEDBACK_JOB_CLAIM_INVALID")
        now = _aware(now)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                select(FeedbackRegressionJobRow)
                .where(
                    FeedbackRegressionJobRow.due_at <= now,
                    or_(
                        FeedbackRegressionJobRow.status == FeedbackJobStatus.PENDING.value,
                        and_(
                            FeedbackRegressionJobRow.status == FeedbackJobStatus.LEASED.value,
                            FeedbackRegressionJobRow.lease_until <= now,
                        ),
                    ),
                )
                .order_by(FeedbackRegressionJobRow.due_at, FeedbackRegressionJobRow.job_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            rows = tuple(result.scalars())
            for row in rows:
                row.status = FeedbackJobStatus.LEASED.value
                row.attempts += 1
                row.lease_owner = worker_id
                row.lease_until = now + lease_ttl
                row.updated_at = now
            await session.flush()
            return tuple(_stored(row) for row in rows)

    async def complete(self, job_id: str, *, worker_id: str, now: datetime):
        async with self._session_factory() as session, session.begin():
            row = await self._leased_row(session, job_id, worker_id)
            row.status = FeedbackJobStatus.COMPLETED.value
            row.lease_owner = None
            row.lease_until = None
            row.updated_at = _aware(now)
            await session.flush()
            return _stored(row)

    async def retry(
        self, job_id: str, *, worker_id: str, due_at: datetime, error: str, now: datetime
    ):
        async with self._session_factory() as session, session.begin():
            row = await self._leased_row(session, job_id, worker_id)
            row.status = FeedbackJobStatus.PENDING.value
            row.due_at = _aware(due_at)
            row.lease_owner = None
            row.lease_until = None
            row.last_error = error[:256]
            row.updated_at = _aware(now)
            await session.flush()
            return _stored(row)

    async def _leased_row(self, session: AsyncSession, job_id: str, worker_id: str):
        row = await session.scalar(
            select(FeedbackRegressionJobRow)
            .where(FeedbackRegressionJobRow.job_id == job_id)
            .with_for_update()
        )
        if row is None:
            raise ValueError("FEEDBACK_JOB_NOT_FOUND")
        if row.status != FeedbackJobStatus.LEASED.value or row.lease_owner != worker_id:
            raise ValueError("FEEDBACK_JOB_LEASE_INVALID")
        return row


@dataclass(frozen=True, slots=True)
class FeedbackSchedulerResult:
    job_id: str
    status: FeedbackJobStatus
    worker_result: FeedbackRegressionWorkerResult | None
    error: str | None = None


class FeedbackRegressionScheduler:
    def __init__(
        self,
        *,
        jobs: FeedbackRegressionJobStore,
        worker: FeedbackRegressionWorker,
        worker_id: str,
        lease_ttl: timedelta = timedelta(minutes=2),
        retry_delay: timedelta = timedelta(minutes=5),
    ) -> None:
        if not worker_id.strip() or lease_ttl <= timedelta(0) or retry_delay <= timedelta(0):
            raise ValueError("FEEDBACK_SCHEDULER_CONFIG_INVALID")
        self.jobs = jobs
        self.worker = worker
        self.worker_id = worker_id
        self.lease_ttl = lease_ttl
        self.retry_delay = retry_delay

    async def run_once(
        self, *, now: datetime, limit: int = 10
    ) -> tuple[FeedbackSchedulerResult, ...]:
        now = _aware(now)
        claimed = await self.jobs.claim_due(
            worker_id=self.worker_id, now=now, lease_ttl=self.lease_ttl, limit=limit
        )
        results: list[FeedbackSchedulerResult] = []
        for job in claimed:
            try:
                result = await self.worker.run_once(job.batch)
            except Exception as error:
                await self.jobs.retry(
                    job.job_id,
                    worker_id=self.worker_id,
                    due_at=now + self.retry_delay,
                    error=type(error).__name__,
                    now=now,
                )
                results.append(
                    FeedbackSchedulerResult(
                        job.job_id, FeedbackJobStatus.PENDING, None, type(error).__name__
                    )
                )
            else:
                await self.jobs.complete(job.job_id, worker_id=self.worker_id, now=now)
                results.append(
                    FeedbackSchedulerResult(job.job_id, FeedbackJobStatus.COMPLETED, result)
                )
        return tuple(results)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _row(job: FeedbackRegressionJob, now: datetime) -> FeedbackRegressionJobRow:
    return FeedbackRegressionJobRow(
        job_id=job.job_id,
        batch_ref=job.batch.batch_ref,
        case_version=job.batch.case_version,
        run_id=job.batch.run_id,
        scope={
            "tenant_id": job.batch.scope.tenant_id,
            "family_id": job.batch.scope.family_id,
            "subject_ids": list(job.batch.scope.subject_ids),
        },
        status=job.status.value,
        due_at=_aware(job.due_at),
        attempts=job.attempts,
        lease_owner=job.lease_owner,
        lease_until=None if job.lease_until is None else _aware(job.lease_until),
        last_error=job.last_error,
        created_at=now,
        updated_at=now,
    )


def _stored(row: FeedbackRegressionJobRow) -> FeedbackRegressionJob:
    scope = row.scope
    batch = FeedbackRegressionBatch(
        batch_ref=row.batch_ref,
        case_version=row.case_version,
        run_id=row.run_id,
        scope=RunScope(
            tenant_id=scope["tenant_id"],
            family_id=scope["family_id"],
            subject_ids=tuple(scope["subject_ids"]),
        ),
    )
    return FeedbackRegressionJob(
        job_id=row.job_id,
        batch=batch,
        due_at=_aware(row.due_at),
        status=FeedbackJobStatus(row.status),
        attempts=row.attempts,
        lease_owner=row.lease_owner,
        lease_until=None if row.lease_until is None else _aware(row.lease_until),
        last_error=row.last_error,
    )


__all__ = [
    "FeedbackJobStatus",
    "FeedbackRegressionJob",
    "FeedbackRegressionJobStore",
    "FeedbackRegressionJobRow",
    "FeedbackSchedulerBase",
    "FeedbackRegressionScheduler",
    "FeedbackSchedulerResult",
    "InMemoryFeedbackRegressionJobStore",
    "SqlAlchemyFeedbackRegressionJobStore",
]
