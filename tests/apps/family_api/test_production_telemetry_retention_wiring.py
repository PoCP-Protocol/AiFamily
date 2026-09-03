from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.production_telemetry_retention_wiring import (
    ProductionTelemetryRetentionRuntime,
)
from backend.intelligence.observability.persistence import (
    TelemetryPersistenceBase,
    TelemetrySpanRow,
)
from backend.intelligence.observability.retention import InMemoryTelemetryDeletionAudit

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(TelemetryPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _row(span_id: str, started_at: datetime) -> TelemetrySpanRow:
    return TelemetrySpanRow(
        span_id=span_id,
        trace_id=f"trace-{span_id}",
        operation_id=f"operation-{span_id}",
        parent_span_id=None,
        name="ai.release.deployment",
        status="OK",
        request_id=None,
        session_id=None,
        tenant_id=None,
        family_id=None,
        use_case="AI_RELEASE_DEPLOYMENT",
        data_class="OPERATIONAL_TEXT",
        correlation_id=None,
        causation_id=None,
        attributes={"environment": "staging"},
        error_code=None,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=1),
        duration_ms=1000,
    )


@pytest.mark.asyncio
async def test_production_retention_runtime_uses_one_transaction_and_audit_factory(
    session_factory,
) -> None:
    async with session_factory() as session, session.begin():
        session.add(_row("old", NOW - timedelta(days=2)))
        session.add(_row("fresh", NOW - timedelta(minutes=5)))

    audit = InMemoryTelemetryDeletionAudit()
    runtime = ProductionTelemetryRetentionRuntime(
        session_factory=session_factory,
        audit_factory=lambda session: audit,
        environment="staging",
        ttl=timedelta(days=1),
        batch_limit=10,
    )
    result = await runtime.run_once(now=NOW)

    assert result.deleted == 1
    assert result.receipts[0].span_id == "old"
    assert tuple(audit.receipts) == ("telemetry-retention:old",)

    async with session_factory() as session:
        assert await session.get(TelemetrySpanRow, "old") is None
        assert await session.get(TelemetrySpanRow, "fresh") is not None


def test_production_retention_runtime_rejects_invalid_environment_or_batch(session_factory) -> None:
    with pytest.raises(ValueError, match="staging or production"):
        ProductionTelemetryRetentionRuntime(
            session_factory=session_factory,
            audit_factory=lambda session: InMemoryTelemetryDeletionAudit(),
            environment="test",
            ttl=timedelta(days=1),
        )
    with pytest.raises(ValueError, match="batch_limit must be positive"):
        ProductionTelemetryRetentionRuntime(
            session_factory=session_factory,
            audit_factory=lambda session: InMemoryTelemetryDeletionAudit(),
            environment="production",
            ttl=timedelta(days=1),
            batch_limit=0,
        )
