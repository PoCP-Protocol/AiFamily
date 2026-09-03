from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.production_agent_wiring import ProductionAgentRuntimeResolver
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentTask,
    AuthorizationBudget,
)
from backend.intelligence.agent_runtime.persistence import AgentRunPersistenceBase
from backend.intelligence.context_engine.contracts import (
    ContextScope,
    ContextScopeError,
    StateObservation,
)
from backend.intelligence.context_engine.sql_store import (
    AsyncSqlContextBroker,
    ContextPersistenceBase,
)
from backend.intelligence.model_gateway.attempt_persistence import (
    AttemptPersistenceBase,
    SqlAlchemyAttemptSink,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.observability import (
    SqlAlchemyTelemetrySink,
    TelemetryPersistenceBase,
)
from backend.intelligence.prompt_registry.contracts import PromptBundle
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.prompt_registry.sql_registry import (
    PromptPersistenceBase,
    SqlAlchemyPromptRegistry,
)
from backend.intelligence.safety.persistence import (
    SafetyDecisionPersistenceBase,
    SqlAlchemySafetyDecisionSink,
)
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.intelligence.schema_registry.contracts import SchemaDefinition
from backend.intelligence.schema_registry.registry import SchemaRegistry
from backend.intelligence.schema_registry.sql_registry import (
    SchemaPersistenceBase,
    SqlAlchemySchemaRegistry,
)

ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = ROOT / "governance" / "AI_USE_CASE_REGISTRY.yaml"
NOW = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(AgentRunPersistenceBase.metadata.create_all)
        await connection.run_sync(AttemptPersistenceBase.metadata.create_all)
        await connection.run_sync(SafetyDecisionPersistenceBase.metadata.create_all)
        await connection.run_sync(TelemetryPersistenceBase.metadata.create_all)
        await connection.run_sync(PromptPersistenceBase.metadata.create_all)
        await connection.run_sync(SchemaPersistenceBase.metadata.create_all)
        await connection.run_sync(ContextPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _scope(*, data_class: str = "MINOR_PERSONAL_DATA") -> ContextScope:
    return ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id="family-1",
        subject_ids=("child-1",),
        purpose="assessment",
        consent_version="consent-v1",
        consent_granted=True,
        data_class=data_class,
        locale="zh-CN",
        deletion_ref="delete-1",
        correlation_id="corr-1",
        causation_id="cause-1",
    )


async def _context_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[AsyncSqlContextBroker, str]:
    broker = AsyncSqlContextBroker(session_factory)
    observed_at = datetime.now(UTC)
    scope = _scope()
    await broker.append(
        StateObservation(
            observation_id="assessment-observation-1",
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            subject_id=scope.subject_ids[0],
            dimension="assessment_evidence",
            observed_value="evidence-1",
            evidence_refs=("evidence-1",),
            provenance="assessment:evidence-1",
            observed_at=observed_at,
            data_class=scope.data_class,
            purpose=scope.purpose,
            consent_version=scope.consent_version,
            consent_granted=True,
            region_id=scope.region_id,
            locale=scope.locale,
            deletion_ref=scope.deletion_ref,
            correlation_id=scope.correlation_id,
            causation_id=scope.causation_id,
            expires_at=observed_at + timedelta(days=1),
            retention_policy="assessment-context.v1",
        )
    )
    snapshot = await broker.snapshot(scope=scope, now=observed_at)
    return broker, snapshot.snapshot_ref


def _registries() -> tuple[PromptRegistry, SchemaRegistry]:
    prompt = PromptBundle(
        prompt_ref="assessment-prompt",
        version="assessment-v1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        template="Explain the evidence.",
        system_policy_ref="family-safety-v1",
        knowledge_refs=(),
        input_contract_ref="assessment-input-v1",
        output_schema_ref="growth-schema",
        safety_policy_version="safety-v1",
        locale="zh-CN",
        author="product",
        reviewer="reviewer",
        status="PUBLISHED",
        effective_at=NOW,
    )
    schema = SchemaDefinition(
        schema_ref="growth-schema",
        version="growth-v1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        object_type="GrowthPerspective",
        json_schema={
            "type": "object",
            "required": ["explanation", "evidence_refs"],
            "properties": {
                "explanation": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
            },
        },
        status="PUBLISHED",
        effective_at=NOW,
        reviewer="reviewer",
    )
    return PromptRegistry(bundles=(prompt,)), SchemaRegistry(definitions=(schema,))


def _task() -> AgentTask:
    return AgentTask(
        request_id="request-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="assessment_interpretation",
        context_snapshot_ref="snapshot-1",
        prompt_version="assessment-v1",
        schema_version="growth-v1",
        data_class="MINOR_PERSONAL_DATA",
        payload={"evidence_refs": ["evidence-1"]},
        output_schema={"type": "object"},
        prompt_ref="assessment-prompt",
        schema_ref="growth-schema",
    )


def _authorization() -> AgentAuthorization:
    return AgentAuthorization(
        authorization_id="auth-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        allowed_tools=frozenset(),
        issued_by="guardian-1",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="auth-v1",
        reason="assessment explanation",
        audit_ref="audit-1",
    )


def _gateway(provider: FakeProvider) -> ModelGateway:
    record = ProviderRecord(
        provider_id=provider.provider_id,
        vendor="aifamily-test",
        model="fake",
        model_version="1",
        status="INTERNAL_APPROVED",
        approved_environments=("staging",),
        sub_delegates=False,
        minor_data_allowed=True,
        security_assessment_ref="test",
        processing_agreement_ref="test",
        deletion_on_termination_committed=True,
    )
    return ModelGateway(
        {provider.provider_id: provider},
        environment="staging",
        registry=ProviderRegistry((record,)),
        safety_runtime=SafetyRuntime(),
    )


@pytest.mark.asyncio
async def test_production_agent_resolver_binds_scope_and_durable_attempt(session_factory) -> None:
    provider = FakeProvider(
        {
            "assessment_interpretation": {
                "explanation": "先讨论早晨流程。",
                "evidence_refs": ["evidence-1"],
            }
        }
    )
    prompt_registry, schema_registry = _registries()
    context_broker, snapshot_ref = await _context_snapshot(session_factory)
    resolver = ProductionAgentRuntimeResolver(
        scope_resolver=lambda family_id: _scope(),
        session_factory=session_factory,
        gateway=_gateway(provider),
        provider_id=provider.provider_id,
        registry_path=REGISTRY_PATH,
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=context_broker,
        environment="staging",
        clock=lambda: NOW + timedelta(minutes=1),
    )

    runtime = await resolver.resolve("family-1")
    result = await runtime.execute(
        replace(_task(), context_snapshot_ref=snapshot_ref),
        _authorization(),
        idempotency_key="idem-1",
    )

    assert result.draft.status == "DRAFT"
    assert len(provider.invocations) == 1
    async with session_factory() as session:
        attempts = await SqlAlchemyAttemptSink(session).list_attempts(request_id="request-1")
        decisions = await SqlAlchemySafetyDecisionSink(session).list_decisions(
            request_id="request-1"
        )
        assert len(attempts) == 1
        assert attempts[0].status == "SUCCESS"
        assert [item.stage for item in decisions] == ["input", "output"]
        spans = await SqlAlchemyTelemetrySink(session).list_spans(trace_id="request-1")
        assert len(spans) == 2
        assert {span.name for span in spans} == {
            "ai.agent_runtime.execute",
            "ai.model_gateway.generate_structured",
        }
        assert all(span.status == "OK" for span in spans)


@pytest.mark.asyncio
async def test_production_agent_resolver_narrows_to_authorized_evidence_subject(
    session_factory,
) -> None:
    provider = FakeProvider()
    prompt_registry, schema_registry = _registries()
    context_broker = AsyncSqlContextBroker(session_factory)
    family_scope = replace(_scope(), subject_ids=("child-1", "child-2"))
    resolver = ProductionAgentRuntimeResolver(
        scope_resolver=lambda family_id: family_scope,
        session_factory=session_factory,
        gateway=_gateway(provider),
        provider_id=provider.provider_id,
        registry_path=REGISTRY_PATH,
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=context_broker,
        environment="staging",
    )

    runtime = await resolver.resolve_for_subject("family-1", "child-2")

    assert runtime.scope.subject_ids == ("child-2",)
    with pytest.raises(ContextScopeError, match="SUBJECT_SCOPE_MISMATCH"):
        await resolver.resolve_for_subject("family-1", "other-child")


@pytest.mark.asyncio
async def test_production_agent_prefers_authoritative_subject_scope_resolver(
    session_factory,
) -> None:
    provider = FakeProvider()
    prompt_registry, schema_registry = _registries()
    context_broker = AsyncSqlContextBroker(session_factory)
    subject_scope = replace(_scope(), subject_ids=("child-2",))
    resolver = ProductionAgentRuntimeResolver(
        scope_resolver=lambda family_id: _scope(),
        subject_scope_resolver=lambda family_id, subject_id: subject_scope,
        session_factory=session_factory,
        gateway=_gateway(provider),
        provider_id=provider.provider_id,
        registry_path=REGISTRY_PATH,
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=context_broker,
        environment="staging",
    )

    runtime = await resolver.resolve_for_subject("family-1", "child-2")

    assert runtime.scope is subject_scope


@pytest.mark.asyncio
async def test_production_agent_resolver_builds_sql_registries_per_request(session_factory) -> None:
    provider = FakeProvider(
        {
            "assessment_interpretation": {
                "explanation": "先讨论早晨流程。",
                "evidence_refs": ["evidence-1"],
            }
        }
    )
    prompt_registry, schema_registry = _registries()
    context_broker, snapshot_ref = await _context_snapshot(session_factory)
    async with session_factory() as session:
        await SqlAlchemyPromptRegistry(session).register(
            prompt_registry.get("assessment-prompt", "assessment-v1")
        )
        await SqlAlchemySchemaRegistry(session).register(
            schema_registry.get("growth-schema", "growth-v1")
        )
        await session.commit()

    resolver = ProductionAgentRuntimeResolver(
        scope_resolver=lambda family_id: _scope(),
        session_factory=session_factory,
        gateway=_gateway(provider),
        provider_id=provider.provider_id,
        registry_path=REGISTRY_PATH,
        prompt_registry_factory=SqlAlchemyPromptRegistry,
        schema_registry_factory=SqlAlchemySchemaRegistry,
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=context_broker,
        environment="staging",
        clock=lambda: NOW + timedelta(minutes=1),
    )
    runtime = await resolver.resolve("family-1")
    result = await runtime.execute(
        replace(_task(), context_snapshot_ref=snapshot_ref),
        _authorization(),
        idempotency_key="sql-registry-1",
    )

    assert result.draft.status == "DRAFT"
    assert len(provider.invocations) == 1


@pytest.mark.asyncio
async def test_production_agent_resolver_requires_safety_runtime(session_factory) -> None:
    provider = FakeProvider()
    gateway = ModelGateway({provider.provider_id: provider}, environment="staging")
    prompt_registry, schema_registry = _registries()
    context_broker = AsyncSqlContextBroker(session_factory)
    with pytest.raises(ValueError, match="SafetyRuntime"):
        ProductionAgentRuntimeResolver(
            scope_resolver=lambda family_id: _scope(),
            session_factory=session_factory,
            gateway=gateway,
            provider_id=provider.provider_id,
            registry_path=REGISTRY_PATH,
            prompt_registry=prompt_registry,
            schema_registry=schema_registry,
            attempt_sink_factory=SqlAlchemyAttemptSink,
            safety_sink_factory=SqlAlchemySafetyDecisionSink,
            context_broker=context_broker,
            environment="staging",
        )


@pytest.mark.asyncio
async def test_production_agent_resolver_requires_durable_context_broker(
    session_factory,
) -> None:
    provider = FakeProvider()
    prompt_registry, schema_registry = _registries()
    with pytest.raises(ValueError, match="Context Broker"):
        ProductionAgentRuntimeResolver(
            scope_resolver=lambda family_id: _scope(),
            session_factory=session_factory,
            gateway=_gateway(provider),
            provider_id=provider.provider_id,
            registry_path=REGISTRY_PATH,
            prompt_registry=prompt_registry,
            schema_registry=schema_registry,
            attempt_sink_factory=SqlAlchemyAttemptSink,
            safety_sink_factory=SqlAlchemySafetyDecisionSink,
            telemetry_sink_factory=SqlAlchemyTelemetrySink,
            environment="staging",
        )


@pytest.mark.asyncio
async def test_production_agent_handle_rejects_cross_scope_task(session_factory) -> None:
    provider = FakeProvider()
    prompt_registry, schema_registry = _registries()
    context_broker = AsyncSqlContextBroker(session_factory)
    resolver = ProductionAgentRuntimeResolver(
        scope_resolver=lambda family_id: _scope(),
        session_factory=session_factory,
        gateway=_gateway(provider),
        provider_id=provider.provider_id,
        registry_path=REGISTRY_PATH,
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=context_broker,
        environment="staging",
    )
    runtime = await resolver.resolve("family-1")
    task = _task()
    with pytest.raises(ContextScopeError, match="SCOPE_MISMATCH"):
        await runtime.execute(
            replace(task, family_id="family-2"),
            _authorization(),
            idempotency_key="idem-2",
        )


@pytest.mark.asyncio
async def test_production_agent_rejects_unknown_context_before_model_call(
    session_factory,
) -> None:
    provider = FakeProvider()
    prompt_registry, schema_registry = _registries()
    resolver = ProductionAgentRuntimeResolver(
        scope_resolver=lambda family_id: _scope(),
        session_factory=session_factory,
        gateway=_gateway(provider),
        provider_id=provider.provider_id,
        registry_path=REGISTRY_PATH,
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=AsyncSqlContextBroker(session_factory),
        environment="staging",
    )
    runtime = await resolver.resolve("family-1")

    with pytest.raises(ValueError, match="CONTEXT_SNAPSHOT_NOT_FOUND"):
        await runtime.execute(_task(), _authorization(), idempotency_key="missing-context")

    assert provider.invocations == []
