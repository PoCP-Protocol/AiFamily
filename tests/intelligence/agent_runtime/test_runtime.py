from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.agent_runtime.authorization import (
    AgentAuthorizationError,
)
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AgentTask,
    AuthorizationBudget,
)
from backend.intelligence.agent_runtime.runtime import AgentRuntime, AgentRuntimeError
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.intelligence.prompt_registry.contracts import PromptBundle
from backend.intelligence.prompt_registry.registry import PromptRegistry
from backend.intelligence.schema_registry.contracts import SchemaDefinition
from backend.intelligence.schema_registry.registry import SchemaRegistry


class FakeGenerationPort:
    def __init__(self) -> None:
        self.calls = []

    async def generate_structured(self, request):
        self.calls.append(request)
        return ModelDraft(
            output={"explanation": "draft"},
            provenance=AiProvenance(
                provider_id="fake",
                model="fake-model",
                model_version="v1",
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
                context_snapshot_ref=request.context_snapshot_ref,
                latency_ms=1,
                data_class=request.data_class,
                use_case=request.use_case,
            ),
        )


def definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="parent_advisor",
        name="家长顾问",
        allowed_skills=frozenset({"explain"}),
        allowed_tools=frozenset({"read_context"}),
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        context_policy="guardian_authorized_minimum",
        safety_policy="family_growth_safety_v1",
        human_handoff_policy="high_risk_or_uncertain",
        budget_policy="one_step_default",
    )


NOW = datetime(2026, 8, 30, 0, 30, tzinfo=UTC)


def authorization(*, expires: datetime | None = None, tools: frozenset[str] | None = None):
    issued = datetime(2026, 8, 30, tzinfo=UTC)
    return AgentAuthorization(
        authorization_id="auth-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        allowed_use_cases=frozenset({"assessment_interpretation"}),
        allowed_tools=frozenset({"read_context"}) if tools is None else tools,
        issued_by="guardian-1",
        issued_at=issued,
        expires_at=expires or issued + timedelta(hours=1),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="agent-auth-v1",
        reason="assessment review",
        audit_ref="audit-1",
    )


def task(**overrides) -> AgentTask:
    values = dict(
        request_id="request-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="assessment_interpretation",
        context_snapshot_ref="snapshot-1",
        prompt_version="assessment-v1",
        schema_version="growth-v1",
        data_class="MINOR_PERSONAL_DATA",
        payload={"evidence_refs": ["e-1"]},
        output_schema={"type": "object"},
        input_refs=("assessment-evidence:e-1",),
        requested_tools=frozenset({"read_context"}),
    )
    values.update(overrides)
    return AgentTask(**values)


def registries(*, prompt_status: str = "PUBLISHED", schema_status: str = "PUBLISHED"):
    prompt = PromptBundle(
        prompt_ref="assessment-prompt",
        version="assessment-v1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        template="explain evidence",
        system_policy_ref="family-safety-v1",
        knowledge_refs=(),
        input_contract_ref="assessment-input-v1",
        output_schema_ref="growth-schema",
        safety_policy_version="safety-v1",
        locale="zh-CN",
        author="author",
        reviewer="reviewer" if prompt_status == "PUBLISHED" else None,
        status=prompt_status,
        effective_at=NOW,
        change_reason="drafting" if prompt_status == "REVIEW" else "",
    )
    schema = SchemaDefinition(
        schema_ref="growth-schema",
        version="growth-v1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        object_type="GrowthPerspective",
        json_schema={"type": "object", "properties": {"explanation": {"type": "string"}}},
        status=schema_status,
        effective_at=NOW,
        reviewer="reviewer" if schema_status == "PUBLISHED" else None,
        change_reason="drafting" if schema_status == "REVIEW" else "",
    )
    return PromptRegistry(bundles=(prompt,)), SchemaRegistry(definitions=(schema,))


@pytest.mark.asyncio
async def test_authorized_execution_uses_only_generation_port_and_returns_draft() -> None:
    port = FakeGenerationPort()
    runtime = AgentRuntime(port, [definition()], clock=lambda: NOW)

    result = await runtime.execute(task(), authorization())

    assert result.agent_id == "parent_advisor"
    assert result.draft.status == "DRAFT"
    assert result.may_mutate_business_state is False
    assert len(port.calls) == 1
    assert port.calls[0].request_id == "request-1"
    assert port.calls[0].input_refs == ("assessment-evidence:e-1",)


def test_task_rejects_mutable_or_blank_input_refs() -> None:
    with pytest.raises(ValueError, match="immutable tuple"):
        task(input_refs=["assessment-evidence:e-1"])
    with pytest.raises(ValueError, match="non-empty refs"):
        task(input_refs=("",))


@pytest.mark.asyncio
async def test_missing_authorization_fails_closed_before_provider_invocation() -> None:
    port = FakeGenerationPort()
    runtime = AgentRuntime(port, [definition()], clock=lambda: NOW)

    with pytest.raises(AgentAuthorizationError, match="agent_authorization_missing"):
        await runtime.execute(task(), None)

    assert port.calls == []


@pytest.mark.asyncio
async def test_scope_and_tool_boundaries_fail_closed() -> None:
    port = FakeGenerationPort()
    runtime = AgentRuntime(port, [definition()], clock=lambda: NOW)

    with pytest.raises(AgentAuthorizationError, match="scope_mismatch"):
        await runtime.execute(task(family_id="other-family"), authorization())
    with pytest.raises(AgentAuthorizationError, match="tool_not_authorized"):
        await runtime.execute(task(), authorization(tools=frozenset()))

    assert port.calls == []


@pytest.mark.asyncio
async def test_expired_authorization_fails_closed() -> None:
    port = FakeGenerationPort()
    runtime = AgentRuntime(port, [definition()], clock=lambda: NOW)
    issued = datetime(2026, 8, 30, tzinfo=UTC)

    with pytest.raises(AgentAuthorizationError, match="authorization_expired_or_revoked"):
        await runtime.execute(
            task(),
            authorization(expires=issued + timedelta(minutes=1)),
        )

    assert port.calls == []


@pytest.mark.asyncio
async def test_published_prompt_and_schema_override_client_output_schema() -> None:
    port = FakeGenerationPort()
    prompt_registry, schema_registry = registries()
    runtime = AgentRuntime(
        port,
        [definition()],
        clock=lambda: NOW + timedelta(minutes=1),
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
    )

    await runtime.execute(
        task(output_schema={"type": "string"}, prompt_ref="assessment-prompt"),
        authorization(),
    )

    assert port.calls[0].output_schema["properties"]["explanation"]["type"] == "string"


@pytest.mark.asyncio
async def test_registry_resolution_fails_closed_for_missing_or_unpublished_assets() -> None:
    port = FakeGenerationPort()
    prompt_registry, schema_registry = registries()
    runtime = AgentRuntime(
        port,
        [definition()],
        clock=lambda: NOW + timedelta(minutes=1),
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
    )

    with pytest.raises(RuntimeError, match="prompt_or_schema_resolution_failed"):
        await runtime.execute(task(prompt_ref="unknown"), authorization())

    _, unpublished_schema_registry = registries(schema_status="REVIEW")
    unpublished_runtime = AgentRuntime(
        port,
        [definition()],
        clock=lambda: NOW + timedelta(minutes=1),
        prompt_registry=prompt_registry,
        schema_registry=unpublished_schema_registry,
    )
    with pytest.raises(RuntimeError, match="prompt_or_schema_resolution_failed"):
        await unpublished_runtime.execute(task(prompt_ref="assessment-prompt"), authorization())

    assert port.calls == []


@pytest.mark.asyncio
async def test_registry_binding_mismatch_fails_closed() -> None:
    port = FakeGenerationPort()
    prompt_registry, schema_registry = registries()
    runtime = AgentRuntime(
        port,
        [definition()],
        clock=lambda: NOW + timedelta(minutes=1),
        prompt_registry=prompt_registry,
        schema_registry=schema_registry,
    )
    mismatched_prompt = PromptBundle(
        prompt_ref="other-prompt",
        version="assessment-v1",
        use_case="assessment_interpretation",
        agent_id="parent_advisor",
        template="other",
        system_policy_ref="family-safety-v1",
        knowledge_refs=(),
        input_contract_ref="assessment-input-v1",
        output_schema_ref="other-schema",
        safety_policy_version="safety-v1",
        locale="zh-CN",
        author="author",
        reviewer="reviewer",
        status="PUBLISHED",
        effective_at=NOW,
    )
    prompt_registry.register(mismatched_prompt)

    with pytest.raises(RuntimeError, match="prompt_schema_binding_mismatch"):
        await runtime.execute(task(prompt_ref="other-prompt"), authorization())

    assert port.calls == []


def test_production_composition_can_require_both_registries() -> None:
    with pytest.raises(AgentRuntimeError, match="prompt_and_schema_registries_required"):
        AgentRuntime(FakeGenerationPort(), [definition()], require_registries=True)
