"""Gated real-model release check for the FE-S01 AI decision seam.

The input is synthetic and classified as operational text.  This test proves
that the canonical Agent Runtime resolves reviewed execution materials before
the shared Model Gateway invokes the real provider.  Missing credentials are
reported by pytest as NOT_RUN (skip); a fake adapter is never substituted.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import MetaData, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.apps.family_api.production_agent_wiring import ProductionAgentRuntime
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AgentTask,
    AuthorizationBudget,
)
from backend.intelligence.agent_runtime.gateway_port import ModelGatewayExecutionPort
from backend.intelligence.agent_runtime.persistence import (
    AgentRunPersistenceBase,
    AgentRunRow,
)
from backend.intelligence.agent_runtime.runtime import AgentRuntime
from backend.intelligence.context_engine.contracts import (
    ContextScope,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.sql_store import (
    AsyncSqlContextBroker,
    ContextPersistenceBase,
)
from backend.intelligence.experience.execution_materials import (
    ExecutionMaterialBase,
    InMemoryExecutionMaterialRegistry,
    KnowledgeExecutionMaterial,
    SessionPerCallExecutionMaterialResolver,
    SqlAlchemyExecutionMaterialRegistry,
    SystemPolicyMaterial,
)
from backend.intelligence.human_gate.contracts import ActorType, DecisionOutcome, GateStatus
from backend.intelligence.human_gate.persistence import HumanGateBase, HumanTaskRow
from backend.intelligence.model_gateway.attempt_persistence import (
    AttemptPersistenceBase,
    ModelAttemptRow,
    SqlAlchemyAttemptSink,
)
from backend.intelligence.model_gateway.ibm_ica_wiring import (
    IBM_ICA_MODEL_API_KEY_ENV_VAR,
    IBM_ICA_MODEL_BASE_URL_ENV_VAR,
    IBM_ICA_PROVIDER_ID,
    build_livecheck_ibm_ica_gateway,
    ibm_ica_credentials_available,
)
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
    SafetyDecisionRow,
    SqlAlchemySafetyDecisionSink,
)
from backend.intelligence.schema_registry.contracts import SchemaDefinition
from backend.intelligence.schema_registry.registry import SchemaRegistry
from backend.intelligence.schema_registry.sql_registry import (
    SchemaPersistenceBase,
    SqlAlchemySchemaRegistry,
)
from backend.platform.audit.store import AuditBase, read_all_events
from tests.support.postgres import postgres_schema_engine, postgres_test_url

NOW = datetime(2026, 9, 16, tzinfo=UTC)
USE_CASE = "assessment_interpretation"
AGENT_ID = "parent_advisor"
PROMPT_REF = "fe_s01_need_to_micro_action_livecheck"
PROMPT_VERSION = "v1"
SCHEMA_REF = "fe_s01_need_to_micro_action_livecheck_v1"
SCHEMA_VERSION = "v1"
POLICY_REF = "fe_s01_synthetic_policy_v1"
KNOWLEDGE_REF = "fe_s01_synthetic_guidance_v1"

OUTPUT_SCHEMA = {
    "type": "object",
    "required": [
        "hypothesis",
        "recommendation",
        "family_confirmation_ref",
        "limitations",
    ],
    "properties": {
        "hypothesis": {
            "type": "object",
            "required": ["kind", "statement"],
            "properties": {
                "kind": {"type": "string", "enum": ["HYPOTHESIS"]},
                "statement": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        "recommendation": {
            "type": "object",
            "required": ["kind", "micro_action"],
            "properties": {
                "kind": {"type": "string", "enum": ["RECOMMENDATION"]},
                "micro_action": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        "family_confirmation_ref": {"type": "string", "minLength": 1},
        "limitations": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
    },
    "additionalProperties": False,
}


def _registries() -> tuple[PromptRegistry, SchemaRegistry]:
    prompt = PromptBundle(
        prompt_ref=PROMPT_REF,
        version=PROMPT_VERSION,
        use_case=USE_CASE,
        agent_id=AGENT_ID,
        template=(
            "This is a synthetic FE-S01 release check. The family has already "
            "confirmed the stated need. Return exactly one tentative need "
            "hypothesis and one small, optional micro-action recommendation. "
            "Use only HYPOTHESIS and RECOMMENDATION kinds. Never emit a Fact, "
            "Outcome, diagnosis, score, ranking, or certainty claim."
        ),
        system_policy_ref=POLICY_REF,
        knowledge_refs=(KNOWLEDGE_REF,),
        input_contract_ref="fe_s01_synthetic_input_v1",
        output_schema_ref=SCHEMA_REF,
        safety_policy_version="family-safety.v1",
        locale="zh-CN",
        author="fe-s01-eval",
        reviewer="fe-s01-release-reviewer",
        status="PUBLISHED",
        effective_at=NOW - timedelta(minutes=1),
    )
    schema = SchemaDefinition(
        schema_ref=SCHEMA_REF,
        version=SCHEMA_VERSION,
        use_case=USE_CASE,
        agent_id=AGENT_ID,
        object_type="FeS01NeedAndMicroActionDraft",
        json_schema=OUTPUT_SCHEMA,
        forbidden_fields=frozenset(
            {"fact", "outcome", "diagnosis", "family_total_score", "family_ranking"}
        ),
        human_gate_rule="REVIEW_REQUIRED",
        status="PUBLISHED",
        effective_at=NOW - timedelta(minutes=1),
        author="fe-s01-eval",
        reviewer="fe-s01-release-reviewer",
    )
    return PromptRegistry(bundles=(prompt,)), SchemaRegistry(definitions=(schema,))


def _materials() -> InMemoryExecutionMaterialRegistry:
    effective_at = NOW - timedelta(minutes=1)
    return InMemoryExecutionMaterialRegistry(
        policies=(
            SystemPolicyMaterial.build(
                policy_ref=POLICY_REF,
                use_case=USE_CASE,
                agent_id=AGENT_ID,
                content=(
                    "Synthetic evaluation only. Output a non-diagnostic draft "
                    "that remains subject to family review."
                ),
                locale="zh-CN",
                status="PUBLISHED",
                reviewer="fe-s01-release-reviewer",
                effective_at=effective_at,
            ),
        ),
        knowledge=(
            KnowledgeExecutionMaterial.build(
                knowledge_ref=KNOWLEDGE_REF,
                use_case=USE_CASE,
                content=(
                    "A useful micro-action is small, reversible, non-comparative, "
                    "and easy for the family to accept, edit, or reject."
                ),
                source_ref="source:fe-s01-reviewed-synthetic-guidance",
                license_ref="license:aifamily-internal-reviewed-content",
                evidence_level="E3",
                status="PUBLISHED",
                reviewer="fe-s01-release-reviewer",
                effective_at=effective_at,
            ),
        ),
    )


def _definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id=AGENT_ID,
        name="FE-S01 synthetic evaluator",
        allowed_use_cases=frozenset({USE_CASE}),
        context_policy="synthetic_operational_only",
        safety_policy="family-safety.v1",
        human_handoff_policy="review_required",
        budget_policy="one_step",
    )


def _authorization() -> AgentAuthorization:
    return AgentAuthorization(
        authorization_id="fe-s01-real-model-livecheck-auth-v1",
        agent_id=AGENT_ID,
        tenant_id="synthetic-tenant",
        family_id="synthetic-family",
        allowed_use_cases=frozenset({USE_CASE}),
        allowed_tools=frozenset(),
        issued_by="fe-s01-release-gate",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="fe-s01-release-gate.v1",
        reason="synthetic real-model release check",
        audit_ref="audit:fe-s01-real-model-livecheck-v1",
    )


def _task(*, context_snapshot_ref: str = "synthetic-context:fe-s01:v1") -> AgentTask:
    return AgentTask(
        request_id="fe-s01-real-model-livecheck-v1",
        agent_id=AGENT_ID,
        tenant_id="synthetic-tenant",
        family_id="synthetic-family",
        use_case=USE_CASE,
        context_snapshot_ref=context_snapshot_ref,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        data_class="OPERATIONAL_TEXT",
        payload={
            "original_expression": "合成案例：晚间作业迟迟难以开始。",
            "confirmed_need": "合成家庭已确认：先降低开始动作的摩擦。",
            "family_confirmation_ref": "synthetic-confirmation:fe-s01:v1",
        },
        output_schema=OUTPUT_SCHEMA,
        prompt_ref=PROMPT_REF,
        schema_ref=SCHEMA_REF,
        input_refs=("synthetic-confirmation:fe-s01:v1",),
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not ibm_ica_credentials_available(),
    reason=(
        "NOT_RUN: "
        f"{IBM_ICA_MODEL_API_KEY_ENV_VAR} / {IBM_ICA_MODEL_BASE_URL_ENV_VAR} "
        "not set for the FE-S01 real-model release check"
    ),
)
async def test_fe_s01_real_model_need_confirmation_to_micro_action() -> None:
    gateway = build_livecheck_ibm_ica_gateway(env=os.environ, model="gpt-5.6-sol")
    prompt_registry, schema_registry = _registries()
    runtime = AgentRuntime(
        ModelGatewayExecutionPort(gateway, IBM_ICA_PROVIDER_ID),
        definitions=(_definition(),),
        clock=lambda: NOW,
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        execution_material_resolver=_materials(),
        require_registries=True,
    )
    run = await runtime.execute(_task(), _authorization())

    assert run.draft.provenance.provider_id == IBM_ICA_PROVIDER_ID
    assert run.draft.output["hypothesis"]["kind"] == "HYPOTHESIS"
    assert run.draft.output["recommendation"]["kind"] == "RECOMMENDATION"
    assert run.draft.output["family_confirmation_ref"]
    assert {"fact", "outcome"}.isdisjoint(run.draft.output)
    assert run.draft.may_mutate_business_state is False


def _postgres_metadata() -> MetaData:
    metadata = MetaData()
    for base in (
        ContextPersistenceBase,
        PromptPersistenceBase,
        SchemaPersistenceBase,
        ExecutionMaterialBase,
        AgentRunPersistenceBase,
        AttemptPersistenceBase,
        SafetyDecisionPersistenceBase,
        TelemetryPersistenceBase,
        HumanGateBase,
        AuditBase,
    ):
        for table in base.metadata.sorted_tables:
            table.to_metadata(metadata)
    return metadata


@pytest.mark.asyncio
@pytest.mark.skipif(
    not ibm_ica_credentials_available() or postgres_test_url() is None,
    reason="NOT_RUN: FE-S01 real-model PostgreSQL gate requires credentials and Postgres",
)
async def test_fe_s01_real_model_postgres_run_attempt_and_context_readback() -> None:
    async with postgres_schema_engine(_postgres_metadata()) as engine:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        prompt_registry, schema_registry = _registries()
        material_registry = _materials()
        async with sessions() as session, session.begin():
            await SqlAlchemyPromptRegistry(session).register(
                prompt_registry.get(PROMPT_REF, PROMPT_VERSION)
            )
            await SqlAlchemySchemaRegistry(session).register(
                schema_registry.get(SCHEMA_REF, SCHEMA_VERSION)
            )
            sql_materials = SqlAlchemyExecutionMaterialRegistry(session)
            await sql_materials.register_policy(await material_registry.get_policy(POLICY_REF))
            await sql_materials.register_knowledge(
                await material_registry.get_knowledge(KNOWLEDGE_REF)
            )

        scope = ContextScope(
            tenant_id="synthetic-tenant",
            region_id="CN",
            family_id="synthetic-family",
            subject_ids=("synthetic-child",),
            purpose="internal_livecheck",
            consent_version="synthetic-consent.v1",
            consent_granted=True,
            data_class=DataClass.OPERATIONAL_TEXT,
            locale="zh-CN",
            deletion_ref="delete:synthetic-family",
            correlation_id="fe-s01-pg-livecheck",
            causation_id="fe-s01-pg-livecheck",
        )
        broker = AsyncSqlContextBroker(sessions)
        await broker.append(
            StateObservation(
                observation_id="fe-s01-synthetic-confirmation",
                tenant_id=scope.tenant_id,
                family_id=scope.family_id,
                subject_id="synthetic-child",
                dimension="confirmed_need",
                observed_value="synthetic-confirmed-need",
                evidence_refs=("synthetic-confirmation:fe-s01:v1",),
                provenance="synthetic-livecheck",
                observed_at=NOW,
                data_class=scope.data_class,
                purpose=scope.purpose,
                consent_version=scope.consent_version,
                consent_granted=True,
                region_id=scope.region_id,
                locale=scope.locale,
                deletion_ref=scope.deletion_ref,
                correlation_id=scope.correlation_id,
                causation_id=scope.causation_id,
                expires_at=NOW + timedelta(hours=1),
                retention_policy="synthetic-livecheck.v1",
            )
        )
        snapshot = await broker.snapshot(
            subject_id="synthetic-child",
            scope=scope,
            now=NOW,
            snapshot_ttl=timedelta(minutes=10),
        )

        gateway = build_livecheck_ibm_ica_gateway(env=os.environ, model="gpt-5.6-sol")
        runtime = ProductionAgentRuntime(
            scope=scope,
            session_factory=sessions,
            gateway=gateway,
            provider_id=IBM_ICA_PROVIDER_ID,
            registry_path="governance/AI_USE_CASE_REGISTRY.yaml",
            prompt_registry=None,
            schema_registry=None,
            prompt_registry_factory=SqlAlchemyPromptRegistry,
            schema_registry_factory=SqlAlchemySchemaRegistry,
            execution_material_resolver=SessionPerCallExecutionMaterialResolver(sessions),
            attempt_sink_factory=SqlAlchemyAttemptSink,
            safety_sink_factory=SqlAlchemySafetyDecisionSink,
            telemetry_sink_factory=SqlAlchemyTelemetrySink,
            context_broker=broker,
            clock=lambda: NOW,
        )
        run = await runtime.execute(
            _task(context_snapshot_ref=snapshot.snapshot_ref),
            _authorization(),
            idempotency_key="fe-s01-pg-real-model-v1",
        )
        assert run.human_task_ref is not None

        # A new object proves the task/decision path does not rely on process memory.
        restarted_runtime = ProductionAgentRuntime(
            scope=scope,
            session_factory=sessions,
            gateway=gateway,
            provider_id=IBM_ICA_PROVIDER_ID,
            registry_path="governance/AI_USE_CASE_REGISTRY.yaml",
            prompt_registry=None,
            schema_registry=None,
            prompt_registry_factory=SqlAlchemyPromptRegistry,
            schema_registry_factory=SqlAlchemySchemaRegistry,
            execution_material_resolver=SessionPerCallExecutionMaterialResolver(sessions),
            attempt_sink_factory=SqlAlchemyAttemptSink,
            safety_sink_factory=SqlAlchemySafetyDecisionSink,
            telemetry_sink_factory=SqlAlchemyTelemetrySink,
            context_broker=broker,
            clock=lambda: NOW + timedelta(minutes=1),
        )
        decided, action = await restarted_runtime.decide_review(
            run.human_task_ref,
            actor_id="synthetic-guardian",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            decision_id="decision:fe-s01-pg-real-model-v1",
            reason="synthetic guardian accepted the tentative hypothesis",
        )

        restarted_broker = AsyncSqlContextBroker(sessions)
        replayed_context = await restarted_broker.read(
            snapshot.snapshot_ref,
            scope,
            now=NOW + timedelta(minutes=1),
        )
        async with sessions() as session:
            stored_run = await session.scalar(
                select(AgentRunRow).where(AgentRunRow.run_id == run.run_id)
            )
            stored_attempt = await session.scalar(select(ModelAttemptRow))
            safety_rows = tuple((await session.scalars(select(SafetyDecisionRow))).all())
            stored_task = await session.scalar(
                select(HumanTaskRow).where(HumanTaskRow.task_id == run.human_task_ref)
            )
            audit_events = await read_all_events(session, tenant_id=scope.tenant_id)

        assert replayed_context.source_refs == ("synthetic-confirmation:fe-s01:v1",)
        assert stored_run is not None and stored_run.status == "SUCCEEDED"
        assert stored_attempt is not None and stored_attempt.status == "SUCCESS"
        assert stored_attempt.model is not None
        assert {row.stage for row in safety_rows} == {"input", "output"}
        assert stored_task is not None and stored_task.status == GateStatus.DECIDED.value
        assert decided.status is GateStatus.DECIDED
        assert action is not None and action.action_name == "CONFIRM_GROWTH_HYPOTHESIS"
        assert [event.action for event in audit_events] == [
            "CREATE_HUMAN_TASK",
            "DECIDE_HUMAN_TASK",
        ]
        assert run.draft.output["hypothesis"]["kind"] == "HYPOTHESIS"
        assert run.draft.output["recommendation"]["kind"] == "RECOMMENDATION"
