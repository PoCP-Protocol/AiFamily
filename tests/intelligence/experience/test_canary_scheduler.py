from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.evaluation.deployment import (
    DeploymentOperation,
    DeploymentPhase,
    DeploymentReceipt,
)
from backend.intelligence.evaluation.release_catalog import (
    ReleaseCandidate,
    ReleaseCandidateStatus,
)
from backend.intelligence.experience.canary_scheduler import (
    CanaryJobOutcome,
    CanaryJobStatus,
    CanaryScheduler,
    CanarySchedulerBase,
    InMemoryCanaryJobStore,
    SqlAlchemyCanaryJobStore,
    build_canary_job,
)
from backend.intelligence.experience.canary_supervision import (
    CanaryHealth,
    CanaryObservation,
    CanaryRollbackBlockedError,
    CanarySloPolicy,
    CanarySupervisionResult,
    assess_canary,
)

NOW = datetime(2026, 8, 31, 15, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(CanarySchedulerBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _candidate(environment: str = "staging") -> ReleaseCandidate:
    return ReleaseCandidate(
        candidate_id="family-experience:candidate-a",
        environment=environment,
        decision_id="d" * 64,
        provider_id="provider-a",
        model="multimodal-a",
        model_version="2026-08",
        report_ref="benchmark:a",
        status=ReleaseCandidateStatus.APPROVED,
        last_control_id="approval-control",
        rollback_target_candidate_id=None,
        registered_at=NOW,
        updated_at=NOW,
    )


def _receipt(environment: str = "staging") -> DeploymentReceipt:
    return DeploymentReceipt(
        receipt_id="canary-receipt",
        operation=DeploymentOperation.APPLY,
        phase=DeploymentPhase.CANARY,
        idempotency_key=f"deploy:{environment}",
        candidate_id=_candidate(environment).candidate_id,
        environment=environment,
        control_id="approval-control",
        actor_id="operator-1",
        rollout_percent=5,
        external_ref=f"external:{environment}",
        created_at=NOW,
    )


def _job(environment: str = "staging"):
    return build_canary_job(
        candidate=_candidate(environment),
        canary_receipt=_receipt(environment),
        rollback_control_id="rollback-control",
        supervision_key=f"supervise:{environment}:canary-a",
        due_at=NOW,
        created_at=NOW,
    )


def _assessment(health: CanaryHealth, environment: str = "staging"):
    kwargs = {
        "request_count": 200,
        "error_rate": 0.0,
        "p95_latency_ms": 500,
        "minor_safety_violation_count": 0,
    }
    if health is CanaryHealth.INSUFFICIENT_DATA:
        kwargs["request_count"] = 1
    elif health is CanaryHealth.BREACHED:
        kwargs["minor_safety_violation_count"] = 1
    observation = CanaryObservation(
        observation_id=f"observation:{health.value}",
        receipt_id="canary-receipt",
        candidate_id=_candidate(environment).candidate_id,
        environment=environment,
        observed_at=NOW,
        window_seconds=300,
        request_count=kwargs["request_count"],
        error_rate=kwargs["error_rate"],
        p95_latency_ms=kwargs["p95_latency_ms"],
        safety_violation_count=0,
        minor_safety_violation_count=kwargs["minor_safety_violation_count"],
    )
    return assess_canary(
        observation,
        CanarySloPolicy("canary.v1", 100, 0.02, 1200, 3600),
        evaluated_at=NOW,
    )


class _Supervisor:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    async def supervise(self, candidate, receipt, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_in_memory_lease_blocks_second_worker_until_expiry() -> None:
    store = InMemoryCanaryJobStore()
    job = await store.enqueue(_job())
    first = await store.claim_due(
        environment="staging",
        worker_id="worker-a",
        now=NOW,
        lease_ttl=timedelta(minutes=2),
        limit=10,
    )
    blocked = await store.claim_due(
        environment="staging",
        worker_id="worker-b",
        now=NOW + timedelta(minutes=1),
        lease_ttl=timedelta(minutes=2),
        limit=10,
    )
    takeover = await store.claim_due(
        environment="staging",
        worker_id="worker-b",
        now=NOW + timedelta(minutes=3),
        lease_ttl=timedelta(minutes=2),
        limit=10,
    )

    assert first[0].job_id == job.job_id
    assert blocked == ()
    assert takeover[0].lease_owner == "worker-b"
    assert takeover[0].attempts == 2


@pytest.mark.asyncio
async def test_sql_queue_commits_lease_and_terminal_state_across_sessions(
    session_factory,
) -> None:
    store = SqlAlchemyCanaryJobStore(session_factory)
    job = await store.enqueue(_job())
    claimed = await store.claim_due(
        environment="staging",
        worker_id="worker-a",
        now=NOW,
        lease_ttl=timedelta(minutes=2),
        limit=1,
    )
    assert claimed[0].status is CanaryJobStatus.LEASED
    assert (
        await store.claim_due(
            environment="staging",
            worker_id="worker-b",
            now=NOW + timedelta(minutes=1),
            lease_ttl=timedelta(minutes=2),
            limit=1,
        )
        == ()
    )
    completed = await store.complete(
        job.job_id,
        worker_id="worker-a",
        assessment_id="assessment-a",
        rollback_receipt_id=None,
        now=NOW + timedelta(minutes=1),
    )
    assert completed.status is CanaryJobStatus.COMPLETED
    assert completed.lease_owner is None


@pytest.mark.asyncio
async def test_scheduler_completes_healthy_job() -> None:
    jobs = InMemoryCanaryJobStore()
    job = await jobs.enqueue(_job())
    result = CanarySupervisionResult(_assessment(CanaryHealth.HEALTHY), None)
    scheduler = CanaryScheduler(
        jobs=jobs,
        supervisor=_Supervisor((result,)),  # type: ignore[arg-type]
        environment="staging",
        worker_id="worker-a",
        clock=lambda: NOW,
    )
    report = await scheduler.run_scheduled_tick()

    assert report.results[0].outcome is CanaryJobOutcome.COMPLETED
    assert jobs.jobs[job.job_id].status is CanaryJobStatus.COMPLETED


@pytest.mark.asyncio
async def test_scheduler_reschedules_insufficient_evidence_without_failure() -> None:
    jobs = InMemoryCanaryJobStore()
    job = await jobs.enqueue(_job())
    result = CanarySupervisionResult(_assessment(CanaryHealth.INSUFFICIENT_DATA), None)
    scheduler = CanaryScheduler(
        jobs=jobs,
        supervisor=_Supervisor((result,)),  # type: ignore[arg-type]
        environment="staging",
        worker_id="worker-a",
        retry_delay=timedelta(minutes=5),
        clock=lambda: NOW,
    )
    report = await scheduler.run_scheduled_tick()

    assert report.results[0].outcome is CanaryJobOutcome.RESCHEDULED
    assert jobs.jobs[job.job_id].status is CanaryJobStatus.PENDING
    assert jobs.jobs[job.job_id].due_at == NOW + timedelta(minutes=5)
    assert jobs.jobs[job.job_id].last_error_code is None


@pytest.mark.asyncio
async def test_scheduler_retries_transient_failure_then_completes() -> None:
    jobs = InMemoryCanaryJobStore()
    job = await jobs.enqueue(_job())
    result = CanarySupervisionResult(_assessment(CanaryHealth.HEALTHY), None)
    clock_values = iter((NOW, NOW, NOW + timedelta(minutes=1), NOW + timedelta(minutes=1)))
    supervisor = _Supervisor((RuntimeError("OBSERVATION_TIMEOUT"), result))
    scheduler = CanaryScheduler(
        jobs=jobs,
        supervisor=supervisor,  # type: ignore[arg-type]
        environment="staging",
        worker_id="worker-a",
        retry_delay=timedelta(minutes=1),
        clock=lambda: next(clock_values),
    )

    first = await scheduler.run_scheduled_tick()
    second = await scheduler.run_scheduled_tick()
    assert first.results[0].outcome is CanaryJobOutcome.RETRY
    assert second.results[0].outcome is CanaryJobOutcome.COMPLETED
    assert jobs.jobs[job.job_id].attempts == 2


@pytest.mark.asyncio
async def test_scheduler_marks_preauthorized_rollback_block_terminal() -> None:
    jobs = InMemoryCanaryJobStore()
    job = await jobs.enqueue(_job())
    assessment = _assessment(CanaryHealth.BREACHED)
    supervisor = _Supervisor(
        (CanaryRollbackBlockedError("ROLLBACK_CONTROL_EXPIRED", assessment),)
    )
    scheduler = CanaryScheduler(
        jobs=jobs,
        supervisor=supervisor,  # type: ignore[arg-type]
        environment="staging",
        worker_id="worker-a",
        clock=lambda: NOW,
    )
    report = await scheduler.run_scheduled_tick()

    assert report.results[0].outcome is CanaryJobOutcome.FAILED
    stored = jobs.jobs[job.job_id]
    assert stored.status is CanaryJobStatus.FAILED
    assert stored.assessment_id == assessment.assessment_id
    assert stored.last_error_code == "ROLLBACK_CONTROL_EXPIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["development", "test", "staging", "production"])
async def test_scheduler_tick_has_same_contract_in_every_environment(environment: str) -> None:
    jobs = InMemoryCanaryJobStore()
    job = await jobs.enqueue(_job(environment))
    result = CanarySupervisionResult(_assessment(CanaryHealth.HEALTHY, environment), None)
    scheduler = CanaryScheduler(
        jobs=jobs,
        supervisor=_Supervisor((result,)),  # type: ignore[arg-type]
        environment=environment,
        worker_id="canary-worker",
        clock=lambda: NOW,
    )

    report = await scheduler.run_scheduled_tick()
    assert report.results[0].outcome is CanaryJobOutcome.COMPLETED
    assert jobs.jobs[job.job_id].status is CanaryJobStatus.COMPLETED
    assert await jobs.enqueue(_job(environment)) == jobs.jobs[job.job_id]
