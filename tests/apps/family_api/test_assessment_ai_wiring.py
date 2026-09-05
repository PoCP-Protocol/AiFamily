from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.assessment_ai_wiring import (
    AssessmentAiAssets,
    AssessmentAiInterpretationAdapter,
    SqlAlchemyAssessmentAuthorizationResolver,
)
from backend.domains.assessment.domain.entities import GrowthHypothesisEvidence
from backend.domains.assessment.domain.errors import AssessmentValidationError
from backend.intelligence.agent_runtime.authorization_persistence import (
    AgentAuthorizationPersistenceBase,
    SqlAlchemyAgentAuthorizationLeaseStore,
)
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentRun,
    AuthorizationBudget,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.sql_store import (
    AsyncSqlContextBroker,
    ContextPersistenceBase,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _scope(*, family_id: str = "family-1") -> ContextScope:
    return ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id=family_id,
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


class RecordingRuntime:
    def __init__(self, scope: ContextScope, *, bad_construct: bool = False) -> None:
        self.scope = scope
        self.bad_construct = bad_construct
        self.calls = []
        self.last_run = None

    async def execute(self, task, authorization, *, idempotency_key):
        self.calls.append((task, authorization, idempotency_key))
        construct_ref = "UNREVIEWED" if self.bad_construct else "PARENT_CHILD_COMMUNICATION"
        self.last_run = AgentRun(
            run_id="agent-run-1",
            request_id=task.request_id,
            agent_id=task.agent_id,
            tenant_id=task.tenant_id,
            family_id=task.family_id,
            use_case=task.use_case,
            draft=ModelDraft(
                output={
                    "model_component_ref": "FAMILY_ASSESSMENT_V1",
                    "assessment_ref": "session-1",
                    "boundary_labels": [
                        "hypothesis_not_fact",
                        "recommendation_not_decision",
                    ],
                    "need_summary": [{"need_ref": "COMMUNICATION_SUPPORT"}],
                    "construct_signals": [
                        {"construct_ref": construct_ref, "boundary": "signal_not_diagnosis"}
                    ],
                    "hypotheses": [
                        {
                            "hypothesis_ref": "session-1:H1",
                            "boundary": "hypothesis_not_fact",
                            "construct_refs": [construct_ref],
                            "is_primary_contradiction": True,
                            "contradiction_rank": 1,
                        }
                    ],
                    "action_candidates": [
                        {
                            "action_ref": "COMMUNICATION_SUPPORT:ACTION",
                            "boundary": "recommendation_not_decision",
                        }
                    ],
                },
                provenance=AiProvenance(
                    provider_id="approved-provider",
                    model="multimodal-family-model",
                    model_version="2026-09",
                    prompt_version=task.prompt_version,
                    schema_version=task.schema_version,
                    context_snapshot_ref=task.context_snapshot_ref,
                    latency_ms=12,
                    data_class=task.data_class,
                    use_case=task.use_case,
                    generated_at=NOW,
                ),
            ),
            started_at=NOW,
            completed_at=NOW,
        )
        return self.last_run


class RuntimeReplayResolver:
    def __init__(self, runtime: RecordingRuntime) -> None:
        self.runtime = runtime

    async def __call__(self, request_id, scope):
        run = self.runtime.last_run
        if run is None or run.request_id != request_id:
            return None
        assert run.tenant_id == scope.tenant_id
        assert run.family_id == scope.family_id
        return run


class Resolver:
    def __init__(self, runtime: RecordingRuntime) -> None:
        self.runtime = runtime

    async def resolve(self, family_id: str):
        return self.runtime


def _authorization(agent_id, scope, evidence):
    assert evidence.assessment_evidence_id == "evidence-1"
    return AgentAuthorization(
        authorization_id="authorization-1",
        agent_id=agent_id,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        allowed_tools=frozenset({"read_context"}),
        issued_by="guardian-1",
        issued_at=NOW - timedelta(minutes=10),
        expires_at=NOW + timedelta(minutes=50),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="assessment-agent-auth.v1",
        reason="guardian requested assessment perspective",
        audit_ref="audit:guardian-1",
    )


def _assets() -> AssessmentAiAssets:
    return AssessmentAiAssets(
        prompt_ref="assessment_interpretation_v1",
        prompt_version="1.0.0",
        schema_ref="growth_perspective_v1",
        schema_version="1.0.0",
        reviewed_construct_refs=frozenset({"PARENT_CHILD_COMMUNICATION"}),
    )


@pytest.fixture
async def broker(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'assessment-context.db'}")
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
async def test_assessment_evidence_reaches_context_principal_and_agent_as_draft(broker) -> None:
    runtime = RecordingRuntime(_scope())
    adapter = AssessmentAiInterpretationAdapter(
        runtime_resolver=Resolver(runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        clock=lambda: NOW,
    )

    result = await adapter.interpret("family-1", _evidence())

    task, authorization, idempotency_key = runtime.calls[0]
    assert task.agent_id == "parent_advisor"
    assert task.use_case == "assessment_interpretation"
    assert task.data_class == "MINOR_PERSONAL_DATA"
    assert task.input_refs == (
        "assessment-evidence:evidence-1",
        "assessment-session:session-1",
        "assessment-response:response-1",
    )
    assert task.requested_tools == frozenset({"read_context"})
    assert task.payload["output_boundary"] == "perspective_draft_only"
    assert authorization.issued_by == "guardian-1"
    assert idempotency_key.endswith(task.request_id)
    snapshot = await broker.read(task.context_snapshot_ref, runtime.scope, now=NOW)
    assert set(task.input_refs).issubset(snapshot.source_refs)
    assert result["interpretation"]["generator"] == "MODEL_GATEWAY"
    assert result["scorecard"]["draft_status"] == "DRAFT"


@pytest.mark.asyncio
async def test_exact_assessment_observation_replay_is_safe(broker) -> None:
    runtime = RecordingRuntime(_scope())
    adapter = AssessmentAiInterpretationAdapter(
        runtime_resolver=Resolver(runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        run_replay_resolver=RuntimeReplayResolver(runtime),
        clock=lambda: NOW,
    )

    await adapter.interpret("family-1", _evidence())
    await adapter.interpret("family-1", _evidence())

    assert len(runtime.calls) == 1


@pytest.mark.asyncio
async def test_unreviewed_construct_fails_closed_after_model_draft(broker) -> None:
    runtime = RecordingRuntime(_scope(), bad_construct=True)
    adapter = AssessmentAiInterpretationAdapter(
        runtime_resolver=Resolver(runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        clock=lambda: NOW,
    )

    with pytest.raises(AssessmentValidationError, match="construct_ref_not_in_reviewed_registry"):
        await adapter.interpret("family-1", _evidence())


@pytest.mark.asyncio
async def test_scope_or_expired_evidence_fails_before_agent_execution(broker) -> None:
    wrong_scope_runtime = RecordingRuntime(_scope(family_id="family-2"))
    adapter = AssessmentAiInterpretationAdapter(
        runtime_resolver=Resolver(wrong_scope_runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=_assets(),
        clock=lambda: NOW,
    )
    with pytest.raises(PermissionError, match="family scope mismatch"):
        await adapter.interpret("family-1", _evidence())

    runtime = RecordingRuntime(_scope())
    expired_assets = AssessmentAiAssets(
        prompt_ref="assessment_interpretation_v1",
        prompt_version="1.0.0",
        schema_ref="growth_perspective_v1",
        schema_version="1.0.0",
        reviewed_construct_refs=frozenset({"PARENT_CHILD_COMMUNICATION"}),
        observation_retention=timedelta(minutes=1),
    )
    expired = AssessmentAiInterpretationAdapter(
        runtime_resolver=Resolver(runtime),
        context_broker=broker,
        authorization_resolver=_authorization,
        assets=expired_assets,
        clock=lambda: NOW,
    )
    with pytest.raises(ValueError, match="RETENTION_EXPIRED"):
        await expired.interpret("family-1", _evidence())
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_sql_authorization_resolver_binds_lease_to_authenticated_actor(
    authorization_session_factory,
) -> None:
    scope = _scope()
    authorization = _authorization("parent_advisor", scope, _evidence())
    async with authorization_session_factory() as session:
        await SqlAlchemyAgentAuthorizationLeaseStore(session).issue(authorization)
        await session.commit()

    resolver = SqlAlchemyAssessmentAuthorizationResolver(
        session_factory=authorization_session_factory,
        actor_id_resolver=lambda: "guardian-1",
        clock=lambda: NOW,
    )
    assert await resolver("parent_advisor", scope, _evidence()) == authorization

    wrong_actor = SqlAlchemyAssessmentAuthorizationResolver(
        session_factory=authorization_session_factory,
        actor_id_resolver=lambda: "other-guardian",
        clock=lambda: NOW,
    )
    with pytest.raises(PermissionError, match="ACTIVE_ASSESSMENT_AGENT_AUTHORIZATION_REQUIRED"):
        await wrong_actor("parent_advisor", scope, _evidence())
