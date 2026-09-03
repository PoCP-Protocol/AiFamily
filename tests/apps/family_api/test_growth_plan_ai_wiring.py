from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio.session import AsyncSession
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.accepted_action_wiring import FGCNAcceptedActionRuntime
from backend.apps.family_api.growth_plan_accepted_action import (
    GrowthPlanAcceptedActionError,
    GrowthPlanAcceptedActionHandler,
)
from backend.apps.family_api.growth_plan_activation_wiring import (
    CONFIRM_JOURNEY_PLAN_ACTION,
    GrowthPlanActivationError,
    JourneyPlanActivationAcceptedActionHandler,
)
from backend.apps.family_api.growth_plan_ai_wiring import (
    GrowthPlanAiAssets,
    GrowthPlanAiDraftAdapter,
    GrowthPlanEvidence,
    SqlAlchemyGrowthPlanAuthorizationResolver,
    growth_plan_draft_schema,
    growth_plan_input_refs,
)
from backend.apps.family_api.growth_plan_evidence_reader import (
    GrowthPlanEvidenceConflictError,
    GrowthPlanEvidenceForbiddenError,
    GrowthPlanEvidenceNotFoundError,
    SqlAlchemyGrowthPlanEvidenceReader,
)
from backend.apps.family_api.growth_plan_review_wiring import (
    CREATE_JOURNEY_PLAN_ACTION,
    GrowthPlanDraftReviewRow,
    GrowthPlanHumanGateApplication,
    GrowthPlanReviewBase,
    GrowthPlanReviewError,
    GrowthPlanReviewNotFound,
    SqlAlchemyGrowthPlanDraftRegistry,
)
from backend.apps.family_api.production_agent_wiring import ProductionAgentRuntimeResolver
from backend.apps.family_api.production_growth_plan_ai_wiring import (
    ProductionGrowthPlanAiComposition,
)
from backend.intelligence.agent_runtime.authorization_persistence import (
    AgentAuthorizationPersistenceBase,
    SqlAlchemyAgentAuthorizationLeaseStore,
)
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentRun,
    AuthorizationBudget,
)
from backend.intelligence.agent_runtime.persistence import AgentRunPersistenceBase
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.sql_store import (
    AsyncSqlContextBroker,
    ContextPersistenceBase,
)
from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    GateStatus,
    HumanGateBase,
    SqlAlchemyHumanGate,
)
from backend.intelligence.model_gateway.attempt_persistence import (
    AttemptPersistenceBase,
    SqlAlchemyAttemptSink,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import (
    ModelDraftRegistryBase,
    ModelDraftRow,
)
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
from backend.intelligence.tool_runtime.accepted_delivery import AcceptedActionDeliveryBase
from backend.platform.audit import AuditBase, AuditRecorder

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]


def _scope(*, family_id: str = "family-1", purpose: str = "growth_tracking") -> ContextScope:
    return ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id=family_id,
        subject_ids=("child-1",),
        purpose=purpose,
        consent_version="growth-consent.v2",
        consent_granted=True,
        data_class=DataClass.MINOR_PERSONAL_DATA,
        locale="zh-CN",
        deletion_ref="deletion:child-1",
        correlation_id="correlation:ui05",
        causation_id="growth-onboarding:onboarding-1",
    )


def _evidence(**changes: object) -> GrowthPlanEvidence:
    values = {
        "intent_id": "intent-1",
        "onboarding_id": "onboarding-1",
        "priority_id": "priority-1",
        "subject_person_id": "child-1",
        "need_type": "COMMUNICATION_SUPPORT",
        "goal_text": "希望先减少晚间沟通中的互相催促。",
        "required_capability_keys": ("FAMILY_DIALOGUE",),
        "dimension_id": "R03",
        "confirmed_by_actor_id": "guardian-1",
        "confirmed_at": NOW - timedelta(minutes=5),
        "priority_confirmed_by_actor_id": "guardian-1",
        "priority_confirmed_at": NOW - timedelta(minutes=3),
    }
    values.update(changes)
    return GrowthPlanEvidence(**values)


def _draft_output() -> dict[str, object]:
    stages = [
        ("SEE", "先看见当前节奏", "记录一次平静沟通发生的时间。"),
        ("PARENT_FIRST", "家长先做一点改变", "用一句观察替代催促。"),
        ("CO_CREATE", "一起商量", "共同选择一个十分钟家庭时段。"),
        ("STABILIZE", "留下适合这个家的方法", "选出一项愿意继续的约定。"),
    ]
    return {
        "draft_status": "DRAFT",
        "intent_ref": "intent-1",
        "onboarding_ref": "onboarding-1",
        "priority_ref": "priority-1",
        "horizon_days": 90,
        "boundary_labels": [
            "plan_draft_not_active",
            "recommendation_not_outcome",
            "guardian_confirmation_required",
            "pause_without_penalty",
        ],
        "stages": [
            {
                "stage_id": stage_id,
                "goal": goal,
                "small_actions": [action],
                "review_prompt": "这一步对家庭来说是否舒服、可继续？",
                "evidence_refs": [],
            }
            for stage_id, goal, action in stages
        ],
        "pause_policy": {"allowed": True, "streak_penalty": False},
        "evidence_refs": [],
        "limitations": ["这是可编辑的计划草案，不代表成长结果。"],
    }


class RecordingRuntime:
    def __init__(self, scope: ContextScope, *, output: dict[str, object] | None = None):
        self.scope = scope
        self.output = output or _draft_output()
        self.calls = []
        self.last_run = None

    async def execute(self, task, authorization, *, idempotency_key):
        self.calls.append((task, authorization, idempotency_key))
        output = {
            **self.output,
            "evidence_refs": [task.input_refs[0], task.input_refs[2]],
            "stages": [
                {
                    **stage,
                    "evidence_refs": [task.input_refs[0], task.input_refs[2]],
                }
                for stage in self.output["stages"]
            ],
        }
        self.last_run = AgentRun(
            run_id="agent-run-plan-1",
            request_id=task.request_id,
            agent_id=task.agent_id,
            tenant_id=task.tenant_id,
            family_id=task.family_id,
            use_case=task.use_case,
            draft=ModelDraft(
                output=output,
                provenance=AiProvenance(
                    provider_id="approved-test-provider",
                    model="multimodal-family-model",
                    model_version="2026-09",
                    prompt_version=task.prompt_version,
                    schema_version=task.schema_version,
                    context_snapshot_ref=task.context_snapshot_ref,
                    latency_ms=15,
                    data_class=task.data_class,
                    use_case=task.use_case,
                    generated_at=NOW,
                ),
            ),
            started_at=NOW,
            completed_at=NOW,
        )
        return self.last_run


class RuntimeResolver:
    def __init__(self, runtime: RecordingRuntime):
        self.runtime = runtime

    async def resolve(self, family_id: str):
        return self.runtime


class RecordingJourneyDraftApplication:
    def __init__(self, status: str = "DRAFT"):
        self.status = status
        self.calls = []
        self.current_status = status

    async def create(
        self,
        actor,
        onboarding_id,
        priority_id,
        idempotency_key,
        correlation_id,
    ):
        self.calls.append((actor, onboarding_id, priority_id, idempotency_key, correlation_id))
        self.current_status = self.status
        return {
            "family_id": actor.family_id,
            "plan": {"plan_id": "journey-plan-1", "status": self.status},
            "model_gateway_status": "NOOP",
        }

    async def get_current(self, actor):
        return {
            "family_id": actor.family_id,
            "plan": {"plan_id": "journey-plan-1", "status": self.current_status},
        }

    async def confirm(self, actor, plan_id, idempotency_key, correlation_id):
        self.calls.append((actor, plan_id, idempotency_key, correlation_id))
        self.current_status = "ACTIVE"
        return {
            "family_id": actor.family_id,
            "plan": {"plan_id": plan_id, "status": "ACTIVE"},
        }


class RecordingJourneyActivationApplication:
    def __init__(self, *, current_status: str = "DRAFT", confirmed_status: str = "ACTIVE"):
        self.current_status = current_status
        self.confirmed_status = confirmed_status
        self.calls = []

    async def get_current(self, actor):
        return {
            "family_id": actor.family_id,
            "plan": {"plan_id": "journey-plan-1", "status": self.current_status},
        }

    async def confirm(
        self,
        actor,
        plan_id,
        idempotency_key,
        correlation_id,
    ):
        self.calls.append((actor, plan_id, idempotency_key, correlation_id))
        return {
            "family_id": actor.family_id,
            "plan": {"plan_id": plan_id, "status": self.confirmed_status},
        }


class RecordingDailyActionInitializer:
    def __init__(self):
        self.calls = []

    async def initialize_from_ai_plan(self, **kwargs):
        self.calls.append(kwargs)
        return {"task_id": "action-1"}


class ReplayResolver:
    def __init__(self, runtime: RecordingRuntime):
        self.runtime = runtime

    async def __call__(self, request_id, scope):
        run = self.runtime.last_run
        if run is None or run.request_id != request_id:
            return None
        assert run.family_id == scope.family_id
        return run


def _authorization(agent_id, scope, evidence):
    assert evidence.intent_id == "intent-1"
    return AgentAuthorization(
        authorization_id="growth-plan-auth-1",
        agent_id=agent_id,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        allowed_use_cases=frozenset({"growth_plan_draft"}),
        allowed_tools=frozenset({"read_context"}),
        issued_by="guardian-1",
        issued_at=NOW - timedelta(minutes=10),
        expires_at=NOW + timedelta(hours=1),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="growth-plan-auth.v1",
        reason="guardian requested a plan draft",
        audit_ref="audit:growth-plan-auth-1",
    )


def _assets() -> GrowthPlanAiAssets:
    return GrowthPlanAiAssets(
        prompt_ref="journey_plan_v1",
        prompt_version="1.0.0",
        schema_ref="journey_plan_preview_v1",
        schema_version="1.0.0",
        journey_template_ref="family-growth-90d",
        journey_template_version="1.0.0",
        release_set_ref="family-growth-release-set:staging:1",
        runtime_config_digest="runtime-config-sha256:plan-v1",
    )


def _evidence_row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "intent_id": "intent-1",
        "onboarding_id": "onboarding-1",
        "priority_id": "priority-1",
        "subject_person_id": "child-1",
        "need_type": "COMMUNICATION_SUPPORT",
        "goal_text": "希望先减少晚间沟通中的互相催促。",
        "required_capability_keys": ["FAMILY_DIALOGUE"],
        "dimension_id": "R03",
        "intent_confirmed_by": "guardian-1",
        "intent_confirmed_at": NOW - timedelta(minutes=5),
        "intent_boundary": "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME",
        "priority_confirmed_by": "guardian-2",
        "priority_confirmed_at": NOW - timedelta(minutes=3),
        "onboarding_version": 7,
        "priority_policy_version": "PRIORITY_POLICY_FROM_DATABASE_V3",
    }
    row.update(changes)
    return row


class _EvidenceResult:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _EvidenceSession(AsyncSession):
    rows: list[dict[str, object]] = []
    statements: list[str] = []
    parameters: list[dict[str, object]] = []

    async def execute(self, statement, params=None, **kwargs):
        type(self).statements.append(str(statement))
        type(self).parameters.append(dict(params or {}))
        return _EvidenceResult(type(self).rows)


def _evidence_reader(rows: list[dict[str, object]]) -> SqlAlchemyGrowthPlanEvidenceReader:
    _EvidenceSession.rows = rows
    _EvidenceSession.statements = []
    _EvidenceSession.parameters = []
    factory = async_sessionmaker(class_=_EvidenceSession, expire_on_commit=False)
    return SqlAlchemyGrowthPlanEvidenceReader(factory, lambda: "guardian-1")


@pytest.fixture
async def broker(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'plan-context.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(ContextPersistenceBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield AsyncSqlContextBroker(session_factory)
    finally:
        await engine.dispose()


@pytest.fixture
async def authorization_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(AgentAuthorizationPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirmed_intent_reaches_growth_planner_as_ui05_draft(broker) -> None:
    runtime = RecordingRuntime(_scope())
    adapter = GrowthPlanAiDraftAdapter(
        runtime_resolver=RuntimeResolver(runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        clock=lambda: NOW,
    )

    projection = await adapter.generate("family-1", _evidence())

    task, authorization, idempotency_key = runtime.calls[0]
    assert task.agent_id == "growth_planner"
    assert task.use_case == "growth_plan_draft"
    assert task.input_refs[0].startswith("growth-intent:intent-1:")
    assert task.input_refs[1] == "growth-onboarding:onboarding-1:v1"
    assert task.input_refs[2].startswith("growth-priority:priority-1:M2_104_DETERMINISTIC_V2:")
    assert task.input_refs[3] == "journey-template:family-growth-90d@1.0.0"
    assert task.requested_tools == frozenset({"read_context"})
    assert task.payload["output_boundary"] == "plan_draft_only"
    assert authorization.issued_by == "guardian-1"
    assert idempotency_key.endswith(task.request_id)
    snapshot = await broker.read(task.context_snapshot_ref, runtime.scope, now=NOW)
    assert set(task.input_refs).issubset(snapshot.source_refs)
    assert projection["state"] == "FAMILY_REVIEW"
    assert projection["ai_state"] == "MODEL_DRAFT_READY"
    assert projection["scorecard"]["draft_status"] == "DRAFT"


@pytest.mark.asyncio
async def test_exact_growth_plan_request_replays_same_agent_draft(broker) -> None:
    runtime = RecordingRuntime(_scope())
    adapter = GrowthPlanAiDraftAdapter(
        runtime_resolver=RuntimeResolver(runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        run_replay_resolver=ReplayResolver(runtime),
        clock=lambda: NOW,
    )

    first = await adapter.generate("family-1", _evidence())
    second = await adapter.generate("family-1", _evidence())

    assert first == second
    assert len(runtime.calls) == 1


@pytest.mark.asyncio
async def test_request_identity_changes_with_scope_and_release_set(broker) -> None:
    first_runtime = RecordingRuntime(_scope())
    first = GrowthPlanAiDraftAdapter(
        runtime_resolver=RuntimeResolver(first_runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        clock=lambda: NOW,
    )
    await first.generate("family-1", _evidence())

    scoped_runtime = RecordingRuntime(_scope(family_id="family-2"))
    scoped = GrowthPlanAiDraftAdapter(
        runtime_resolver=RuntimeResolver(scoped_runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        clock=lambda: NOW,
    )
    await scoped.generate("family-2", _evidence())

    release_runtime = RecordingRuntime(_scope())
    release = GrowthPlanAiDraftAdapter(
        runtime_resolver=RuntimeResolver(release_runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=replace(_assets(), release_set_ref="family-growth-release-set:staging:2"),
        clock=lambda: NOW,
    )
    await release.generate("family-1", _evidence())

    request_ids = {
        first_runtime.calls[0][0].request_id,
        scoped_runtime.calls[0][0].request_id,
        release_runtime.calls[0][0].request_id,
    }
    assert len(request_ids) == 3


@pytest.mark.asyncio
async def test_scope_and_forbidden_gamification_fail_closed(broker) -> None:
    wrong_scope = RecordingRuntime(_scope(family_id="family-2"))
    adapter = GrowthPlanAiDraftAdapter(
        runtime_resolver=RuntimeResolver(wrong_scope),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        clock=lambda: NOW,
    )
    with pytest.raises(PermissionError, match="family scope mismatch"):
        await adapter.generate("family-1", _evidence())
    assert wrong_scope.calls == []

    output = _draft_output()
    output["family_total_score"] = 100
    unsafe = RecordingRuntime(_scope(), output=output)
    adapter = GrowthPlanAiDraftAdapter(
        runtime_resolver=RuntimeResolver(unsafe),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        clock=lambda: NOW,
    )
    with pytest.raises(ValueError, match="forbidden output"):
        await adapter.generate("family-1", _evidence())


def test_growth_plan_evidence_requires_real_human_confirmation() -> None:
    with pytest.raises(PermissionError, match="HUMAN_CONFIRMATION"):
        _evidence(confirmed_by_actor_id="ai:growth-planner")
    with pytest.raises(PermissionError, match="CONFIRMED_INTENT"):
        _evidence(boundary="AI_INFERRED_INTENT")


@pytest.mark.asyncio
async def test_sql_authorization_is_bound_to_authenticated_guardian(
    authorization_session_factory,
) -> None:
    scope = _scope()
    authorization = _authorization("growth_planner", scope, _evidence())
    async with authorization_session_factory() as session:
        await SqlAlchemyAgentAuthorizationLeaseStore(session).issue(authorization)
        await session.commit()

    resolver = SqlAlchemyGrowthPlanAuthorizationResolver(
        session_factory=authorization_session_factory,
        actor_id_resolver=lambda: "guardian-1",
        clock=lambda: NOW,
    )
    assert (await resolver("growth_planner", scope, _evidence())).authorization_id == (
        "growth-plan-auth-1"
    )

    wrong_actor = SqlAlchemyGrowthPlanAuthorizationResolver(
        session_factory=authorization_session_factory,
        actor_id_resolver=lambda: "guardian-2",
        clock=lambda: NOW,
    )
    with pytest.raises(PermissionError, match="ACTIVE_GROWTH_PLAN"):
        await wrong_actor("growth_planner", scope, _evidence())


@pytest.mark.asyncio
async def test_sql_evidence_reader_resolves_all_identities_from_onboarding() -> None:
    reader = _evidence_reader([_evidence_row()])

    evidence = await reader.load(scope=_scope(), onboarding_id="onboarding-1")

    assert evidence.intent_id == "intent-1"
    assert evidence.priority_id == "priority-1"
    assert evidence.subject_person_id == "child-1"
    assert evidence.onboarding_version == 7
    assert evidence.priority_policy_version == "PRIORITY_POLICY_FROM_DATABASE_V3"
    assert evidence.confirmed_by_actor_id == "guardian-1"
    assert evidence.priority_confirmed_by_actor_id == "guardian-2"
    sql = _EvidenceSession.statements[0].lower()
    assert "growth_onboarding_intent_bindings" in sql
    assert "tenant_family_bindings" in sql
    assert "family_memberships" in sql
    assert "limit 1" not in sql
    assert "gp.rank" not in sql
    assert _EvidenceSession.parameters[0]["onboarding_id"] == "onboarding-1"
    assert "intent_id" not in _EvidenceSession.parameters[0]
    assert "priority_id" not in _EvidenceSession.parameters[0]


@pytest.mark.asyncio
async def test_sql_evidence_reader_fails_closed_for_missing_duplicate_and_scope() -> None:
    with pytest.raises(GrowthPlanEvidenceNotFoundError):
        await _evidence_reader([]).load(scope=_scope(), onboarding_id="onboarding-1")
    with pytest.raises(GrowthPlanEvidenceConflictError, match="NOT_UNIQUE"):
        await _evidence_reader([_evidence_row(), _evidence_row()]).load(
            scope=_scope(), onboarding_id="onboarding-1"
        )
    invalid_scope = replace(_scope(), subject_ids=("child-1", "child-2"))
    reader = _evidence_reader([_evidence_row()])
    with pytest.raises(GrowthPlanEvidenceForbiddenError, match="SINGLE"):
        await reader.load(scope=invalid_scope, onboarding_id="onboarding-1")
    assert _EvidenceSession.statements == []


def test_production_composition_builds_same_durable_adapter(
    broker,
    authorization_session_factory,
) -> None:
    composition = ProductionGrowthPlanAiComposition(
        environment="test",
        session_factory=authorization_session_factory,
        runtime_resolver=RuntimeResolver(RecordingRuntime(_scope())),
        context_broker=broker,
        actor_id_resolver=lambda: "guardian-1",
        assets=_assets(),
        clock=lambda: NOW,
    )

    assert isinstance(composition.build_draft_adapter(), GrowthPlanAiDraftAdapter)
    assert isinstance(composition.build_evidence_reader(), SqlAlchemyGrowthPlanEvidenceReader)
    assert isinstance(composition.build_review_application(), GrowthPlanHumanGateApplication)
    with pytest.raises(ValueError, match="test/staging/production"):
        ProductionGrowthPlanAiComposition(
            environment="development",
            session_factory=authorization_session_factory,
            runtime_resolver=RuntimeResolver(RecordingRuntime(_scope())),
            context_broker=broker,
            actor_id_resolver=lambda: "guardian-1",
            assets=_assets(),
            clock=lambda: NOW,
        )


@pytest.mark.asyncio
async def test_production_composition_invokes_model_gateway_once_and_replays() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        for metadata in (
            ContextPersistenceBase.metadata,
            AgentAuthorizationPersistenceBase.metadata,
            AgentRunPersistenceBase.metadata,
            AttemptPersistenceBase.metadata,
            SafetyDecisionPersistenceBase.metadata,
            TelemetryPersistenceBase.metadata,
            ModelDraftRegistryBase.metadata,
            GrowthPlanReviewBase.metadata,
            HumanGateBase.metadata,
            AcceptedActionDeliveryBase.metadata,
            AuditBase.metadata,
        ):
            await connection.run_sync(metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    broker = AsyncSqlContextBroker(session_factory)
    evidence = _evidence()
    assets = _assets()
    input_refs = growth_plan_input_refs(evidence, assets)
    output = _draft_output()
    output["evidence_refs"] = [input_refs[0], input_refs[2]]
    output["stages"] = [
        {**stage, "evidence_refs": [input_refs[0], input_refs[2]]} for stage in output["stages"]
    ]
    provider = FakeProvider({"growth_plan_draft": output})
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
    prompt_registry = PromptRegistry(
        bundles=(
            PromptBundle(
                prompt_ref=assets.prompt_ref,
                version=assets.prompt_version,
                use_case="growth_plan_draft",
                agent_id="growth_planner",
                template="Draft a bounded, evidence-grounded family growth plan.",
                system_policy_ref="family-growth-safety-v1",
                knowledge_refs=(),
                input_contract_ref="confirmed-growth-intent-v1",
                output_schema_ref=assets.schema_ref,
                safety_policy_version="family-growth-safety-v1",
                locale="zh-CN",
                author="product",
                reviewer="reviewer",
                status="PUBLISHED",
                effective_at=NOW - timedelta(days=1),
            ),
        )
    )
    schema_registry = SchemaRegistry(
        definitions=(
            SchemaDefinition(
                schema_ref=assets.schema_ref,
                version=assets.schema_version,
                use_case="growth_plan_draft",
                agent_id="growth_planner",
                object_type="GrowthPlanDraft",
                json_schema=growth_plan_draft_schema(),
                forbidden_fields=frozenset({"family_total_score", "family_ranking"}),
                status="PUBLISHED",
                effective_at=NOW - timedelta(days=1),
                reviewer="reviewer",
            ),
        )
    )
    runtime_resolver = ProductionAgentRuntimeResolver(
        scope_resolver=lambda family_id: _scope(family_id=family_id),
        session_factory=session_factory,
        gateway=gateway,
        provider_id=provider.provider_id,
        registry_path=ROOT / "governance" / "AI_USE_CASE_REGISTRY.yaml",
        attempt_sink_factory=SqlAlchemyAttemptSink,
        safety_sink_factory=SqlAlchemySafetyDecisionSink,
        telemetry_sink_factory=SqlAlchemyTelemetrySink,
        context_broker=broker,
        environment="staging",
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        clock=lambda: NOW,
    )
    async with session_factory() as session:
        await SqlAlchemyAgentAuthorizationLeaseStore(session).issue(
            _authorization("growth_planner", _scope(), evidence)
        )
        await session.commit()
    composition = ProductionGrowthPlanAiComposition(
        environment="staging",
        session_factory=session_factory,
        runtime_resolver=runtime_resolver,
        context_broker=broker,
        actor_id_resolver=lambda: "guardian-1",
        assets=assets,
        clock=lambda: NOW,
    )
    try:
        first = await composition.build_draft_adapter().generate("family-1", evidence)
        replay = await composition.build_draft_adapter().generate("family-1", evidence)
        review_scope = replace(_scope(), correlation_id="correlation:ui05-review")
        task = await composition.build_review_application().submit(
            scope=review_scope, draft_id=first["scorecard"]["draft_id"]
        )
        task_replay = await composition.build_review_application().submit(
            scope=review_scope, draft_id=first["scorecard"]["draft_id"]
        )
        async with session_factory() as session:
            gate = SqlAlchemyHumanGate(session)
            recorder = AuditRecorder()
            decided, named_action = await gate.decide(
                task.task_id,
                actor_id="guardian-1",
                actor_type=ActorType.GUARDIAN,
                outcome=DecisionOutcome.ACCEPT,
                recorder=recorder,
                now=NOW + timedelta(minutes=1),
            )
            await gate.flush_audit(recorder)
            await gate.commit()
        journey = RecordingJourneyDraftApplication()
        daily_action_initializer = RecordingDailyActionInitializer()
        runtime = FGCNAcceptedActionRuntime(
            session_factory=session_factory,
            claim_owner="worker:growth-plan-test",
            growth_plan_scope_resolver=lambda request: replace(
                review_scope,
                correlation_id="correlation:accepted-worker",
            ),
            journey_application=journey,
            growth_plan_daily_action_initializer=daily_action_initializer,
            clock=lambda: NOW + timedelta(minutes=2),
        )
        first_delivery = await runtime.run_until_idle(limit=10, max_polls=2)
        async with session_factory() as session:
            gate = SqlAlchemyHumanGate(session)
            activation_task_id = (
                f"human-task:tenant-1:journey-activation:"
                f"{named_action.action_arguments['draft_digest']}:journey-plan-1"
            )
            activation_task = await gate.get(activation_task_id)
            recorder = AuditRecorder()
            decided_activation, activation_request = await gate.decide(
                activation_task.task_id,
                actor_id="guardian-1",
                actor_type=ActorType.GUARDIAN,
                outcome=DecisionOutcome.ACCEPT,
                recorder=recorder,
                now=NOW + timedelta(minutes=3),
            )
            await gate.flush_audit(recorder)
            await gate.commit()
        second_delivery = await runtime.run_until_idle(limit=10, max_polls=2)
        with pytest.raises(GrowthPlanActivationError, match="REQUIRES_CURRENT_DRAFT"):
            await JourneyPlanActivationAcceptedActionHandler(
                SqlAlchemyGrowthPlanDraftRegistry(session_factory),
                scope_resolver=lambda request: review_scope,
                journey=RecordingJourneyActivationApplication(current_status="ACTIVE"),
                clock=lambda: NOW + timedelta(minutes=4),
            )(activation_request)
        unsafe_handler = GrowthPlanAcceptedActionHandler(
            SqlAlchemyGrowthPlanDraftRegistry(session_factory),
            scope_resolver=lambda request: review_scope,
            journey=RecordingJourneyDraftApplication(status="ACTIVE"),
            clock=lambda: NOW + timedelta(minutes=2),
        )
        with pytest.raises(GrowthPlanAcceptedActionError, match="BOUNDARY_VIOLATED"):
            await unsafe_handler(named_action)
        async with session_factory() as session:
            stored_drafts = tuple(await session.scalars(select(ModelDraftRow)))
        with pytest.raises(GrowthPlanReviewNotFound):
            await composition.build_review_application().submit(
                scope=replace(review_scope, family_id="family-2"),
                draft_id=first["scorecard"]["draft_id"],
            )
        async with session_factory() as session:
            review_row = await session.get(
                GrowthPlanDraftReviewRow,
                {
                    "tenant_id": "tenant-1",
                    "draft_id": first["scorecard"]["draft_id"],
                },
            )
            assert review_row is not None
            review_row.priority_id = "tampered-priority"
            await session.commit()
        with pytest.raises(GrowthPlanReviewError, match="DIGEST_MISMATCH"):
            await composition.build_review_application().submit(
                scope=review_scope,
                draft_id=first["scorecard"]["draft_id"],
            )
    finally:
        await engine.dispose()

    assert first == replay
    assert first["scorecard"]["draft_status"] == "DRAFT"
    assert first["scorecard"]["draft_persistence"] == "DURABLE"
    assert len(provider.invocations) == 1
    assert len(stored_drafts) == 1
    assert task == task_replay
    assert task.status is GateStatus.OPEN
    assert task.proposal.action_name == CREATE_JOURNEY_PLAN_ACTION
    assert task.proposal.allowed_actor_types == ("GUARDIAN",)
    assert task.proposal.scope.correlation_id == "correlation:ui05-review"
    assert task.proposal.action_arguments["draft_id"] == first["scorecard"]["draft_id"]
    assert task.proposal.action_arguments["priority_id"] == "priority-1"
    assert decided.status is GateStatus.DECIDED
    assert named_action is not None
    assert named_action.action_name == CREATE_JOURNEY_PLAN_ACTION
    assert named_action.actor_id == "guardian-1"
    assert named_action.action_arguments["draft_digest"] == task.proposal.proposal_id.removeprefix(
        "growth-plan-proposal:"
    )
    assert first_delivery.succeeded == 1
    assert journey.calls[0][0].actor_id == "guardian-1"
    assert journey.calls[0][1:3] == ("onboarding-1", "priority-1")
    assert activation_task.status is GateStatus.OPEN
    assert activation_task.proposal.action_name == CONFIRM_JOURNEY_PLAN_ACTION
    assert activation_task.proposal.draft_id == "journey-plan-1"
    assert decided_activation.status is GateStatus.DECIDED
    assert activation_request is not None
    assert activation_request.action_name == CONFIRM_JOURNEY_PLAN_ACTION
    assert second_delivery.succeeded == 1
    assert journey.calls[1][0].actor_id == "guardian-1"
    assert journey.current_status == "ACTIVE"
    assert daily_action_initializer.calls[0]["assignment_text"] == "记录一次平静沟通发生的时间。"
    assert daily_action_initializer.calls[0]["source_draft_id"] == first["scorecard"]["draft_id"]
