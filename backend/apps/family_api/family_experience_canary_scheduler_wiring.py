"""SQL composition root for bounded family-experience canary scheduler ticks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.family_experience_release_wiring import (
    FAMILY_EXPERIENCE_RELEASE_ENVIRONMENTS,
)
from backend.intelligence.experience.canary_alerts import (
    CanaryAlertingSupervisor,
    SessionPerCallCanaryAlertStore,
)
from backend.intelligence.experience.canary_scheduler import (
    CanaryJob,
    CanaryScheduler,
    CanarySchedulerReport,
    SqlAlchemyCanaryJobStore,
)
from backend.intelligence.experience.canary_supervision import (
    CanaryObservationPort,
    CanarySloPolicy,
    CanarySupervisionError,
    FamilyExperienceCanarySupervisor,
    SessionPerCallCanaryAssessmentStore,
    SessionPerCallRollbackControlReader,
)
from backend.intelligence.experience.release_bundle_deployment import (
    FamilyExperienceReleaseDeploymentService,
)


@dataclass(frozen=True, slots=True)
class CanarySchedulerSchedule:
    interval: timedelta = timedelta(minutes=1)
    batch_limit: int = 100

    def __post_init__(self) -> None:
        if self.interval.total_seconds() <= 0:
            raise CanarySupervisionError("CANARY_SCHEDULE_INTERVAL_INVALID")
        if (
            not isinstance(self.batch_limit, int)
            or isinstance(self.batch_limit, bool)
            or not 1 <= self.batch_limit <= 1000
        ):
            raise CanarySupervisionError("CANARY_SCHEDULE_BATCH_LIMIT_INVALID")


@dataclass(frozen=True, slots=True)
class FamilyExperienceCanarySchedulerRuntime:
    jobs: SqlAlchemyCanaryJobStore
    scheduler: CanaryScheduler
    schedule: CanarySchedulerSchedule = field(default_factory=CanarySchedulerSchedule)

    async def enqueue(self, job: CanaryJob) -> CanaryJob:
        if job.candidate.environment != self.scheduler.environment:
            raise CanarySupervisionError("CANARY_JOB_ENVIRONMENT_MISMATCH")
        return await self.jobs.enqueue(job)

    async def run_scheduled_tick(self) -> CanarySchedulerReport:
        """Bounded tick; deployment owns recurring invocation and never sleeps here."""

        return await self.scheduler.run_scheduled_tick(limit=self.schedule.batch_limit)

    async def job(self, job_id: str) -> CanaryJob | None:
        return await self.jobs.get(job_id)


def build_sql_family_experience_canary_scheduler(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    environment: str,
    worker_id: str,
    observation_port: CanaryObservationPort,
    deployment: FamilyExperienceReleaseDeploymentService,
    policy: CanarySloPolicy,
    schedule: CanarySchedulerSchedule | None = None,
    lease_ttl: timedelta = timedelta(minutes=2),
    retry_delay: timedelta = timedelta(minutes=1),
    max_attempts: int = 3,
    clock: Callable[[], datetime] | None = None,
) -> FamilyExperienceCanarySchedulerRuntime:
    if not isinstance(session_factory, async_sessionmaker):
        raise TypeError("session_factory must be an async_sessionmaker")
    if environment not in FAMILY_EXPERIENCE_RELEASE_ENVIRONMENTS:
        raise CanarySupervisionError("CANARY_RUNTIME_ENVIRONMENT_INVALID")
    assessments = SessionPerCallCanaryAssessmentStore(session_factory)
    alerts = SessionPerCallCanaryAlertStore(session_factory)
    supervisor = FamilyExperienceCanarySupervisor(
        observation_port=observation_port,
        rollback_controls=SessionPerCallRollbackControlReader(session_factory),
        deployment=deployment,
        assessments=assessments,
        policy=policy,
        clock=clock,
    )
    jobs = SqlAlchemyCanaryJobStore(session_factory)
    scheduler = CanaryScheduler(
        jobs=jobs,
        supervisor=CanaryAlertingSupervisor(supervisor, alerts, clock=clock),
        environment=environment,
        worker_id=worker_id,
        lease_ttl=lease_ttl,
        retry_delay=retry_delay,
        max_attempts=max_attempts,
        clock=clock,
    )
    return FamilyExperienceCanarySchedulerRuntime(
        jobs=jobs,
        scheduler=scheduler,
        schedule=schedule or CanarySchedulerSchedule(),
    )


__all__ = [
    "CanarySchedulerSchedule",
    "FamilyExperienceCanarySchedulerRuntime",
    "build_sql_family_experience_canary_scheduler",
]
