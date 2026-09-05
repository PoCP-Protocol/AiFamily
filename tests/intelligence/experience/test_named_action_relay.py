from dataclasses import replace

import pytest

from backend.intelligence.experience.human_gate_bridge import ExperienceRunHumanGateBridge
from backend.intelligence.experience.named_action_relay import (
    InMemoryNamedActionRelay,
    RelayConflictError,
    RunBoundNamedActionEnvelope,
)
from backend.intelligence.human_gate import ActorType, DecisionOutcome

from .test_human_gate_bridge import _draft, _run, _scope


@pytest.mark.asyncio
async def test_relay_is_idempotent_and_preserves_run_scope():
    run = _run()
    bridge = ExperienceRunHumanGateBridge()
    task = bridge.submit_model_draft(
        run,
        _draft(),
        draft_id="draft:relay-001",
        proposal_id="proposal:relay-001",
        action_name="START_GROWTH_ACTION",
        action_arguments={"action": "start"},
        scope=_scope(),
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="LOW",
        provenance_ref="model-draft:relay-001",
    )
    _, request = bridge.decide(
        run,
        task.task_id,
        actor_id="guardian-bridge",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
    )
    assert request is not None
    envelope = RunBoundNamedActionEnvelope.from_run(run, request)
    relay = InMemoryNamedActionRelay()
    first = await relay.publish(envelope)
    replay = await relay.publish(envelope)
    assert first.replayed is False
    assert replay.replayed is True
    assert envelope.scope == request.scope
    assert envelope.provenance_ref == request.provenance_ref


@pytest.mark.asyncio
async def test_relay_rejects_same_request_id_with_changed_content():
    run = _run()
    bridge = ExperienceRunHumanGateBridge()
    task = bridge.submit_model_draft(
        run,
        _draft(),
        draft_id="draft:relay-002",
        proposal_id="proposal:relay-002",
        action_name="START_GROWTH_ACTION",
        action_arguments={},
        scope=_scope(),
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="LOW",
        provenance_ref="model-draft:relay-002",
    )
    _, request = bridge.decide(
        run,
        task.task_id,
        actor_id="guardian-bridge",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
    )
    assert request is not None
    relay = InMemoryNamedActionRelay()
    await relay.publish(RunBoundNamedActionEnvelope.from_run(run, request))
    changed = replace(request, provenance_ref="model-draft:tampered")
    with pytest.raises(RelayConflictError):
        await relay.publish(RunBoundNamedActionEnvelope.from_run(run, changed))

