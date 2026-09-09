"""Lease-based scheduling boundary for feedback regression batches.

The scheduler owns job lifecycle only.  It does not fetch family data, call a
model provider, or promote a release; ``FeedbackRegressionWorker`` remains the
only execution dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

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


__all__ = [
    "FeedbackJobStatus",
    "FeedbackRegressionJob",
    "FeedbackRegressionJobStore",
    "FeedbackRegressionScheduler",
    "FeedbackSchedulerResult",
    "InMemoryFeedbackRegressionJobStore",
]
