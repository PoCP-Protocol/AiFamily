from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.model_gateway.attempt_persistence import (
    AttemptPersistenceBase,
    SessionPerCallAttemptSink,
    SqlAlchemyAttemptSink,
)
from backend.intelligence.model_gateway.attempts import AttemptOutcome
from backend.intelligence.model_gateway.contracts import StructuredRequest, TokenUsage
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.safety.runtime import SafetyRuntime


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(AttemptPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_attempt_sink_persists_started_before_finish(session_factory) -> None:
    started = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)
    async with session_factory() as session:
        sink = SqlAlchemyAttemptSink(session, clock=lambda: started)
        attempt_id = await sink.begin(
            provider_id="provider-1",
            use_case="assessment_interpretation",
            data_class="SYNTHETIC",
            environment="test",
            route_sequence=0,
            request_id="request-1",
            session_id="session-1",
        )
        rows = await sink.list_attempts(request_id="request-1")
        assert len(rows) == 1
        assert rows[0].attempt_id == attempt_id
        assert rows[0].status == "STARTED"
        assert rows[0].finished_at is None

        await sink.finish(
            attempt_id,
            AttemptOutcome(
                status="SUCCESS",
                latency_ms=17,
                model="model-1",
                model_version="v1",
                token_usage=TokenUsage(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            ),
        )
        await session.commit()

    async with session_factory() as session:
        sink = SqlAlchemyAttemptSink(session, clock=lambda: started)
        rows = await sink.list_attempts(request_id="request-1")
        assert rows[0].status == "SUCCESS"
        assert rows[0].latency_ms == 17
        assert rows[0].model == "model-1"
        assert rows[0].model_version == "v1"
        assert rows[0].prompt_tokens == 11
        assert rows[0].completion_tokens == 7
        assert rows[0].total_tokens == 18


@pytest.mark.asyncio
async def test_sql_attempt_sink_rejects_naive_clock(session_factory) -> None:
    async with session_factory() as session:
        sink = SqlAlchemyAttemptSink(session, clock=lambda: datetime(2026, 8, 30))
        with pytest.raises(ValueError, match="timezone-aware"):
            await sink.begin(
                provider_id="provider-1",
                use_case="assessment_interpretation",
                data_class="SYNTHETIC",
                environment="test",
                route_sequence=0,
                request_id=None,
                session_id=None,
            )


@pytest.mark.asyncio
async def test_session_per_call_attempt_survives_caller_rollback(session_factory) -> None:
    sink = SessionPerCallAttemptSink(session_factory)
    attempt_id = await sink.begin(
        provider_id="provider-1",
        use_case="assessment_interpretation",
        data_class="SYNTHETIC",
        environment="test",
        route_sequence=0,
        request_id="request-independent",
        session_id=None,
    )
    async with session_factory() as session:
        rows = await SqlAlchemyAttemptSink(session).list_attempts(
            request_id="request-independent"
        )
        assert rows[0].status == "STARTED"
    await sink.finish(
        attempt_id,
        AttemptOutcome(status="FAILURE", latency_ms=1, failure_kind="TIMEOUT"),
    )
    async with session_factory() as session:
        rows = await SqlAlchemyAttemptSink(session).list_attempts(
            request_id="request-independent"
        )
        assert rows[0].status == "FAILURE"
        assert rows[0].failure_kind == "TIMEOUT"


@pytest.mark.asyncio
async def test_gateway_awaits_durable_sink_and_closes_attempt(session_factory) -> None:
    provider = FakeProvider({"assessment_interpretation": {"headline": "ok"}})
    record = ProviderRecord(
        provider_id=provider.provider_id,
        vendor="aifamily-test",
        model="fake",
        model_version="1",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        sub_delegates=False,
        security_assessment_ref="test",
        processing_agreement_ref="test",
        deletion_on_termination_committed=True,
    )
    request = StructuredRequest(
        use_case="assessment_interpretation",
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        data_class="SYNTHETIC",
        payload={"answers": [1]},
        output_schema={
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
        context_snapshot_ref="ctx:attempt",
        request_id="request:attempt",
        tenant_id="tenant:attempt",
        family_id="family:attempt",
    )
    async with session_factory() as session:
        sink = SqlAlchemyAttemptSink(session)
        gateway = ModelGateway(
            {provider.provider_id: provider},
            environment="test",
            registry=ProviderRegistry((record,)),
            attempt_sink=sink,
            safety_runtime=SafetyRuntime(),
        )
        draft = await gateway.generate_structured(request, provider_id=provider.provider_id)
        assert draft.output["headline"] == "ok"
        rows = await sink.list_attempts(request_id="request:attempt")
        assert len(rows) == 1
        assert rows[0].status == "SUCCESS"
        assert rows[0].prompt_tokens == 0
        assert rows[0].completion_tokens == 0
        assert rows[0].total_tokens == 0
        assert rows[0].tenant_id == "tenant:attempt"
        assert rows[0].family_id == "family:attempt"
        await session.commit()
