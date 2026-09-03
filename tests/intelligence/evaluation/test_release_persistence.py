from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.evaluation.release_gate import ReleaseDecision
from backend.intelligence.evaluation.release_persistence import (
    InMemoryReleaseDecisionSink,
    ReleaseDecisionPersistenceBase,
    ReleaseDecisionPersistenceError,
    SqlAlchemyReleaseDecisionSink,
    decision_fingerprint,
)
from backend.intelligence.evaluation.release_service import ReleaseAdmissionService


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ReleaseDecisionPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _decision(*, status: str = "ADMITTED", failures: tuple[str, ...] = ()) -> ReleaseDecision:
    return ReleaseDecision(
        status=status,  # type: ignore[arg-type]
        candidate_id="candidate-a",
        provider_id="provider-a",
        model="model-a",
        model_version="v1",
        environment="staging",
        report_ref="benchmark:report-1",
        failures=failures,
    )


@pytest.mark.asyncio
async def test_in_memory_release_sink_is_idempotent() -> None:
    sink = InMemoryReleaseDecisionSink()
    decision = _decision()

    first = await sink.append(decision)
    second = await sink.append(decision)

    assert first == second == decision
    assert len(sink.decisions) == 1
    assert len(decision_fingerprint(decision)) == 64


@pytest.mark.asyncio
async def test_sql_release_sink_round_trips_metadata_only(session_factory) -> None:
    evaluated_at = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)
    decision = _decision(status="BLOCKED", failures=("safety_below_min", "cost_missing"))
    async with session_factory() as session:
        sink = SqlAlchemyReleaseDecisionSink(session, clock=lambda: evaluated_at)
        await sink.append(decision)
        await sink.append(decision)
        rows = await sink.list_decisions(candidate_id="candidate-a", environment="staging")
        await session.commit()

    assert rows == (decision,)
    assert rows[0].failures == ("safety_below_min", "cost_missing")


@pytest.mark.asyncio
async def test_sql_release_sink_rejects_naive_clock(session_factory) -> None:
    async with session_factory() as session:
        sink = SqlAlchemyReleaseDecisionSink(session, clock=lambda: datetime(2026, 8, 30))
        with pytest.raises(ReleaseDecisionPersistenceError, match="timezone-aware"):
            await sink.append(_decision())


@pytest.mark.asyncio
async def test_release_admission_service_records_gate_result() -> None:
    class StubGate:
        def evaluate(self, **kwargs):
            assert kwargs["environment"] == "production"
            return _decision()

    sink = InMemoryReleaseDecisionSink()
    service = ReleaseAdmissionService(gate=StubGate(), sink=sink)  # type: ignore[arg-type]
    result = await service.evaluate_and_record(
        report=object(),  # type: ignore[arg-type]
        provider_registry=object(),  # type: ignore[arg-type]
        environment="production",
    )

    assert result.status == "ADMITTED"
    assert sink.decisions == [result]
