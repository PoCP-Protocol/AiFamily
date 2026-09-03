from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.assessment_ai_wiring import AssessmentAiAssets
from backend.apps.family_api.production_agent_wiring import ProductionAgentRuntimeResolver
from backend.apps.family_api.production_assessment_ai_wiring import (
    ProductionAssessmentAiComposition,
)
from backend.apps.family_api.production_assessment_http_wiring import (
    ProductionAssessmentAiCompositionResolver,
    SqlAlchemyAssessmentContextScopeResolver,
    SqlAlchemyAssessmentIdentityResolver,
    install_production_assessment_http_wiring,
)
from backend.domains.assessment.api import register_exception_handlers
from backend.domains.assessment.api import router as assessment_router
from backend.domains.assessment.api.dependencies import FamilyContext
from backend.domains.assessment.application.commands import (
    AssessmentCommandHandler,
    MutationMeta,
    SaveAssessmentResponseCommand,
    StartAssessmentCommand,
    SubmitAssessmentCommand,
)
from backend.domains.assessment.application.growth_hypothesis_commands import (
    GrowthHypothesisCommandHandler,
)
from backend.domains.assessment.application.queries import AssessmentQueryHandler
from backend.domains.assessment.domain.entities import GrowthHypothesisEvidence
from backend.domains.assessment.infrastructure.fake_repository import FakeAssessmentRepository
from backend.intelligence.agent_runtime.authorization_persistence import (
    AgentAuthorizationPersistenceBase,
    SqlAlchemyAgentAuthorizationLeaseStore,
)
from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AuthorizationBudget
from backend.intelligence.agent_runtime.persistence import AgentRunPersistenceBase
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
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
from backend.intelligence.observability import SqlAlchemyTelemetrySink, TelemetryPersistenceBase
from backend.intelligence.prompt_registry.contracts import PromptBundle
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.safety.persistence import (
    SafetyDecisionPersistenceBase,
    SqlAlchemySafetyDecisionSink,
)
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.intelligence.schema_registry.contracts import SchemaDefinition
from backend.intelligence.schema_registry.registry import SchemaRegistry

NOW = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]


class RuntimeResolver:
    def __init__(self, session_factory, context_broker, *, environment="staging") -> None:
        self.session_factory = session_factory
        self.context_broker = context_broker
        self.environment = environment

    async def resolve(self, family_id):  # pragma: no cover - composition-only test
        raise AssertionError("not executed")


def _assets() -> AssessmentAiAssets:
    return AssessmentAiAssets(
        prompt_ref="assessment_interpretation_v1",
        prompt_version="1.0.0",
        schema_ref="growth_perspective_v1",
        schema_version="1.0.0",
        reviewed_construct_refs=frozenset({"PARENT_CHILD_COMMUNICATION"}),
    )


@pytest.fixture
async def dependencies():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ContextPersistenceBase.metadata.create_all)
        await connection.run_sync(AgentAuthorizationPersistenceBase.metadata.create_all)
        await connection.run_sync(AgentRunPersistenceBase.metadata.create_all)
        await connection.run_sync(AttemptPersistenceBase.metadata.create_all)
        await connection.run_sync(SafetyDecisionPersistenceBase.metadata.create_all)
        await connection.run_sync(TelemetryPersistenceBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    broker = AsyncSqlContextBroker(session_factory)
    try:
        yield engine, session_factory, broker
    finally:
        await engine.dispose()


def test_composition_builds_ui03_query_and_confirmation_handlers_with_same_policy(
    dependencies,
) -> None:
    engine, session_factory, broker = dependencies
    composition = ProductionAssessmentAiComposition(
        environment="test",
        session_factory=session_factory,
        runtime_resolver=RuntimeResolver(session_factory, broker),
        context_broker=broker,
        actor_id_resolver=lambda: "guardian-1",
        assets=_assets(),
        clock=lambda: NOW,
    )
    repository = FakeAssessmentRepository()

    assert isinstance(composition.build_query_handler(repository), AssessmentQueryHandler)
    assert isinstance(
        composition.build_growth_hypothesis_handler(repository),
        GrowthHypothesisCommandHandler,
    )


def test_composition_rejects_split_context_or_store_wiring(dependencies) -> None:
    _, session_factory, broker = dependencies
    other_broker = AsyncSqlContextBroker(session_factory)
    with pytest.raises(ValueError, match="share Context Broker"):
        ProductionAssessmentAiComposition(
            environment="staging",
            session_factory=session_factory,
            runtime_resolver=RuntimeResolver(session_factory, broker),
            context_broker=other_broker,
            actor_id_resolver=lambda: "guardian-1",
            assets=_assets(),
            clock=lambda: NOW,
        )


def test_composition_rejects_dev_environment(dependencies) -> None:
    _, session_factory, broker = dependencies
    with pytest.raises(ValueError, match="test/staging/production"):
        ProductionAssessmentAiComposition(
            environment="development",
            session_factory=session_factory,
            runtime_resolver=RuntimeResolver(session_factory, broker),
            context_broker=broker,
            actor_id_resolver=lambda: "guardian-1",
            assets=_assets(),
            clock=lambda: NOW,
        )


def _scope() -> ContextScope:
    return ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id="family-1",
        subject_ids=("child-1",),
        purpose="ASSESSMENT",
        consent_version="consent.v3",
        consent_granted=True,
        data_class=DataClass.MINOR_PERSONAL_DATA,
        locale="zh-CN",
        deletion_ref="deletion:child-1",
        correlation_id="correlation:ui03",
        causation_id="assessment-session:session-1",
    )


def _evidence() -> GrowthHypothesisEvidence:
    return GrowthHypothesisEvidence(
        assessment_session_id="session-1",
        subject_person_id="child-1",
        subject_display_name="小宇",
        submitted_at=NOW - timedelta(minutes=5),
        tool_ref="FAMILY_SUPPORT_NEEDS",
        tool_version=2,
        assessment_response_id="response-1",
        focus_ref="COMMUNICATION",
        assessment_evidence_id="evidence-1",
        need_type_ref="COMMUNICATION_SUPPORT",
        need_type_version=1,
        title="沟通支持",
        description="先观察家庭沟通节奏。",
        required_capability_keys=["FAMILY_DIALOGUE"],
        response_set=[
            {"item_ref": "item-1", "response_type": "SINGLE_CHOICE", "response_value": "B"}
        ],
    )


def _registries() -> tuple[PromptRegistry, SchemaRegistry]:
    schema = {
        "type": "object",
        "required": [
            "model_component_ref",
            "boundary_labels",
            "need_summary",
            "construct_signals",
            "hypotheses",
            "action_candidates",
        ],
        "properties": {
            "model_component_ref": {"type": "string"},
            "assessment_ref": {"type": "string"},
            "boundary_labels": {"type": "array", "items": {"type": "string"}},
            "need_summary": {"type": "array"},
            "construct_signals": {"type": "array"},
            "hypotheses": {"type": "array"},
            "action_candidates": {"type": "array"},
        },
    }
    return (
        PromptRegistry(
            bundles=(
                PromptBundle(
                    prompt_ref="assessment_interpretation_v1",
                    version="1.0.0",
                    use_case="assessment_interpretation",
                    agent_id="parent_advisor",
                    template="Explain submitted evidence as a non-diagnostic perspective.",
                    system_policy_ref="family-safety-v1",
                    knowledge_refs=(),
                    input_contract_ref="assessment-evidence-v1",
                    output_schema_ref="growth_perspective_v1",
                    safety_policy_version="family-safety-v1",
                    locale="zh-CN",
                    author="product",
                    reviewer="reviewer",
                    status="PUBLISHED",
                    effective_at=NOW - timedelta(days=1),
                ),
            )
        ),
        SchemaRegistry(
            definitions=(
                SchemaDefinition(
                    schema_ref="growth_perspective_v1",
                    version="1.0.0",
                    use_case="assessment_interpretation",
                    agent_id="parent_advisor",
                    object_type="GrowthPerspective",
                    json_schema=schema,
                    status="PUBLISHED",
                    effective_at=NOW - timedelta(days=1),
                    reviewer="reviewer",
                ),
            )
        ),
    )


def _model_output(assessment_ref: str) -> dict:
    return {
        "model_component_ref": "FAMILY_ASSESSMENT_V1",
        "assessment_ref": assessment_ref,
        "boundary_labels": ["hypothesis_not_fact", "recommendation_not_decision"],
        "need_summary": [{"need_ref": "COMMUNICATION_SUPPORT"}],
        "construct_signals": [
            {
                "construct_ref": "PARENT_CHILD_COMMUNICATION",
                "boundary": "signal_not_diagnosis",
            }
        ],
        "hypotheses": [
            {
                "hypothesis_ref": f"{assessment_ref}:H1",
                "boundary": "hypothesis_not_fact",
                "construct_refs": ["PARENT_CHILD_COMMUNICATION"],
                "is_primary_contradiction": True,
            }
        ],
        "action_candidates": [
            {
                "action_ref": "COMMUNICATION_SUPPORT:ACTION",
                "boundary": "recommendation_not_decision",
            }
        ],
    }


async def _build_real_composition(
    session_factory,
    broker,
    *,
    assessment_ref: str,
    runtime_scope: ContextScope | None = None,
) -> tuple[ProductionAssessmentAiComposition, FakeProvider]:
    provider = FakeProvider({"assessment_interpretation": _model_output(assessment_ref)})
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="staging",
        registry=ProviderRegistry(
            (
                ProviderRecord(
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
                ),
            )
        ),
        safety_runtime=SafetyRuntime(),
    )
    prompt_registry, schema_registry = _registries()
    resolved_scope = runtime_scope or _scope()
    runtime_resolver = ProductionAgentRuntimeResolver(
        scope_resolver=lambda family_id: resolved_scope,
        session_factory=session_factory,
        gateway=gateway,
        provider_id=provider.provider_id,
        registry_path=ROOT / "governance" / "AI_USE_CASE_REGISTRY.yaml",
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=broker,
        environment="staging",
        clock=lambda: NOW,
    )
    authorization = AgentAuthorization(
        authorization_id="assessment-auth-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        allowed_tools=frozenset({"read_context"}),
        issued_by="guardian-1",
        issued_at=NOW - timedelta(minutes=10),
        expires_at=NOW + timedelta(hours=1),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="assessment-auth.v1",
        reason="guardian requested assessment perspective",
        audit_ref="audit:assessment-auth-1",
    )
    async with session_factory() as session:
        await SqlAlchemyAgentAuthorizationLeaseStore(session).issue(authorization)
        await session.commit()
    return (
        ProductionAssessmentAiComposition(
            environment="staging",
            session_factory=session_factory,
            runtime_resolver=runtime_resolver,
            context_broker=broker,
            actor_id_resolver=lambda: "guardian-1",
            assets=_assets(),
            clock=lambda: NOW,
        ),
        provider,
    )


@pytest.mark.asyncio
async def test_real_composition_replays_exact_ui03_draft_without_second_provider_call(
    dependencies,
) -> None:
    _, session_factory, broker = dependencies
    composition, provider = await _build_real_composition(
        session_factory,
        broker,
        assessment_ref="session-1",
    )
    adapter = composition.build_interpretation_adapter()

    first = await adapter.interpret("family-1", _evidence())
    replay = await adapter.interpret("family-1", _evidence())

    assert first == replay
    assert len(provider.invocations) == 1
    assert first["scorecard"]["draft_status"] == "DRAFT"


@pytest.mark.asyncio
async def test_http_composition_resolver_builds_subject_scoped_production_runtime(
    dependencies,
) -> None:
    engine, session_factory, broker = dependencies
    source, _ = await _build_real_composition(
        session_factory,
        broker,
        assessment_ref="session-1",
    )
    source_runtime = source.runtime_resolver
    resolver = ProductionAssessmentAiCompositionResolver(
        engine=engine,
        session_factory=session_factory,
        gateway=source_runtime.gateway,
        provider_id=source_runtime.provider_id,
        registry_path=source_runtime.registry_path,
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=broker,
        assets=_assets(),
        environment="staging",
        clock=lambda: NOW,
        prompt_registry=source_runtime.prompt_registry,
        schema_registry=source_runtime.schema_registry,
    )

    composition = await resolver(
        FamilyContext("tenant-1", "family-1", "guardian-1"),
        "Bearer guardian-token",
        "corr:ui03",
        "cause:ui03",
    )

    assert composition.actor_id_resolver() == "guardian-1"
    assert isinstance(composition.runtime_resolver, ProductionAgentRuntimeResolver)
    assert composition.runtime_resolver.subject_scope_resolver is not None


@pytest.mark.asyncio
async def test_http_ui03_to_guardian_confirmation_reuses_same_model_draft(
    dependencies,
) -> None:
    engine, session_factory, broker = dependencies
    child_id = "11111111-1111-4111-8111-111111111111"
    repository = FakeAssessmentRepository()
    repository.seed_family("tenant-1", "family-1")
    repository.grant_family_manage_permission("family-1", "guardian-1")
    repository.seed_subject("family-1", child_id, "小宇")
    repository.seed_need_type(
        "COMMUNICATION",
        "COMMUNICATION_SUPPORT",
        "沟通支持",
        "先观察家庭沟通节奏。",
        ["FAMILY_DIALOGUE"],
    )
    commands = AssessmentCommandHandler(repository)
    started = await commands.start(
        StartAssessmentCommand(
            "family-1",
            "tenant-1",
            "guardian-1",
            child_id,
            None,
            MutationMeta("corr:start", "idem:start", "test"),
        )
    )
    session_id = started["session"]["assessment_session_id"]
    await commands.save_response(
        SaveAssessmentResponseCommand(
            "family-1",
            "tenant-1",
            "guardian-1",
            session_id,
            "FOCUS",
            "SINGLE_CHOICE",
            "COMMUNICATION",
            MutationMeta("corr:response", "idem:response", "test"),
        )
    )
    await commands.submit(
        SubmitAssessmentCommand(
            "family-1",
            "tenant-1",
            "guardian-1",
            session_id,
            MutationMeta("corr:submit", "idem:submit", "test"),
        )
    )
    composition, provider = await _build_real_composition(
        session_factory,
        broker,
        assessment_ref=session_id,
        runtime_scope=replace(_scope(), subject_ids=(child_id,)),
    )

    async def identity_resolver(family_id, authorization, correlation_id, causation_id):
        if authorization != "Bearer guardian-session":
            raise HTTPException(status_code=401, detail="authenticated identity required")
        return FamilyContext("tenant-1", family_id, "guardian-1")

    async def composition_resolver(identity, authorization, correlation_id, causation_id):
        assert causation_id is None
        assert identity.person_id == "guardian-1"
        assert authorization == "Bearer guardian-session"
        return composition

    app = FastAPI()
    app.include_router(assessment_router, prefix="/families")
    register_exception_handlers(app)
    install_production_assessment_http_wiring(
        app,
        engine=engine,
        identity_resolver=identity_resolver,
        composition_resolver=composition_resolver,
        repository_factory=lambda connection: repository,
    )
    headers = {
        "Authorization": "Bearer guardian-session",
        "X-Correlation-Id": "corr:http-ui03",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        unauthenticated = await client.get("/families/family-1/ui/03/growth-hypothesis")
        assert unauthenticated.status_code == 401
        assert provider.invocations == []

        projection = await client.get(
            "/families/family-1/ui/03/growth-hypothesis",
            headers=headers,
        )
        assert projection.status_code == 200, projection.text
        body = projection.json()
        assert body["ai_state"] == "MODEL_DRAFT_READY"
        assert body["hypothesis"]["subject_person_id"] == child_id

        confirmation = await client.post(
            "/families/family-1/growth-hypotheses/decisions",
            headers={**headers, "Idempotency-Key": "idem:http-confirm"},
            json={
                "assessment_session_id": session_id,
                "hypothesis_ref": body["hypothesis"]["hypothesis_ref"],
                "decision_type": "CONFIRM",
            },
        )

    assert confirmation.status_code == 200, confirmation.text
    receipt = confirmation.json()
    assert receipt["outcome"] == "INTENT_CREATED"
    assert receipt["intent"]["boundary"] == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
    assert len(provider.invocations) == 1


@pytest.mark.asyncio
async def test_sql_identity_resolver_binds_bearer_to_active_guardian(dependencies) -> None:
    engine, session_factory, _ = dependencies
    ddl = (
        "CREATE TABLE accounts (account_id TEXT PRIMARY KEY, status TEXT NOT NULL)",
        "CREATE TABLE identity_sessions (session_id TEXT PRIMARY KEY, account_id TEXT, "
        "account_ref TEXT, family_id TEXT, token_hash TEXT, revoked_at TIMESTAMP, "
        "expires_at TIMESTAMP)",
        "CREATE TABLE tenants (tenant_id TEXT PRIMARY KEY, status TEXT, region_ref TEXT)",
        "CREATE TABLE tenant_account_memberships (account_id TEXT, tenant_id TEXT, role TEXT, "
        "status TEXT, valid_from TIMESTAMP, valid_to TIMESTAMP)",
        "CREATE TABLE tenant_family_bindings (tenant_id TEXT, family_id TEXT, status TEXT, "
        "effective_from TIMESTAMP, effective_to TIMESTAMP)",
        "CREATE TABLE account_person_bindings (account_id TEXT, person_id TEXT, status TEXT)",
        "CREATE TABLE family_memberships (membership_id TEXT, family_id TEXT, person_id TEXT, "
        "status TEXT, role TEXT)",
        "CREATE TABLE persons (person_id TEXT PRIMARY KEY, family_id TEXT, birth_date DATE)",
        "CREATE TABLE consents (consent_id TEXT, family_id TEXT, subject_person_id TEXT, "
        "guardian_person_id TEXT, purpose TEXT, status TEXT, policy_version TEXT, "
        "granted_at TIMESTAMP, withdrawn_at TIMESTAMP)",
    )
    async with engine.begin() as connection:
        for statement in ddl:
            await connection.execute(text(statement))
        await connection.execute(text("INSERT INTO accounts VALUES ('account-1', 'ACTIVE')"))
        await connection.execute(
            text(
                "INSERT INTO identity_sessions VALUES "
                "('session-1', 'account-1', 'account-1', 'family-1', :token_hash, NULL, "
                "'2099-01-01 00:00:00')"
            ),
            {"token_hash": sha256(b"guardian-token").hexdigest()},
        )
        await connection.execute(text("INSERT INTO tenants VALUES ('tenant-1', 'ACTIVE', 'CN')"))
        await connection.execute(
            text(
                "INSERT INTO tenant_account_memberships VALUES "
                "('account-1', 'tenant-1', 'TENANT_OWNER', 'ACTIVE', "
                "'2020-01-01 00:00:00', NULL)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO tenant_family_bindings VALUES "
                "('tenant-1', 'family-1', 'ACTIVE', '2020-01-01 00:00:00', NULL)"
            )
        )
        await connection.execute(
            text("INSERT INTO account_person_bindings VALUES ('account-1', 'guardian-1', 'ACTIVE')")
        )
        await connection.execute(
            text(
                "INSERT INTO family_memberships VALUES "
                "('membership-1', 'family-1', 'guardian-1', 'ACTIVE', 'GUARDIAN')"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO persons VALUES "
                "('11111111-1111-4111-8111-111111111111', 'family-1', '2016-01-01')"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO consents VALUES "
                "('consent-1', 'family-1', '11111111-1111-4111-8111-111111111111', "
                "'guardian-1', 'ASSESSMENT', 'GRANTED', 'assessment-consent.v1', "
                "'2026-01-01 00:00:00', NULL)"
            )
        )

    resolver = SqlAlchemyAssessmentIdentityResolver(engine, session_factory)
    identity = await resolver(
        "family-1",
        "Bearer guardian-token",
        "corr:identity",
        "cause:identity",
    )

    assert identity == FamilyContext("tenant-1", "family-1", "guardian-1")
    context_scope = await SqlAlchemyAssessmentContextScopeResolver(
        engine,
        session_factory,
        "Bearer guardian-token",
        correlation_id="corr:identity",
        causation_id="cause:identity",
    )("family-1", "11111111-1111-4111-8111-111111111111")
    assert context_scope.subject_ids == ("11111111-1111-4111-8111-111111111111",)
    assert context_scope.purpose == "assessment"
    assert context_scope.data_class is DataClass.MINOR_PERSONAL_DATA
    with pytest.raises(HTTPException) as error:
        await resolver("family-1", "Bearer wrong-token", None, None)
    assert error.value.status_code == 401
