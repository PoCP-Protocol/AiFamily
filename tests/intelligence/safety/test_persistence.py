from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.model_gateway.attempt_persistence import (
    AttemptPersistenceBase,
    SqlAlchemyAttemptSink,
)
from backend.intelligence.model_gateway.contracts import StructuredRequest
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.safety.persistence import (
    InMemorySafetyDecisionSink,
    SafetyDecisionPersistenceBase,
    SessionPerCallSafetyDecisionSink,
    SqlAlchemySafetyDecisionSink,
)
from backend.intelligence.safety.runtime import SafetyContext, SafetyRuntime


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(AttemptPersistenceBase.metadata.create_all)
        await connection.run_sync(SafetyDecisionPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _request(*, use_case: str = "assessment_interpretation") -> StructuredRequest:
    return StructuredRequest(
        use_case=use_case,
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        data_class="SYNTHETIC",
        payload={"headline": "ok"},
        output_schema={
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
        context_snapshot_ref="ctx:safety",
        request_id="request:safety",
        tenant_id="tenant:safety",
        family_id="family:safety",
    )


def _gateway(provider: FakeProvider, *, safety_sink=None) -> ModelGateway:
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
    return ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((record,)),
        safety_runtime=SafetyRuntime(),
        safety_sink=safety_sink,
    )


def test_in_memory_safety_sink_records_policy_metadata_only() -> None:
    sink = InMemorySafetyDecisionSink()
    runtime = SafetyRuntime()
    context = SafetyContext(use_case="assessment_interpretation", data_class="SYNTHETIC")
    decision = runtime.evaluate_input(context, {"headline": "ok"})
    sink.record(
        stage="input",
        context=context,
        decision=decision,
        request_id="request-1",
        session_id=None,
    )
    assert sink.decisions[0]["status"] == "ALLOW"
    assert "payload" not in sink.decisions[0]


@pytest.mark.asyncio
async def test_session_per_call_safety_decision_is_immediately_durable(
    session_factory,
) -> None:
    context = SafetyContext(use_case="assessment_interpretation", data_class="SYNTHETIC")
    decision = SafetyRuntime().evaluate_input(context, {"headline": "ok"})
    await SessionPerCallSafetyDecisionSink(session_factory).record(
        stage="input",
        context=context,
        decision=decision,
        request_id="request-independent",
        session_id=None,
    )
    async with session_factory() as session:
        rows = await SqlAlchemySafetyDecisionSink(session).list_decisions(
            request_id="request-independent"
        )
        assert [row.stage for row in rows] == ["input"]


@pytest.mark.asyncio
async def test_gateway_persists_input_and_output_safety_decisions(session_factory) -> None:
    provider = FakeProvider({"assessment_interpretation": {"headline": "ok"}})
    async with session_factory() as session:
        gateway = _gateway(
            provider,
            safety_sink=SqlAlchemySafetyDecisionSink(session, clock=lambda: datetime.now(UTC)),
        ).with_attempt_sink(SqlAlchemyAttemptSink(session))
        draft = await gateway.generate_structured(
            _request(), provider_id=provider.provider_id
        )
        assert draft.status == "DRAFT"
        rows = await SqlAlchemySafetyDecisionSink(session).list_decisions(
            request_id="request:safety"
        )
        assert [row.stage for row in rows] == ["input", "output"]
        assert all(row.status == "ALLOW" for row in rows)
        assert all(row.tenant_id == "tenant:safety" for row in rows)
        assert all(row.family_id == "family:safety" for row in rows)
        await session.commit()


@pytest.mark.asyncio
async def test_gateway_fails_closed_when_safety_decision_persistence_breaks() -> None:
    class BrokenSink(InMemorySafetyDecisionSink):
        def record(self, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("ledger unavailable")

    provider = FakeProvider({"assessment_interpretation": {"headline": "ok"}})
    gateway = _gateway(provider, safety_sink=BrokenSink())
    with pytest.raises(ModelGatewayError, match="POLICY_REJECTED"):
        await gateway.generate_structured(_request(), provider_id=provider.provider_id)
    assert provider.invocations == []
