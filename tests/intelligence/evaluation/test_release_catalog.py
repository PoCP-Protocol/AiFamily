from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.evaluation.release_catalog import (
    InMemoryReleaseCandidateCatalog,
    ReleaseCatalogBase,
    ReleaseCatalogError,
    SqlAlchemyReleaseCandidateCatalog,
)
from backend.intelligence.evaluation.release_control import (
    InMemoryReleaseControlStore,
    ReleaseControlEvent,
)
from backend.intelligence.evaluation.release_gate import ReleaseDecision
from backend.intelligence.evaluation.release_persistence import decision_fingerprint


class _SignatureVerifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        return bool(payload and actor_id and signature == "valid-signature")


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ReleaseCatalogBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _decision(*, candidate_id: str = "candidate-a", status: str = "ADMITTED") -> ReleaseDecision:
    return ReleaseDecision(
        status=status,  # type: ignore[arg-type]
        candidate_id=candidate_id,
        provider_id="provider-a",
        model="model-a",
        model_version="v1",
        environment="staging",
        report_ref=f"benchmark:{candidate_id}",
        failures=(),
    )


async def _approval(decision: ReleaseDecision):
    controls = InMemoryReleaseControlStore(signature_verifier=_SignatureVerifier())
    return await controls.approve(
        decision,
        actor_id="operator-1",
        idempotency_key=f"approve:{decision.candidate_id}",
        reason="reviewed",
        signature="valid-signature",
    )


@pytest.mark.asyncio
async def test_in_memory_catalog_requires_control_and_supports_rollback() -> None:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    catalog = InMemoryReleaseCandidateCatalog(clock=lambda: now)
    decision = _decision()
    candidate = await catalog.register(decision)
    assert candidate.status == "ADMITTED"
    controls = InMemoryReleaseControlStore(signature_verifier=_SignatureVerifier())
    approval = await controls.approve(
        decision,
        actor_id="operator-1",
        idempotency_key="approve:candidate-a",
        reason="reviewed",
        signature="valid-signature",
    )
    approved = await catalog.approve(approval, human_actor="operator-1")
    assert approved.status == "APPROVED"

    previous_decision = _decision(candidate_id="candidate-previous")
    await catalog.register(previous_decision)
    previous_approval = await controls.approve(
        previous_decision,
        actor_id="operator-1",
        idempotency_key="approve:candidate-previous",
        reason="reviewed",
        signature="valid-signature",
    )
    await catalog.approve(previous_approval, human_actor="operator-1")
    rollback = await controls.rollback(
        decision,
        target_candidate_id="candidate-previous",
        actor_id="operator-1",
        idempotency_key="rollback:candidate-a",
        reason="incident",
        signature="valid-signature",
    )
    rolled_back = await catalog.rollback(rollback, human_actor="operator-1")
    assert rolled_back.status == "ROLLED_BACK"
    assert rolled_back.rollback_target_candidate_id == "candidate-previous"


@pytest.mark.asyncio
async def test_catalog_rejects_unregistered_or_blocked_control() -> None:
    catalog = InMemoryReleaseCandidateCatalog()
    blocked = _decision(status="BLOCKED")
    await catalog.register(blocked)
    approval = ReleaseControlEvent(
        control_id="control-blocked",
        kind="APPROVAL",
        idempotency_key="approval-blocked",
        decision_id=decision_fingerprint(blocked),
        candidate_id=blocked.candidate_id,
        environment=blocked.environment,
        actor_id="operator-1",
        target_candidate_id=None,
        reason="reviewed",
        signature_ref="signature",
        signature_algorithm="external",
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    with pytest.raises(ReleaseCatalogError, match="NOT_ADMITTED"):
        await catalog.approve(approval, human_actor="operator-1")


@pytest.mark.asyncio
async def test_sql_catalog_round_trips_candidate_and_control(session_factory) -> None:
    decision = _decision()
    timestamp = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)
    async with session_factory() as session:
        catalog = SqlAlchemyReleaseCandidateCatalog(session, clock=lambda: timestamp)
        candidate = await catalog.register(decision)
        approval = await _approval(decision)
        approved = await catalog.approve(approval, human_actor="operator-1")
        await session.commit()
    assert candidate.status == "ADMITTED"
    assert approved.status == "APPROVED"
