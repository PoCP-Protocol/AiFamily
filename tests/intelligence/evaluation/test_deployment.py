from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.evaluation.deployment import (
    DeploymentBase,
    DeploymentError,
    DeploymentPhase,
    DeploymentResult,
    InMemoryDeploymentReceiptStore,
    ReleaseDeploymentService,
    SqlAlchemyDeploymentReceiptStore,
)
from backend.intelligence.evaluation.release_catalog import (
    InMemoryReleaseCandidateCatalog,
)
from backend.intelligence.evaluation.release_control import (
    InMemoryReleaseControlStore,
)
from backend.intelligence.evaluation.release_gate import ReleaseDecision
from backend.intelligence.observability import InMemoryTelemetrySink


class _SignatureVerifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        return bool(payload and actor_id and signature == "valid-signature")


class _DeploymentPort:
    def __init__(self) -> None:
        self.apply_calls = 0
        self.rollback_calls = 0

    async def apply(self, candidate, control, *, phase, rollout_percent, idempotency_key):
        self.apply_calls += 1
        return DeploymentResult(external_ref=f"deploy:{idempotency_key}")

    async def rollback(self, candidate, control, *, idempotency_key):
        self.rollback_calls += 1
        return DeploymentResult(external_ref=f"rollback:{idempotency_key}")


class _FailingDeploymentPort(_DeploymentPort):
    async def apply(self, candidate, control, *, phase, rollout_percent, idempotency_key):
        self.apply_calls += 1
        raise DeploymentError("DEPLOYMENT_PLATFORM_5XX")


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(DeploymentBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _decision() -> ReleaseDecision:
    return ReleaseDecision(
        status="ADMITTED",
        candidate_id="candidate-a",
        provider_id="provider-a",
        model="model-a",
        model_version="v1",
        environment="staging",
        report_ref="benchmark:candidate-a",
        failures=(),
    )


async def _approved_candidate():
    decision = _decision()
    catalog = InMemoryReleaseCandidateCatalog()
    candidate = await catalog.register(decision)
    controls = InMemoryReleaseControlStore(signature_verifier=_SignatureVerifier())
    control = await controls.approve(
        decision,
        actor_id="operator-1",
        idempotency_key="approve:candidate-a",
        reason="reviewed",
        signature="valid-signature",
    )
    return candidate, await catalog.approve(control, human_actor="operator-1"), control


@pytest.mark.asyncio
async def test_deployment_service_calls_port_once_and_replays_receipt() -> None:
    _, candidate, control = await _approved_candidate()
    port = _DeploymentPort()
    service = ReleaseDeploymentService(port, InMemoryDeploymentReceiptStore())
    first = await service.apply(
        candidate,
        control,
        human_actor="operator-1",
        phase=DeploymentPhase.CANARY,
        rollout_percent=10,
        idempotency_key="deploy:candidate-a:canary",
    )
    second = await service.apply(
        candidate,
        control,
        human_actor="operator-1",
        phase=DeploymentPhase.CANARY,
        rollout_percent=10,
        idempotency_key="deploy:candidate-a:canary",
    )
    assert first == second
    assert port.apply_calls == 1


@pytest.mark.asyncio
async def test_deployment_service_records_metadata_only_telemetry() -> None:
    _, candidate, control = await _approved_candidate()
    telemetry = InMemoryTelemetrySink()
    service = ReleaseDeploymentService(
        _DeploymentPort(),
        InMemoryDeploymentReceiptStore(),
        telemetry_sink=telemetry,
    )

    await service.apply(
        candidate,
        control,
        human_actor="operator-1",
        phase=DeploymentPhase.CANARY,
        rollout_percent=10,
        idempotency_key="deploy:telemetry",
    )

    assert len(telemetry.spans) == 1
    span = telemetry.spans[0]
    assert span["name"] == "ai.release.deployment"
    assert span["status"] == "OK"
    assert span["attributes"] == {
        "provider_id": "provider-a",
        "model": "model-a",
        "model_version": "v1",
        "environment": "staging",
        "stage": "CANARY",
    }
    assert "deploy:telemetry" not in str(span)


@pytest.mark.asyncio
async def test_deployment_service_records_stable_error_code_without_exception_text() -> None:
    _, candidate, control = await _approved_candidate()
    telemetry = InMemoryTelemetrySink()
    service = ReleaseDeploymentService(
        _FailingDeploymentPort(),
        InMemoryDeploymentReceiptStore(),
        telemetry_sink=telemetry,
    )

    with pytest.raises(DeploymentError, match="DEPLOYMENT_PLATFORM_5XX"):
        await service.apply(
            candidate,
            control,
            human_actor="operator-1",
            phase=DeploymentPhase.ACTIVE,
            rollout_percent=100,
            idempotency_key="deploy:telemetry-error",
        )

    assert telemetry.spans[0]["status"] == "ERROR"
    assert telemetry.spans[0]["error_code"] == "DEPLOYMENT_PLATFORM_5XX"
    assert "telemetry-error" not in str(telemetry.spans[0])


@pytest.mark.asyncio
async def test_deployment_service_rejects_ai_or_unapproved_requests() -> None:
    decision = _decision()
    catalog = InMemoryReleaseCandidateCatalog()
    candidate = await catalog.register(decision)
    controls = InMemoryReleaseControlStore(signature_verifier=_SignatureVerifier())
    control = await controls.approve(
        decision,
        actor_id="operator-1",
        idempotency_key="approve:candidate-a",
        reason="reviewed",
        signature="valid-signature",
    )
    service = ReleaseDeploymentService(_DeploymentPort(), InMemoryDeploymentReceiptStore())
    with pytest.raises(DeploymentError, match="CANDIDATE_NOT_APPROVED"):
        await service.apply(
            candidate,
            control,
            human_actor="operator-1",
            phase=DeploymentPhase.ACTIVE,
            rollout_percent=100,
            idempotency_key="deploy:blocked",
        )
    approved = await catalog.approve(control, human_actor="operator-1")
    with pytest.raises(DeploymentError, match="HUMAN_ACTOR_MISMATCH"):
        await service.apply(
            approved,
            control,
            human_actor="ai:agent",
            phase=DeploymentPhase.ACTIVE,
            rollout_percent=100,
            idempotency_key="deploy:ai",
        )


@pytest.mark.asyncio
async def test_sql_receipt_store_round_trips(session_factory) -> None:
    _, candidate, control = await _approved_candidate()
    timestamp = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)
    async with session_factory() as session:
        store = SqlAlchemyDeploymentReceiptStore(session)
        service = ReleaseDeploymentService(_DeploymentPort(), store, clock=lambda: timestamp)
        receipt = await service.apply(
            candidate,
            control,
            human_actor="operator-1",
            phase=DeploymentPhase.ACTIVE,
            rollout_percent=100,
            idempotency_key="deploy:sql",
        )
        reread = await store.get("deploy:sql")
        await session.commit()
    assert reread == receipt
