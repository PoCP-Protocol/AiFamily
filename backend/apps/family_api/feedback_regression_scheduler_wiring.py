"""Production composition root for feedback regression scheduler ticks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.evaluation.feedback_regression import (
    FeedbackRegressionAdapter,
    FeedbackRegressionCaseSource,
    FeedbackRegressionWorker,
)
from backend.intelligence.evaluation.feedback_scheduler import (
    FeedbackRegressionJob,
    FeedbackRegressionJobStore,
    FeedbackRegressionScheduler,
    FeedbackSchedulerResult,
    SqlAlchemyFeedbackRegressionJobStore,
)


@dataclass(frozen=True, slots=True)
class FeedbackRegressionSchedule:
    interval: timedelta = timedelta(minutes=5)
    batch_limit: int = 20

    def __post_init__(self) -> None:
        if self.interval.total_seconds() <= 0:
            raise ValueError("FEEDBACK_SCHEDULE_INTERVAL_INVALID")
        if isinstance(self.batch_limit, bool) or not 1 <= self.batch_limit <= 500:
            raise ValueError("FEEDBACK_SCHEDULE_BATCH_LIMIT_INVALID")


@dataclass(frozen=True, slots=True)
class FeedbackRegressionSchedulerRuntime:
    jobs: FeedbackRegressionJobStore
    scheduler: FeedbackRegressionScheduler
    schedule: FeedbackRegressionSchedule = field(default_factory=FeedbackRegressionSchedule)

    async def enqueue(self, job: FeedbackRegressionJob) -> FeedbackRegressionJob:
        return await self.jobs.enqueue(job)

    async def get(self, job_id: str) -> FeedbackRegressionJob | None:
        return await self.jobs.get(job_id)

    async def run_scheduled_tick(
        self, *, now: datetime | None = None
    ) -> tuple[FeedbackSchedulerResult, ...]:
        """Run one bounded tick; deployment owns recurring invocation."""

        return await self.scheduler.run_once(
            now=now or datetime.now().astimezone(),
            limit=self.schedule.batch_limit,
        )


def build_sql_feedback_regression_scheduler(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    case_source: FeedbackRegressionCaseSource,
    ledger: object,
    adapter: FeedbackRegressionAdapter,
    worker_id: str,
    schedule: FeedbackRegressionSchedule | None = None,
    lease_ttl: timedelta = timedelta(minutes=2),
    retry_delay: timedelta = timedelta(minutes=5),
    max_attempts: int = 3,
) -> FeedbackRegressionSchedulerRuntime:
    """Build the durable scheduler without creating fallback dependencies."""

    if not isinstance(session_factory, async_sessionmaker):
        raise TypeError("session_factory must be an async_sessionmaker")
    if not callable(getattr(case_source, "load", None)):
        raise TypeError("case_source must expose async load")
    if not callable(getattr(ledger, "record_evaluation", None)):
        raise TypeError("ledger must expose record_evaluation")
    if not callable(adapter):
        raise TypeError("adapter must be callable")
    jobs = SqlAlchemyFeedbackRegressionJobStore(session_factory)
    worker = FeedbackRegressionWorker(case_source=case_source, ledger=ledger, adapter=adapter)
    scheduler = FeedbackRegressionScheduler(
        jobs=jobs,
        worker=worker,
        worker_id=worker_id,
        lease_ttl=lease_ttl,
        retry_delay=retry_delay,
        max_attempts=max_attempts,
    )
    return FeedbackRegressionSchedulerRuntime(
        jobs=jobs,
        scheduler=scheduler,
        schedule=schedule or FeedbackRegressionSchedule(),
    )


__all__ = [
    "FeedbackRegressionSchedule",
    "FeedbackRegressionSchedulerRuntime",
    "build_sql_feedback_regression_scheduler",
]
