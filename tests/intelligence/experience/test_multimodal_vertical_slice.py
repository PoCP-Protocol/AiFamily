from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import (
    MultimodalExperienceCommand,
    MultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
    MultimodalRouteRequest,
)
from backend.intelligence.human_gate.contracts import (
    ActorType,
    DecisionOutcome,
    GateScope,
    GateStatus,
)
from backend.intelligence.human_gate.gate import InMemoryHumanGate
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.model_gateway.test_fail_closed import build


def _command() -> MultimodalExperienceCommand:
    return MultimodalExperienceCommand(
        run_id="run-vertical-001",
        provider_id="placeholder",
        use_case="family-image-summary",
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        data_class="SYNTHETIC",
        context_snapshot_ref="ctx:vertical-001",
        payload={"media_ref": "fixture:image-001"},
        output_schema={
            "type": "object",
            "required": ["action"],
            "properties": {"action": {"type": "string"}},
        },
    )


def _route_request() -> MultimodalRouteRequest:
    return MultimodalRouteRequest(
        use_case="family-image-summary",
        data_class="SYNTHETIC",
        modalities=("TEXT", "IMAGE"),
        environment="test",
        estimated_input_tokens=500,
    )


def _service() -> RoutedMultimodalExperienceService:
    provider = FakeProvider({"family-image-summary": {"action": "start"}})
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id="fake-deterministic",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
    )
    return RoutedMultimodalExperienceService(
        router=MultimodalRouter((profile,)),
        generation=MultimodalExperienceService(build(provider)),
    )


def _scope() -> GateScope:
    return GateScope(
        tenant_id="tenant-a",
        family_id="family-a",
        subject_ids=("guardian-a", "child-a"),
        purpose="growth_action",
        consent_version="consent-v1",
        correlation_id="corr:vertical-001",
    )


@pytest.mark.asyncio
async def test_draft_to_human_gate_to_named_action_request() -> None:
    routed = await _service().generate_draft(_command(), _route_request())
    gate = InMemoryHumanGate()

    task = gate.submit_model_draft(
        routed.experience.draft,
        draft_id="draft:vertical-001",
        proposal_id="proposal:vertical-001",
        action_name="START_GROWTH_ACTION",
        action_arguments={"run_id": routed.run_id, "action": routed.output["action"]},
        scope=_scope(),
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="LOW",
        provenance_ref="prov:vertical-001",
        now=datetime(2026, 8, 30, tzinfo=UTC),
    )
    assert task.status is GateStatus.OPEN

    decided, action_request = gate.decide(
        task.task_id,
        actor_id="guardian-a",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
        now=datetime(2026, 8, 30, 0, 1, tzinfo=UTC),
    )
    assert decided.status is GateStatus.DECIDED
    assert action_request is not None
    assert action_request.action_name == "START_GROWTH_ACTION"
    assert action_request.actor_type is ActorType.GUARDIAN

    replayed, replayed_request = gate.decide(
        task.task_id,
        actor_id="guardian-a",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
        now=datetime(2026, 8, 30, 0, 2, tzinfo=UTC),
    )
    assert replayed == decided
    assert replayed_request == action_request


@pytest.mark.asyncio
async def test_human_gate_escalation_does_not_create_domain_action() -> None:
    routed = await _service().generate_draft(_command(), _route_request())
    gate = InMemoryHumanGate()
    task = gate.submit_model_draft(
        routed.experience.draft,
        draft_id="draft:vertical-002",
        proposal_id="proposal:vertical-002",
        action_name="START_GROWTH_ACTION",
        action_arguments={"run_id": routed.run_id},
        scope=_scope(),
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="MEDIUM",
        provenance_ref="prov:vertical-002",
    )

    decided, action_request = gate.decide(
        task.task_id,
        actor_id="guardian-a",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ESCALATE,
        reason="需要专业人员先看一下",
    )
    assert decided.status is GateStatus.DECIDED
    assert decided.decision is not None
    assert decided.decision.outcome is DecisionOutcome.ESCALATE
    assert action_request is None
