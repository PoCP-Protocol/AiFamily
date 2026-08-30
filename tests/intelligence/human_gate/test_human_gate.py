from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    GateScope,
    GateStatus,
    HumanGateError,
    InMemoryHumanGate,
)
from backend.intelligence.model_gateway import FakeProvider, ModelGateway
from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    ModelDraft,
    StructuredRequest,
)


def _scope() -> GateScope:
    return GateScope(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ids=("child-1",),
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-1",
    )


def _draft() -> ModelDraft:
    return ModelDraft(
        output={"candidate_provider_id": "provider-1", "reason": "skill match"},
        provenance=AiProvenance(
            provider_id="fake-deterministic",
            model="fake-deterministic",
            model_version="1.0.0",
            prompt_version="service-matching.v1",
            schema_version="service-task-proposal.v1",
            context_snapshot_ref="context:tenant-1:child-1:1",
            latency_ms=1,
            data_class="OPERATIONAL_TEXT",
            use_case="service_matching_recommendation",
        ),
    )


def _submit(
    gate: InMemoryHumanGate,
    *,
    now: datetime | None = None,
    server_clock: bool = False,
):
    resolved_now = None if server_clock else now or datetime(2026, 8, 30, 9, tzinfo=UTC)
    return gate.submit_model_draft(
        _draft(),
        draft_id="draft-1",
        proposal_id="proposal-1",
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments={"service_task_id": "task-1", "provider_id": "provider-1"},
        scope=_scope(),
        allowed_actor_types=(ActorType.GUARDIAN, ActorType.PROFESSIONAL),
        risk_level="HIGH",
        provenance_ref="prov:request-1",
        now=resolved_now,
    )


def test_model_draft_enters_an_open_task_without_executing_a_domain_action():
    gate = InMemoryHumanGate()
    task = _submit(gate)

    assert task.status is GateStatus.OPEN
    assert task.proposal.action_name == "CONFIRM_SERVICE_TASK_ASSIGNMENT"
    assert task.proposal.action_arguments["service_task_id"] == "task-1"
    assert task.proposal.scope.family_id == "family-1"
    assert task.action_request is None


def test_acceptance_requires_a_human_and_returns_only_a_named_action_request():
    gate = InMemoryHumanGate()
    task = _submit(gate)

    decided, request = gate.decide(
        task.task_id,
        actor_id="guardian-1",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
        now=datetime(2026, 8, 30, 10, tzinfo=UTC),
    )

    assert decided.status is GateStatus.DECIDED
    assert request is not None
    assert request.action_name == "CONFIRM_SERVICE_TASK_ASSIGNMENT"
    assert request.actor_id == "guardian-1"
    assert request.scope.tenant_id == "tenant-1"
    assert request.provenance_ref == "prov:request-1"
    assert request.idempotency_key.startswith("tenant-1:")

    replayed, replay_request = gate.decide(
        task.task_id,
        actor_id="guardian-1",
        actor_type="GUARDIAN",
        outcome="ACCEPT",
        now=datetime(2026, 8, 30, 10, tzinfo=UTC),
    )
    assert replayed is decided
    assert replay_request == request

    with pytest.raises(HumanGateError, match="TASK_ALREADY_DECIDED"):
        gate.decide(
            task.task_id,
            actor_id="guardian-2",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
        )


def test_rejection_does_not_create_a_named_action_request():
    gate = InMemoryHumanGate()
    task = _submit(gate)

    decided, request = gate.decide(
        task.task_id,
        actor_id="professional-1",
        actor_type=ActorType.PROFESSIONAL,
        outcome=DecisionOutcome.REJECT,
        reason="The provider is not available in the required time window.",
        now=datetime(2026, 8, 30, 10, tzinfo=UTC),
    )

    assert decided.status is GateStatus.DECIDED
    assert decided.decision is not None
    assert request is None
    assert decided.action_request is None


def test_ai_actor_and_disallowed_human_are_rejected_before_decision():
    gate = InMemoryHumanGate()
    task = _submit(gate)

    with pytest.raises(HumanGateError, match="REVIEWER_NOT_ALLOWED"):
        gate.decide(
            task.task_id,
            actor_id="operator-1",
            actor_type=ActorType.OPERATOR,
            outcome=DecisionOutcome.ACCEPT,
        )

    with pytest.raises(HumanGateError, match="HUMAN_REVIEWER_REQUIRED"):
        gate.decide(
            task.task_id,
            actor_id="agent-1",
            actor_type=ActorType.AI,
            outcome=DecisionOutcome.ACCEPT,
        )

    assert gate.get(task.task_id).status is GateStatus.OPEN


def test_expired_task_is_closed_and_cannot_be_decided():
    gate = InMemoryHumanGate()
    created = datetime(2026, 8, 29, 10, tzinfo=UTC)
    task = _submit(gate, now=created)

    with pytest.raises(HumanGateError, match="TASK_EXPIRED"):
        gate.decide(
            task.task_id,
            actor_id="guardian-1",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            now=created + timedelta(days=1),
        )

    assert gate.get(task.task_id).status is GateStatus.EXPIRED


def test_generic_write_names_are_not_named_actions():
    gate = InMemoryHumanGate()
    with pytest.raises(HumanGateError, match="INVALID_NAMED_ACTION"):
        gate.submit_model_draft(
            _draft(),
            draft_id="draft-1",
            proposal_id="proposal-1",
            action_name="UPDATE",
            action_arguments={},
            scope=_scope(),
            allowed_actor_types=(ActorType.GUARDIAN,),
            risk_level="HIGH",
            provenance_ref="prov:request-1",
        )


def test_proposal_replay_is_idempotent_but_content_reuse_is_rejected():
    gate = InMemoryHumanGate()
    first = _submit(gate)
    replay = _submit(gate)
    assert replay is first

    with pytest.raises(HumanGateError, match="PROPOSAL_REPLAY_MISMATCH"):
        gate.submit_model_draft(
            _draft(),
            draft_id="draft-other",
            proposal_id="proposal-1",
            action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
            action_arguments={"service_task_id": "different-task"},
            scope=_scope(),
            allowed_actor_types=(ActorType.GUARDIAN, ActorType.PROFESSIONAL),
            risk_level="HIGH",
            provenance_ref="prov:request-2",
        )


def test_proposal_replay_does_not_depend_on_server_clock():
    gate = InMemoryHumanGate()
    first = _submit(gate, server_clock=True)
    replay = _submit(gate, server_clock=True)

    assert replay is first


@pytest.mark.asyncio
async def test_model_gateway_draft_flows_into_human_gate_and_named_action_request():
    provider = FakeProvider(
        {
            "service_matching_recommendation": {
                "candidate_provider_id": "provider-1",
                "reason": "skill match",
            }
        }
    )
    gateway = ModelGateway({"fake-deterministic": provider}, environment="test")
    draft = await gateway.generate_structured(
        StructuredRequest(
            use_case="service_matching_recommendation",
            prompt_version="service-matching.v1",
            schema_version="service-task-proposal.v1",
            data_class="OPERATIONAL_TEXT",
            payload={"service_task_id": "task-1"},
            output_schema={
                "type": "object",
                "properties": {
                    "candidate_provider_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["candidate_provider_id", "reason"],
            },
            context_snapshot_ref="context:tenant-1:child-1:1",
            request_id="request-1",
        ),
        provider_id="fake-deterministic",
    )

    gate = InMemoryHumanGate()
    task = gate.submit_model_draft(
        draft,
        draft_id="draft-1",
        proposal_id="proposal-1",
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments={"service_task_id": "task-1", "provider_id": "provider-1"},
        scope=_scope(),
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref="model-draft:request-1",
        now=datetime(2026, 8, 30, 9, tzinfo=UTC),
    )
    decided, request = gate.decide(
        task.task_id,
        actor_id="guardian-1",
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
        now=datetime(2026, 8, 30, 10, tzinfo=UTC),
    )

    assert draft.status == "DRAFT"
    assert draft.may_mutate_business_state is False
    assert decided.status is GateStatus.DECIDED
    assert request is not None
    assert request.action_name == "CONFIRM_SERVICE_TASK_ASSIGNMENT"
    assert request.provenance_ref == "model-draft:request-1"
