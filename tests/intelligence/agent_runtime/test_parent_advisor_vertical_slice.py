from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.agent_runtime.authorization import AgentAuthorizer
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AgentTask,
    AuthorizationBudget,
)
from backend.intelligence.agent_runtime.gateway_port import ModelGatewayExecutionPort
from backend.intelligence.agent_runtime.runtime import AgentRuntime
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.prompt_registry.contracts import PromptBundle
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.intelligence.schema_registry.contracts import SchemaDefinition
from backend.intelligence.schema_registry.registry import SchemaRegistry

NOW = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)


def _definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="parent_advisor",
        name="家长顾问",
        allowed_skills=frozenset({"explain_evidence"}),
        allowed_tools=frozenset({"read_context"}),
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        context_policy="guardian_authorized_minimum",
        safety_policy="family_growth_safety_v1",
        human_handoff_policy="high_risk_or_uncertain",
        budget_policy="one_step_default",
    )


def _authorization() -> AgentAuthorization:
    return AgentAuthorization(
        authorization_id="auth-parent-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        allowed_tools=frozenset({"read_context"}),
        issued_by="guardian-1",
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="agent-auth-v1",
        reason="family assessment explanation",
        audit_ref="audit-parent-1",
    )


def _task() -> AgentTask:
    return AgentTask(
        request_id="request-parent-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="assessment_interpretation",
        context_snapshot_ref="snapshot-parent-1",
        prompt_version="assessment-v1",
        schema_version="growth-v1",
        data_class="MINOR_PERSONAL_DATA",
        payload={"evidence_refs": ["evidence-1"]},
        output_schema={"type": "object"},
        prompt_ref="assessment-prompt",
        schema_ref="growth-schema",
        requested_tools=frozenset({"read_context"}),
    )


def _registries() -> tuple[PromptRegistry, SchemaRegistry]:
    prompt = PromptBundle(
        prompt_ref="assessment-prompt",
        version="assessment-v1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        template="Explain the evidence in plain language.",
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


def _gateway(provider: FakeProvider) -> ModelGateway:
    record = ProviderRecord(
        provider_id=provider.provider_id,
        vendor="aifamily-test",
        model="fake-parent-advisor",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        sub_delegates=False,
        minor_data_allowed=True,
        security_assessment_ref="synthetic-test",
        processing_agreement_ref="synthetic-test",
        deletion_on_termination_committed=True,
    )
    return ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((record,)),
        safety_runtime=SafetyRuntime(),
    )


@pytest.mark.asyncio
async def test_parent_advisor_runs_through_gateway_safety_and_returns_draft() -> None:
    provider = FakeProvider(
        {
            "assessment_interpretation": {
                "explanation": "根据已确认的证据，建议先讨论早晨流程。",
                "evidence_refs": ["evidence-1"],
            }
        }
    )
    prompt_registry, schema_registry = _registries()
    runtime = AgentRuntime(
        ModelGatewayExecutionPort(_gateway(provider), provider.provider_id),
        [_definition()],
        authorizer=AgentAuthorizer(),
        clock=lambda: NOW + timedelta(minutes=1),
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
        require_registries=True,
    )

    result = await runtime.execute(_task(), _authorization())

    assert result.agent_id == "parent_advisor"
    assert result.draft.status == "DRAFT"
    assert result.draft.requires_human_confirmation is True
    assert len(provider.invocations) == 1
    assert provider.invocations[0].data_class == "MINOR_PERSONAL_DATA"
