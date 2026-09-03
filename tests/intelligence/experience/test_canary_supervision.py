from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

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
from backend.intelligence.evaluation.release_control import (
    ReleaseControlBase,
    ReleaseControlEvent,
    SqlAlchemyReleaseControlStore,
)
from backend.intelligence.evaluation.release_gate import ReleaseDecision
from backend.intelligence.experience.canary_supervision import (
    CanaryAssessmentBase,
    CanaryHealth,
    CanaryObservation,
    CanarySloPolicy,
    CanarySupervisionError,
    FamilyExperienceCanarySupervisor,
    InMemoryCanaryAssessmentStore,
    InMemoryRollbackControlReader,
    SessionPerCallRollbackControlReader,
    SqlAlchemyCanaryAssessmentStore,
    assess_canary,
)
from backend.intelligence.experience.release_bundle import FamilyExperienceReleaseBundle
from backend.intelligence.experience.release_bundle_deployment import (
    FamilyExperienceReleaseDeploymentService,
)
from backend.intelligence.experience.release_bundle_persistence import (
    InMemoryFamilyExperienceReleaseBundleStore,
)

NOW = datetime(2026, 8, 31, 11, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(CanaryAssessmentBase.metadata.create_all)
        await connection.run_sync(ReleaseControlBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


class _ObservationPort:
    def __init__(self, observation: CanaryObservation) -> None:
        self.observation = observation
        self.calls = 0

    async def observe(self, candidate, canary_receipt, *, idempotency_key):
        self.calls += 1
        return self.observation


class _DeploymentPort:
    def __init__(self) -> None:
        self.rollback_calls = 0

    async def apply(
        self, bundle, candidate, control, *, phase, rollout_percent, idempotency_key
    ):
        return DeploymentResult(external_ref="unused")

    async def rollback(self, bundle, candidate, control, *, idempotency_key):
        self.rollback_calls += 1
        return DeploymentResult(external_ref=f"rollback:{control.target_candidate_id}")


def _policy() -> CanarySloPolicy:
    return CanarySloPolicy(
        version="family-experience-canary.v1",
        min_request_count=100,
        max_error_rate=0.02,
        max_p95_latency_ms=1200,
        rollback_authorization_ttl_seconds=3600,
    )


def _candidate() -> ReleaseCandidate:
    return ReleaseCandidate(
        candidate_id="family-experience:candidate-a",
        environment="staging",
        decision_id="d" * 64,
        provider_id="provider-a",
        model="multimodal-a",
        model_version="2026-08",
        report_ref="benchmark:family-experience",
        status=ReleaseCandidateStatus.APPROVED,
        last_control_id="approval-control",
        rollback_target_candidate_id=None,
        registered_at=NOW,
        updated_at=NOW,
    )


def _bundle(candidate: ReleaseCandidate) -> FamilyExperienceReleaseBundle:
    return FamilyExperienceReleaseBundle(
        bundle_id="b" * 64,
        candidate_id=candidate.candidate_id,
        environment=candidate.environment,
        use_case="family_assistant_conversation",
        agent_id="parent_advisor",
        provider_id=candidate.provider_id,
        model=candidate.model,
        model_version=candidate.model_version,
        prompt_ref="family_assistant_v1",
        prompt_version="family-companion.v1",
        schema_ref="assistant_response_v1",
        schema_version="family-experience-draft.v1",
        safety_policy_version="minor-safety.v1",
        routing_policy_version="multimodal-routing.v1",
        rate_card_version="family-rate-card.v1",
        budget_policy_version="family-budget.v1",
        knowledge_refs=("knowledge:family-companion:v1",),
        data_class="MINOR_PERSONAL_DATA",
        report_ref=candidate.report_ref,
        decision_id=candidate.decision_id,
        control_id="approval-control",
        approval_signature_ref="approval-signature",
        approval_signature_algorithm="external-kms-v1",
        approved_by="operator-1",
        approved_at=NOW,
        asset_digest="a" * 64,
        human_gate_rule="REVIEW_REQUIRED",
    )


def _canary_receipt(candidate: ReleaseCandidate) -> DeploymentReceipt:
    return DeploymentReceipt(
        receipt_id="canary-receipt",
        operation=DeploymentOperation.APPLY,
        phase=DeploymentPhase.CANARY,
        idempotency_key="deploy:canary",
        candidate_id=candidate.candidate_id,
        environment=candidate.environment,
        control_id="approval-control",
        actor_id="operator-1",
        rollout_percent=5,
        external_ref="deployment:canary",
        created_at=NOW,
    )


def _observation(
    candidate: ReleaseCandidate,
    *,
    request_count: int = 200,
    error_rate: float = 0.0,
    latency: int | None = 500,
    safety: int = 0,
    minor_safety: int = 0,
) -> CanaryObservation:
    return CanaryObservation(
        observation_id="observation-1",
        receipt_id="canary-receipt",
        candidate_id=candidate.candidate_id,
        environment=candidate.environment,
        observed_at=NOW + timedelta(minutes=5),
        window_seconds=300,
        request_count=request_count,
        error_rate=error_rate,
        p95_latency_ms=latency,
        safety_violation_count=safety,
        minor_safety_violation_count=minor_safety,
    )


def _rollback_control(candidate: ReleaseCandidate) -> ReleaseControlEvent:
    return ReleaseControlEvent(
        control_id="rollback-control",
        kind="ROLLBACK",
        idempotency_key="authorize:canary-rollback",
        decision_id=candidate.decision_id,
        candidate_id=candidate.candidate_id,
        environment=candidate.environment,
        actor_id="operator-1",
        target_candidate_id="family-experience:previous",
        reason="pre-authorized when canary SLO is breached",
        signature_ref="rollback-signature",
        signature_algorithm="external-kms-v1",
        created_at=NOW + timedelta(minutes=1),
    )


def test_canary_assessment_waits_for_volume_but_safety_is_immediate() -> None:
    candidate = _candidate()
    insufficient = assess_canary(
        _observation(candidate, request_count=10),
        _policy(),
        evaluated_at=NOW + timedelta(minutes=5),
    )
    minor_breach = assess_canary(
        _observation(candidate, request_count=1, minor_safety=1),
        _policy(),
        evaluated_at=NOW + timedelta(minutes=5),
    )

    assert insufficient.health is CanaryHealth.INSUFFICIENT_DATA
    assert insufficient.reasons == ("request_count_below_minimum",)
    assert minor_breach.health is CanaryHealth.BREACHED
    assert minor_breach.reasons == ("minor_safety_violation",)


@pytest.mark.parametrize(
    ("error_rate", "latency", "health", "reasons"),
    [
        (0.0, 500, CanaryHealth.HEALTHY, ()),
        (0.03, 500, CanaryHealth.BREACHED, ("error_rate_above_maximum",)),
        (0.0, 1300, CanaryHealth.BREACHED, ("p95_latency_above_maximum",)),
        (0.0, None, CanaryHealth.BREACHED, ("p95_latency_missing",)),
    ],
)
def test_canary_assessment_is_deterministic(error_rate, latency, health, reasons) -> None:
    assessment = assess_canary(
        _observation(_candidate(), error_rate=error_rate, latency=latency),
        _policy(),
        evaluated_at=NOW + timedelta(minutes=5),
    )
    assert assessment.health is health
    assert assessment.reasons == reasons


@pytest.mark.asyncio
async def test_breach_executes_only_pre_authorized_human_rollback_once() -> None:
    candidate = _candidate()
    bundle_store = InMemoryFamilyExperienceReleaseBundleStore()
    await bundle_store.append(_bundle(candidate))
    deployment_port = _DeploymentPort()
    receipts = InMemoryDeploymentReceiptStore()
    control = _rollback_control(candidate)
    supervisor = FamilyExperienceCanarySupervisor(
        observation_port=_ObservationPort(_observation(candidate, minor_safety=1)),
        rollback_controls=InMemoryRollbackControlReader((control,)),
        deployment=FamilyExperienceReleaseDeploymentService(
            port=deployment_port,
            bundles=bundle_store,
            receipts=receipts,
            clock=lambda: NOW + timedelta(minutes=5),
        ),
        assessments=InMemoryCanaryAssessmentStore(),
        policy=_policy(),
        clock=lambda: NOW + timedelta(minutes=5),
    )

    first = await supervisor.supervise(
        candidate,
        _canary_receipt(candidate),
        rollback_control_id=control.control_id,
        idempotency_key="supervise:canary-1",
    )
    replay = await supervisor.supervise(
        candidate,
        _canary_receipt(candidate),
        rollback_control_id=control.control_id,
        idempotency_key="supervise:canary-1",
    )

    assert first.rollback_receipt == replay.rollback_receipt
    assert first.assessment.health is CanaryHealth.BREACHED
    assert first.rollback_receipt is not None
    assert first.rollback_receipt.actor_id == "operator-1"
    assert deployment_port.rollback_calls == 1


@pytest.mark.asyncio
async def test_healthy_canary_never_requires_or_executes_rollback() -> None:
    candidate = _candidate()
    bundle_store = InMemoryFamilyExperienceReleaseBundleStore()
    await bundle_store.append(_bundle(candidate))
    deployment_port = _DeploymentPort()
    supervisor = FamilyExperienceCanarySupervisor(
        observation_port=_ObservationPort(_observation(candidate)),
        rollback_controls=InMemoryRollbackControlReader(),
        deployment=FamilyExperienceReleaseDeploymentService(
            port=deployment_port,
            bundles=bundle_store,
            receipts=InMemoryDeploymentReceiptStore(),
        ),
        assessments=InMemoryCanaryAssessmentStore(),
        policy=_policy(),
        clock=lambda: NOW + timedelta(minutes=5),
    )

    result = await supervisor.supervise(
        candidate,
        _canary_receipt(candidate),
        rollback_control_id=None,
        idempotency_key="supervise:healthy",
    )
    assert result.assessment.health is CanaryHealth.HEALTHY
    assert result.rollback_receipt is None
    assert deployment_port.rollback_calls == 0


@pytest.mark.asyncio
async def test_breach_rejects_missing_ai_or_expired_rollback_control() -> None:
    candidate = _candidate()
    bundle_store = InMemoryFamilyExperienceReleaseBundleStore()
    await bundle_store.append(_bundle(candidate))
    deployment_port = _DeploymentPort()
    observation = _observation(candidate, error_rate=0.2)

    async def attempt(control: ReleaseControlEvent | None, expected: str) -> None:
        reader = InMemoryRollbackControlReader(() if control is None else (control,))
        supervisor = FamilyExperienceCanarySupervisor(
            observation_port=_ObservationPort(observation),
            rollback_controls=reader,
            deployment=FamilyExperienceReleaseDeploymentService(
                port=deployment_port,
                bundles=bundle_store,
                receipts=InMemoryDeploymentReceiptStore(),
            ),
            assessments=InMemoryCanaryAssessmentStore(),
            policy=_policy(),
            clock=lambda: observation.observed_at,
        )
        control_id = "missing" if control is None else control.control_id
        with pytest.raises(CanarySupervisionError, match=expected):
            await supervisor.supervise(
                candidate,
                _canary_receipt(candidate),
                rollback_control_id=control_id,
                idempotency_key=f"supervise:{expected}",
            )

    await attempt(None, "CONTROL_NOT_FOUND")
    await attempt(replace(_rollback_control(candidate), actor_id="ai:monitor"), "HUMAN_SIGNATURE")
    await attempt(
        replace(_rollback_control(candidate), created_at=NOW - timedelta(hours=2)),
        "CONTROL_EXPIRED",
    )
    assert deployment_port.rollback_calls == 0


@pytest.mark.asyncio
async def test_sql_assessment_ledger_round_trips_and_rejects_drift(session_factory) -> None:
    assessment = assess_canary(
        _observation(_candidate(), minor_safety=1),
        _policy(),
        evaluated_at=NOW + timedelta(minutes=5),
    )
    async with session_factory() as session:
        stored = await SqlAlchemyCanaryAssessmentStore(session).append(assessment)
        await session.commit()
    async with session_factory() as session:
        store = SqlAlchemyCanaryAssessmentStore(session)
        assert await store.get(assessment.assessment_id) == stored
        replay = replace(assessment, evaluated_at=NOW + timedelta(minutes=6))
        assert await store.append(replay) == stored
        changed = assess_canary(
            replace(_observation(_candidate(), minor_safety=1), error_rate=0.9),
            _policy(),
            evaluated_at=NOW + timedelta(minutes=5),
        )
        with pytest.raises(CanarySupervisionError, match="ASSESSMENT_CONFLICT"):
            await store.append(changed)


class _SignatureVerifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        return bool(payload and actor_id and signature == "valid-signature")


@pytest.mark.asyncio
async def test_session_per_call_reader_only_returns_verified_sql_control(
    session_factory,
) -> None:
    candidate = _candidate()
    decision = ReleaseDecision(
        status="ADMITTED",
        candidate_id=candidate.candidate_id,
        provider_id=candidate.provider_id,
        model=candidate.model,
        model_version=candidate.model_version,
        environment=candidate.environment,
        report_ref=candidate.report_ref,
        failures=(),
    )
    async with session_factory() as session:
        store = SqlAlchemyReleaseControlStore(
            session,
            signature_verifier=_SignatureVerifier(),
            clock=lambda: NOW + timedelta(minutes=1),
        )
        await store.approve(
            decision,
            actor_id="operator-1",
            idempotency_key="approve:sql-canary",
            reason="canary approved",
            signature="valid-signature",
        )
        rollback = await store.rollback(
            decision,
            target_candidate_id="family-experience:previous",
            actor_id="operator-1",
            idempotency_key="rollback:sql-canary",
            reason="pre-authorized SLO rollback",
            signature="valid-signature",
            signature_algorithm="external-kms-v1",
        )
        await session.commit()

    reader = SessionPerCallRollbackControlReader(session_factory)
    assert await reader.get(rollback.control_id) == rollback
    assert await reader.get("missing-control") is None
