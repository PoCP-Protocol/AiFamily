from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.observability.persistence import (
    TelemetryPersistenceBase,
    TelemetrySpanRow,
)
from backend.intelligence.observability.retention import (
    InMemoryTelemetryDeletionAudit,
    InMemoryTelemetryRetentionStore,
    SqlAlchemyTelemetryRetentionStore,
    TelemetryRetentionWorker,
    TelemetrySpanRecord,
)

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory():
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
        name="ai.model_gateway.generate_structured",
        status="OK",
        request_id=None,
        session_id=None,
        tenant_id="tenant-opaque",
        family_id="family-opaque",
        use_case="experience_draft",
        data_class="SYNTHETIC",
        correlation_id=None,
        causation_id=None,
        attributes={"environment": "test"},
        error_code=None,
        started_at=started_at,
        ended_at=started_at + timedelta(seconds=1),
        duration_ms=1000,
    )


@pytest.mark.asyncio
async def test_sql_retention_deletes_only_expired_spans_in_batches(session_factory) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add_all(
                [
                    _row("span-old-a", NOW - timedelta(hours=3)),
                    _row("span-old-b", NOW - timedelta(hours=2)),
                    _row("span-fresh", NOW - timedelta(minutes=30)),
                ]
            )
        worker = TelemetryRetentionWorker(SqlAlchemyTelemetryRetentionStore(session))
        async with session.begin():
            first = await worker.run_once(ttl=timedelta(hours=1), limit=1, now=NOW)
        assert first.deleted == 1
        assert first.receipts[0].span_id == "span-old-a"
        assert first.receipts[0].cutoff == NOW - timedelta(hours=1)

        async with session.begin():
            second = await worker.run_once(ttl=timedelta(hours=1), limit=10, now=NOW)
        assert tuple(item.span_id for item in second.receipts) == ("span-old-b",)

        remaining = await session.scalars(select(TelemetrySpanRow))
        assert {row.span_id for row in remaining} == {"span-fresh"}


@pytest.mark.asyncio
async def test_sql_retention_is_idempotent_and_transaction_rolls_back(session_factory) -> None:
    async with session_factory() as session:
        async with session.begin():
            session.add(_row("span-old", NOW - timedelta(days=2)))
        worker = TelemetryRetentionWorker(SqlAlchemyTelemetryRetentionStore(session))
        async with session.begin():
            first = await worker.run_once(ttl=timedelta(days=1), now=NOW)
        assert first.deleted == 1

        async with session.begin():
            repeated = await worker.run_once(ttl=timedelta(days=1), now=NOW)
        assert repeated.receipts == ()

        async with session.begin():
            session.add(_row("span-rollback", NOW - timedelta(days=2)))
        with pytest.raises(RuntimeError, match="abort retention"):
            async with session.begin():
                await worker.run_once(ttl=timedelta(days=1), now=NOW)
                raise RuntimeError("abort retention")
        assert await session.get(TelemetrySpanRow, "span-rollback") is not None


@pytest.mark.asyncio
async def test_in_memory_retention_audit_and_batch_boundary_are_replay_safe() -> None:
    store = InMemoryTelemetryRetentionStore(
        [
            TelemetrySpanRecord("span-b", NOW - timedelta(hours=3), "t", "f"),
            TelemetrySpanRecord("span-a", NOW - timedelta(hours=3), "t", "f"),
            TelemetrySpanRecord("span-new", NOW - timedelta(minutes=1), "t", "f"),
        ]
    )
    audit = InMemoryTelemetryDeletionAudit()
    worker = TelemetryRetentionWorker(store, audit=audit)

    first = await worker.run_once(ttl=timedelta(hours=1), limit=1, now=NOW)
    assert tuple(item.span_id for item in first.receipts) == ("span-a",)
    assert tuple(audit.receipts) == ("telemetry-retention:span-a",)
    second = await worker.run_once(ttl=timedelta(hours=1), limit=10, now=NOW)
    assert tuple(item.span_id for item in second.receipts) == ("span-b",)
    repeated = await worker.run_once(ttl=timedelta(hours=1), limit=10, now=NOW)
    assert repeated.receipts == ()
    assert {item.span_id for item in store.remaining()} == {"span-new"}


@pytest.mark.asyncio
async def test_retention_validates_ttl_limit_and_timezone() -> None:
    worker = TelemetryRetentionWorker(InMemoryTelemetryRetentionStore())
    with pytest.raises(ValueError, match="TTL_MUST_BE_POSITIVE"):
        await worker.run_once(ttl=timedelta(0), now=NOW)
    with pytest.raises(ValueError, match="LIMIT_INVALID"):
        await worker.run_once(ttl=timedelta(hours=1), limit=-1, now=NOW)
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        await worker.run_once(ttl=timedelta(hours=1), now=datetime(2026, 8, 30, 12, 0))
