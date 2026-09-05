from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AuthorizationBudget,
)
from backend.intelligence.tool_runtime import (
    ToolAuthorization,
    ToolCallRequest,
    ToolDefinition,
    ToolRuntime,
    ToolRuntimeError,
)

NOW = datetime(2026, 8, 30, 1, 0, tzinfo=UTC)


class FakeTool:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def prepare_named_action(self, definition, request):
        self.calls.append((definition.tool_id, dict(request.input_payload)))
        return {"candidate": "prepared"}


def definition() -> ToolDefinition:
    return ToolDefinition(
        tool_id="create_growth_plan",
        name="成长计划候选生成器",
        description="Prepare a plan candidate for human review",
        input_schema={"type": "object"},
        action_name="CREATE_GROWTH_PLAN",
        allowed_use_cases=frozenset({"growth_planning"}),
        risk_level="HIGH",
    )


def agent_definition(*, tools=frozenset({"create_growth_plan"})) -> AgentDefinition:
    return AgentDefinition(
        agent_id="planner",
        name="成长计划 Agent",
        allowed_tools=tools,
        allowed_use_cases=frozenset({"growth_planning"}),
        context_policy="family_context",
        safety_policy="family_safety",
        human_handoff_policy="human_gate",
        budget_policy="one_step",
    )


def agent_authorization(*, tools=frozenset({"create_growth_plan"})) -> AgentAuthorization:
    return AgentAuthorization(
        authorization_id="agent-auth-1",
        agent_id="planner",
        tenant_id="tenant-1",
        family_id="family-1",
        allowed_use_cases=frozenset({"growth_planning"}),
        allowed_tools=tools,
        issued_by="guardian-1",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=30),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="agent-auth-v1",
        reason="prepare candidate",
        audit_ref="audit-1",
    )


def tool_authorization(*, expires_at: datetime | None = None) -> ToolAuthorization:
    return ToolAuthorization(
        authorization_id="tool-auth-1",
        agent_authorization_id="agent-auth-1",
        tool_id="create_growth_plan",
        agent_id="planner",
        tenant_id="tenant-1",
        family_id="family-1",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=expires_at or NOW + timedelta(minutes=10),
        audit_ref="tool-audit-1",
    )


def request(**overrides) -> ToolCallRequest:
    values = dict(
        call_id="call-1",
        agent_id="planner",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="growth_planning",
        tool_id="create_growth_plan",
        context_snapshot_ref="snapshot-1",
        provenance_ref="agent-run-1",
        input_payload={"goal": "家庭共读"},
        subject_ids=("child-1",),
    )
    values.update(overrides)
    return ToolCallRequest(**values)


@pytest.mark.asyncio
async def test_tool_call_only_returns_pending_human_action() -> None:
    tool = FakeTool()
    runtime = ToolRuntime(
        tool, [definition()], agent_definitions=[agent_definition()], clock=lambda: NOW
    )

    result = await runtime.execute(request(), agent_authorization(), tool_authorization())

    assert result.status == "PENDING_HUMAN_CONFIRMATION"
    assert result.requires_human_confirmation is True
    assert result.may_mutate_business_state is False
    assert result.pending_action.action_name == "CREATE_GROWTH_PLAN"
    assert result.pending_action.scope.family_id == "family-1"
    assert tool.calls == [("create_growth_plan", {"goal": "家庭共读"})]


@pytest.mark.asyncio
async def test_agent_authorization_whitelist_is_enforced_before_tool_invocation() -> None:
    tool = FakeTool()
    runtime = ToolRuntime(
        tool, [definition()], agent_definitions=[agent_definition()], clock=lambda: NOW
    )

    with pytest.raises(ToolRuntimeError, match="AGENT_AUTHORIZATION_DENIED"):
        await runtime.execute(
            request(), agent_authorization(tools=frozenset()), tool_authorization()
        )

    assert tool.calls == []


@pytest.mark.asyncio
async def test_missing_or_expired_tool_lease_fails_closed() -> None:
    tool = FakeTool()
    runtime = ToolRuntime(
        tool, [definition()], agent_definitions=[agent_definition()], clock=lambda: NOW
    )

    with pytest.raises(ToolRuntimeError, match="TOOL_AUTHORIZATION_MISSING"):
        await runtime.execute(request(), agent_authorization(), None)
    with pytest.raises(ToolRuntimeError, match="TOOL_AUTHORIZATION_EXPIRED_OR_REVOKED"):
        await runtime.execute(
            request(), agent_authorization(), tool_authorization(expires_at=NOW)
        )

    assert tool.calls == []


@pytest.mark.asyncio
async def test_static_agent_definition_whitelist_is_enforced() -> None:
    tool = FakeTool()
    runtime = ToolRuntime(
        tool,
        [definition()],
        agent_definitions=[agent_definition(tools=frozenset())],
        clock=lambda: NOW,
    )

    with pytest.raises(ToolRuntimeError, match="AGENT_AUTHORIZATION_DENIED"):
        await runtime.execute(request(), agent_authorization(), tool_authorization())

    assert tool.calls == []


def test_tool_definition_rejects_generic_action_and_result_is_immutable() -> None:
    with pytest.raises(ValueError, match="explicit Named Action"):
        ToolDefinition(
            tool_id="bad",
            name="bad",
            description="bad",
            input_schema={},
            action_name="UPDATE",
            allowed_use_cases=frozenset({"growth_planning"}),
        )
