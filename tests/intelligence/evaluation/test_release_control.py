from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.evaluation.release_control import (
    InMemoryReleaseControlStore,
    ReleaseControlBase,
    ReleaseControlError,
    SqlAlchemyReleaseControlStore,
)
from backend.intelligence.evaluation.release_gate import ReleaseDecision


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ReleaseControlBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _decision(*, status: str = "ADMITTED") -> ReleaseDecision:
    return ReleaseDecision(
        status=status,  # type: ignore[arg-type]
        candidate_id="candidate-a",
        provider_id="provider-a",
        model="model-a",
        model_version="v1",
        environment="staging",
        report_ref="benchmark:report-1",
        failures=(),
    )


class _SignatureVerifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        assert payload
        assert actor_id
        return signature == "valid-signature"


def _store() -> InMemoryReleaseControlStore:
    return InMemoryReleaseControlStore(signature_verifier=_SignatureVerifier())


@pytest.mark.asyncio
async def test_in_memory_approval_is_idempotent_and_rejects_ai_actor() -> None:
    store = InMemoryReleaseControlStore(
        signature_verifier=_SignatureVerifier(),
        clock=lambda: datetime(2026, 8, 30, tzinfo=UTC),
    )
    event = await store.approve(
        _decision(),
        actor_id="operator-1",
        idempotency_key="approve-1",
        reason="reviewed",
        signature="valid-signature",
    )
    assert event.kind == "APPROVAL"
    assert (
        await store.approve(
            _decision(),
            actor_id="operator-1",
            idempotency_key="approve-1",
            reason="reviewed",
            signature="valid-signature",
        )
        == event
    )
    with pytest.raises(ReleaseControlError, match="AI_ACTOR_NOT_ALLOWED"):
        await store.approve(
            _decision(),
            actor_id="ai:agent",
            idempotency_key="approve-2",
            reason="no",
            signature="valid-signature",
        )
    with pytest.raises(ReleaseControlError, match="SIGNATURE_INVALID"):
        await store.approve(
            _decision(),
            actor_id="operator-1",
            idempotency_key="approve-3",
            reason="tampered",
            signature="invalid-signature",
        )


@pytest.mark.asyncio
async def test_release_control_requires_admitted_and_distinct_rollback_target() -> None:
    store = _store()
    with pytest.raises(ReleaseControlError, match="MUST_BE_ADMITTED"):
        await store.approve(
            _decision(status="BLOCKED"),
            actor_id="operator-1",
            idempotency_key="x",
            reason="x",
            signature="valid-signature",
        )
    with pytest.raises(ReleaseControlError, match="TARGET_MUST_DIFFER"):
        await store.rollback(
            _decision(),
            target_candidate_id="candidate-a",
            actor_id="operator-1",
            idempotency_key="r",
            reason="r",
            signature="valid-signature",
        )
    with pytest.raises(ReleaseControlError, match="ROLLBACK_REQUIRES_APPROVAL"):
        await store.rollback(
            _decision(),
            target_candidate_id="candidate-previous",
            actor_id="operator-1",
            idempotency_key="r2",
            reason="r",
            signature="valid-signature",
        )


@pytest.mark.asyncio
async def test_sql_release_control_round_trips_and_lists_events(session_factory) -> None:
    timestamp = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)
    async with session_factory() as session:
        store = SqlAlchemyReleaseControlStore(
            session, signature_verifier=_SignatureVerifier(), clock=lambda: timestamp
        )
        approval = await store.approve(
            _decision(),
            actor_id="operator-1",
            idempotency_key="approve-1",
            reason="reviewed",
            signature="valid-signature",
        )
        rollback = await store.rollback(
            _decision(),
            target_candidate_id="candidate-previous",
            actor_id="operator-1",
            idempotency_key="rollback-1",
            reason="incident",
            signature="valid-signature",
        )
        rows = await store.list_events(environment="staging")
        await session.commit()
    assert set(rows) == {approval, rollback}
    assert rollback.target_candidate_id == "candidate-previous"
