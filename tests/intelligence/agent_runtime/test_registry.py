from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.intelligence.agent_runtime import (
    AgentAuthorization,
    AgentAuthorizationError,
    AgentDefinitionRegistry,
    AgentRegistryError,
    AgentRuntime,
    AgentTask,
    AuthorizationBudget,
    DurableAgentRuntime,
    build_agent_runtime,
    build_durable_agent_runtime,
)
from backend.intelligence.model_gateway import FakeProvider
from backend.intelligence.prompt_registry import PromptRegistry
from backend.intelligence.schema_registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = ROOT / "governance" / "AI_USE_CASE_REGISTRY.yaml"


def test_canonical_registry_loads_all_governed_agents() -> None:
    registry = AgentDefinitionRegistry.from_yaml(REGISTRY_PATH)
    definition = registry.require("growth_planner")

    assert len(registry.all()) == 5
    assert definition.allowed_use_cases == frozenset(
        {"growth_hypothesis_prioritization", "growth_plan_draft", "daily_action_proposal"}
    )
    assert definition.may_mutate_business_state is False


def test_runtime_registry_excludes_planned_agents_use_cases_and_tools() -> None:
    registry = AgentDefinitionRegistry.from_yaml(REGISTRY_PATH, runnable_only=True)

    assert {item.agent_id for item in registry.all()} == {
        "parent_advisor",
        "growth_planner",
    }
    assert registry.require("parent_advisor").allowed_use_cases == frozenset(
        {"assessment_interpretation"}
    )
    growth_planner = registry.require("growth_planner")
    assert growth_planner.allowed_use_cases == frozenset({"growth_plan_draft"})
    assert growth_planner.allowed_tools == frozenset({"read_context"})
    with pytest.raises(AgentRegistryError, match="NOT_FOUND"):
        registry.require("child_coach")


@pytest.mark.asyncio
async def test_planned_agent_fails_before_provider_invocation() -> None:
    provider = FakeProvider({"daily_action_proposal": {"never": "called"}})
    runtime = build_agent_runtime(
        generation_port=provider,
        registry_path=REGISTRY_PATH,
        prompt_registry=PromptRegistry(),
        schema_registry=SchemaRegistry(),
        clock=lambda: datetime(2026, 9, 1, tzinfo=UTC),
    )
    task = AgentTask(
        request_id="planned-agent-request",
        agent_id="child_coach",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="daily_action_proposal",
        context_snapshot_ref="context:planned-agent",
        prompt_version="1.0.0",
        schema_version="1.0.0",
        data_class="MINOR_PERSONAL_DATA",
        payload={"human_gate": "EXPLICIT_CONFIRMATION"},
        output_schema={"type": "object"},
        prompt_ref="daily_action_v1",
        schema_ref="daily_action_proposal_v1",
    )
    authorization = AgentAuthorization(
        authorization_id="planned-agent-auth",
        agent_id="child_coach",
        tenant_id="tenant-1",
        family_id="family-1",
        allowed_use_cases=frozenset({"daily_action_proposal"}),
        allowed_tools=frozenset(),
        issued_by="guardian-1",
        issued_at=datetime(2026, 8, 31, tzinfo=UTC),
        expires_at=datetime(2026, 9, 1, tzinfo=UTC) + timedelta(hours=1),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="planned-agent-auth.v1",
        reason="negative governance test",
        audit_ref="audit:planned-agent-auth",
    )

    with pytest.raises(AgentAuthorizationError):
        await runtime.execute(task, authorization)

    assert provider.invocations == []


def test_registry_rejects_mutating_agent_definition() -> None:
    with pytest.raises(AgentRegistryError, match="MUTATION_FORBIDDEN"):
        AgentDefinitionRegistry.from_mapping(
            {
                "agents": [
                    {
                        "id": "bad-agent",
                        "name": "bad",
                        "context_policy": "scope",
                        "safety_policy": "safe",
                        "human_handoff_policy": "human",
                        "budget_policy": "bounded",
                        "allowed_use_cases": ["test"],
                        "allowed_tools": [],
                        "may_mutate_business_state": True,
                    }
                ]
            }
        )


def test_registry_rejects_duplicate_or_malformed_entries() -> None:
    entry = {
        "id": "agent-a",
        "name": "Agent A",
        "context_policy": "scope",
        "safety_policy": "safe",
        "human_handoff_policy": "human",
        "budget_policy": "bounded",
        "allowed_use_cases": ["test"],
        "allowed_tools": [],
        "may_mutate_business_state": False,
    }
    with pytest.raises(AgentRegistryError, match="DUPLICATE"):
        AgentDefinitionRegistry.from_mapping({"agents": [entry, dict(entry)]})
    with pytest.raises(AgentRegistryError, match="AGENTS_REQUIRED"):
        AgentDefinitionRegistry.from_mapping({"agents": []})


def test_composition_factory_requires_governed_registries() -> None:
    runtime = build_agent_runtime(
        generation_port=FakeProvider(),
        registry_path=REGISTRY_PATH,
        prompt_registry=PromptRegistry(),
        schema_registry=SchemaRegistry(),
    )
    assert isinstance(runtime, AgentRuntime)


def test_durable_composition_factory_binds_run_store() -> None:
    durable = build_durable_agent_runtime(
        generation_port=FakeProvider(),
        registry_path=REGISTRY_PATH,
        prompt_registry=PromptRegistry(),
        schema_registry=SchemaRegistry(),
        run_store=object(),  # type: ignore[arg-type]
    )

    assert isinstance(durable, DurableAgentRuntime)
