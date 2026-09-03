from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.observability import (
    InMemoryTelemetrySink,
    SessionPerCallTelemetrySink,
    SqlAlchemyTelemetrySink,
    TelemetryContext,
    TelemetryPersistenceBase,
)


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


def _context() -> TelemetryContext:
    return TelemetryContext(
        trace_id="trace-1",
        request_id="request-1",
        session_id="session-1",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="family_image_summary",
        data_class="OPERATIONAL_TEXT",
        operation_id="operation-1",
        correlation_id="correlation-1",
        causation_id="causation-1",
    )


def test_telemetry_context_does_not_trust_malformed_ref_prefix() -> None:
    context = TelemetryContext(
        trace_id="trace-ref",
        tenant_id="ref:plain-tenant",
        family_id="family-1",
        use_case="test",
        data_class="SYNTHETIC",
    )
    assert context.tenant_id != "ref:plain-tenant"
    assert context.tenant_id is not None and context.tenant_id.startswith("ref:")


@pytest.mark.asyncio
async def test_in_memory_telemetry_lifecycle_is_metadata_only() -> None:
    sink = InMemoryTelemetrySink()
    handle = await sink.start_span(
        name="ai.model_gateway.generate_structured",
        context=_context(),
        attributes={"provider_id": "internal", "has_media": True},
    )
    await sink.finish_span(
        handle,
        status="OK",
        attributes={"draft_status": "DRAFT"},
    )

    assert sink.spans[0]["status"] == "OK"
    assert sink.spans[0]["trace_id"] == "trace-1"
    assert sink.spans[0]["tenant_id"] != "tenant-1"
    assert sink.spans[0]["family_id"] != "family-1"
    assert sink.spans[0]["attributes"] == {
        "provider_id": "internal",
        "has_media": True,
        "draft_status": "DRAFT",
    }
    assert "payload" not in sink.spans[0]
    assert "prompt" not in sink.spans[0]


@pytest.mark.asyncio
async def test_telemetry_rejects_unallowlisted_attributes() -> None:
    sink = InMemoryTelemetrySink()
    with pytest.raises(ValueError, match="ATTRIBUTE_NOT_ALLOWED"):
        await sink.start_span(
            name="ai.model_gateway.generate_structured",
            context=_context(),
            attributes={"raw_payload": "must-not-be-recorded"},
        )


@pytest.mark.asyncio
async def test_sql_telemetry_round_trips_and_flushes_only(session_factory) -> None:
    started = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)
    async with session_factory() as session:
        sink = SqlAlchemyTelemetrySink(session)
        handle = await sink.start_span(
            name="ai.model_gateway.generate_structured",
            context=_context(),
            attributes={"provider_id": "internal", "route_sequence": 0},
        )
        await sink.finish_span(
            handle,
            status="ERROR",
            ended_at=started,
            error_code="POLICY_REJECTED",
        )
        rows = await sink.list_spans(trace_id="trace-1")
        await session.commit()

    assert len(rows) == 1
    assert rows[0].status == "ERROR"
    assert rows[0].error_code == "POLICY_REJECTED"
    assert rows[0].attributes == {"provider_id": "internal", "route_sequence": 0}
    assert rows[0].tenant_id != "tenant-1"
    assert rows[0].family_id != "family-1"


@pytest.mark.asyncio
async def test_session_per_call_telemetry_lifecycle_is_immediately_durable(
    session_factory,
) -> None:
    sink = SessionPerCallTelemetrySink(session_factory)
    handle = await sink.start_span(
        name="ai.model_gateway.generate_structured",
        context=_context(),
        attributes={"provider_id": "internal"},
    )
    async with session_factory() as session:
        rows = await SqlAlchemyTelemetrySink(session).list_spans(trace_id="trace-1")
        assert rows[0].status == "IN_PROGRESS"
    await sink.finish_span(handle, status="ERROR", error_code="TIMEOUT")
    async with session_factory() as session:
        rows = await SqlAlchemyTelemetrySink(session).list_spans(trace_id="trace-1")
        assert rows[0].status == "ERROR"
        assert rows[0].error_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_telemetry_operation_replay_is_idempotent_and_conflicts_fail() -> None:
    sink = InMemoryTelemetrySink()
    handle = await sink.start_span(
        name="ai.model_gateway.generate_structured",
        context=_context(),
        attributes={"provider_id": "internal"},
    )
    replay = await sink.start_span(
        name="ai.model_gateway.generate_structured",
        context=_context(),
        attributes={"provider_id": "internal"},
    )
    assert replay == handle
    with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
        await sink.start_span(
            name="ai.model_gateway.generate_structured",
            context=replace(_context(), use_case="different_use_case"),
            attributes={"provider_id": "other"},
        )


@pytest.mark.asyncio
async def test_sql_telemetry_operation_replay_is_idempotent(session_factory) -> None:
    async with session_factory() as session:
        sink = SqlAlchemyTelemetrySink(session)
        first = await sink.start_span(
            name="ai.model_gateway.generate_structured",
            context=_context(),
            attributes={"provider_id": "internal"},
        )
        replay = await sink.start_span(
            name="ai.model_gateway.generate_structured",
            context=_context(),
            attributes={"provider_id": "internal"},
        )
        assert replay.span_id == first.span_id
        with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
            await sink.start_span(
                name="ai.model_gateway.generate_structured",
                context=replace(_context(), use_case="different_use_case"),
                attributes={"provider_id": "other"},
            )


@pytest.mark.asyncio
async def test_replay_cannot_relabel_scope_with_same_attributes() -> None:
    sink = InMemoryTelemetrySink()
    await sink.start_span(
        name="ai.model_gateway.generate_structured",
        context=_context(),
        attributes={"provider_id": "internal"},
    )
    with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
        await sink.start_span(
            name="ai.model_gateway.generate_structured",
            context=replace(_context(), family_id="family-other"),
            attributes={"provider_id": "internal"},
        )


@pytest.mark.asyncio
async def test_sql_replay_cannot_relabel_scope_with_same_attributes(session_factory) -> None:
    async with session_factory() as session:
        sink = SqlAlchemyTelemetrySink(session)
        await sink.start_span(
            name="ai.model_gateway.generate_structured",
            context=_context(),
            attributes={"provider_id": "internal"},
        )
        with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
            await sink.start_span(
                name="ai.model_gateway.generate_structured",
                context=replace(_context(), family_id="family-other"),
                attributes={"provider_id": "internal"},
            )
