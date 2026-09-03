from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.family_experience_canary_scheduler_wiring import (
    CanarySchedulerSchedule,
    build_sql_family_experience_canary_scheduler,
)
from backend.intelligence.evaluation.deployment import (
    DeploymentOperation,
    DeploymentPhase,
    DeploymentReceipt,
    DeploymentResult,
    InMemoryDeploymentReceiptStore,
)
from backend.intelligence.evaluation.release_catalog import (
    ReleaseCandidate,
    ReleaseCandidateStatus,
)
from backend.intelligence.evaluation.release_control import ReleaseControlBase
from backend.intelligence.experience.canary_alerts import CanaryAlertBase
from backend.intelligence.experience.canary_scheduler import (
    CanaryJobOutcome,
    CanaryJobStatus,
    CanarySchedulerBase,
    build_canary_job,
)
from backend.intelligence.experience.canary_supervision import (
    CanaryAssessmentBase,
    CanaryObservation,
    CanarySloPolicy,
)
from backend.intelligence.experience.release_bundle_deployment import (
    FamilyExperienceReleaseDeploymentService,
)
from backend.intelligence.experience.release_bundle_persistence import (
    InMemoryFamilyExperienceReleaseBundleStore,
)

NOW = datetime(2026, 8, 31, 16, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        for metadata in (
            CanarySchedulerBase.metadata,
            CanaryAssessmentBase.metadata,
            CanaryAlertBase.metadata,
            ReleaseControlBase.metadata,
        ):
            await connection.run_sync(metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


class _ObservationPort:
    async def observe(self, candidate, receipt, *, idempotency_key):
        return CanaryObservation(
            observation_id=f"observation:{candidate.environment}",
            receipt_id=receipt.receipt_id,
            candidate_id=candidate.candidate_id,
            environment=candidate.environment,
            observed_at=NOW,
            window_seconds=300,
            request_count=200,
            error_rate=0.0,
            p95_latency_ms=500,
            safety_violation_count=0,
            minor_safety_violation_count=0,
        )


class _DeploymentPort:
    async def apply(
        self, bundle, candidate, control, *, phase, rollout_percent, idempotency_key
    ):
        return DeploymentResult(external_ref="unused")

    async def rollback(self, bundle, candidate, control, *, idempotency_key):
        return DeploymentResult(external_ref="unused")


def _job(environment: str):
    candidate = ReleaseCandidate(
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
    receipt = DeploymentReceipt(
        receipt_id="canary-receipt",
        operation=DeploymentOperation.APPLY,
        phase=DeploymentPhase.CANARY,
        idempotency_key=f"deploy:{environment}",
        candidate_id=candidate.candidate_id,
        environment=environment,
        control_id="approval-control",
        actor_id="operator-1",
        rollout_percent=5,
        external_ref=f"external:{environment}",
        created_at=NOW,
    )
    return build_canary_job(
        candidate=candidate,
        canary_receipt=receipt,
        rollback_control_id=None,
        supervision_key=f"supervise:{environment}",
        due_at=NOW,
        created_at=NOW,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["development", "test", "staging", "production"])
async def test_sql_scheduler_runtime_has_same_bounded_tick_in_every_environment(
    session_factory,
    environment: str,
) -> None:
    runtime = build_sql_family_experience_canary_scheduler(
        session_factory=session_factory,
        environment=environment,
        worker_id="canary-worker",
        observation_port=_ObservationPort(),
        deployment=FamilyExperienceReleaseDeploymentService(
            port=_DeploymentPort(),
            bundles=InMemoryFamilyExperienceReleaseBundleStore(),
            receipts=InMemoryDeploymentReceiptStore(),
            clock=lambda: NOW,
        ),
        policy=CanarySloPolicy("canary.v1", 100, 0.02, 1200, 3600),
        schedule=CanarySchedulerSchedule(batch_limit=10),
        clock=lambda: NOW,
    )
    job = await runtime.enqueue(_job(environment))
    report = await runtime.run_scheduled_tick()
    stored = await runtime.job(job.job_id)

    assert report.claimed == 1
    assert report.results[0].outcome is CanaryJobOutcome.COMPLETED
    assert stored is not None
    assert stored.status is CanaryJobStatus.COMPLETED
    assert stored.assessment_id == report.results[0].assessment_id


@pytest.mark.asyncio
async def test_sql_scheduler_runtime_rejects_cross_environment_enqueue(
    session_factory,
) -> None:
    runtime = build_sql_family_experience_canary_scheduler(
        session_factory=session_factory,
        environment="production",
        worker_id="canary-worker",
        observation_port=_ObservationPort(),
        deployment=FamilyExperienceReleaseDeploymentService(
            port=_DeploymentPort(),
            bundles=InMemoryFamilyExperienceReleaseBundleStore(),
            receipts=InMemoryDeploymentReceiptStore(),
        ),
        policy=CanarySloPolicy("canary.v1", 100, 0.02, 1200, 3600),
    )
    with pytest.raises(ValueError, match="JOB_ENVIRONMENT_MISMATCH"):
        await runtime.enqueue(_job("test"))
