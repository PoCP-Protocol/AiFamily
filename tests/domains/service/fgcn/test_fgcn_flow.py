from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)
from backend.domains.service.fgcn.contracts import (
    AllocationBucket,
    BlueprintSnapshot,
    CaseStatus,
    GateServiceScope,
    TaskQualityState,
    TaskStatus,
)
from backend.domains.service.fgcn.engine import FGCNEngine
from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    GateScope,
    InMemoryHumanGate,
)
from backend.intelligence.model_gateway import FakeProvider, ModelGateway
from backend.intelligence.model_gateway.contracts import StructuredRequest

NOW = datetime(2026, 8, 30, 9, tzinfo=UTC)


def _scope() -> GateServiceScope:
    return GateServiceScope(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_person_id="child-1",
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-fgcn-1",
    )


def _gate_scope() -> GateScope:
    return GateScope(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ids=("child-1",),
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-fgcn-1",
    )


def _blueprint(*, status: str = "PUBLISHED") -> BlueprintSnapshot:
    return BlueprintSnapshot(
        blueprint_ref="communication-21day-service-collab",
        version=1,
        status=status,
        policy_ref="shadow-policy.v1",
        policy_version=1,
        checksum="checksum-v1",
        task_template_keys=("AI_GUIDANCE_DELIVERY", "HUMAN_HANDOFF"),
    )


def _engine() -> FGCNEngine:
    engine = FGCNEngine()
    engine.open_case(
        case_id="case-1",
        scope=_scope(),
        intent_ref="intent-1",
        plan_ref="plan-1",
        owner_id="steward-1",
        blueprint=_blueprint(),
        idempotency_key="open-case-1",
        opened_at=NOW,
    )
    engine.create_task(
        task_id="task-1",
        case_id="case-1",
        task_key="AI_GUIDANCE_DELIVERY",
        title="Guidance delivery",
        description="Deliver the configured guidance activity.",
        role_key="DELIVERY_RESOURCE",
        acceptance_criteria=("Evidence reference is present",),
        actor_id="steward-1",
        created_at=NOW,
    )
    return engine


def _assignment_request(
    *,
    scope: GateScope | None = None,
    provider_id: str = "expert-1",
    proposal_id: str = "proposal-fgcn-1",
):
    gate = InMemoryHumanGate()
    draft_provider = FakeProvider(
        {
            "service_matching_recommendation": {
                "candidate_provider_id": provider_id,
                "reason": "admitted capability match",
            }
        }
    )
    gateway = ModelGateway({"fake-deterministic": draft_provider}, environment="test")

    async def _build():
        draft = await gateway.generate_structured(
            StructuredRequest(
                use_case="service_matching_recommendation",
                prompt_version="service-matching.v1",
                schema_version="service-task-proposal.v1",
                data_class="OPERATIONAL_TEXT",
                payload={"task_id": "task-1"},
                output_schema={
                    "type": "object",
                    "properties": {
                        "candidate_provider_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["candidate_provider_id", "reason"],
                },
                context_snapshot_ref="context:tenant-1:child-1:fgcn",
                request_id="request-fgcn-1",
            ),
            provider_id="fake-deterministic",
        )
        task = gate.submit_model_draft(
            draft,
            draft_id="draft-fgcn-1",
            proposal_id=proposal_id,
            action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
            action_arguments={
                "service_task_id": "task-1",
                "provider_id": provider_id,
                "assignee_kind": "EXPERT",
            },
            scope=scope or _gate_scope(),
            allowed_actor_types=(ActorType.GUARDIAN,),
            risk_level="HIGH",
            provenance_ref="model-draft:request-fgcn-1",
            now=NOW,
        )
        _, request = gate.decide(
            task.task_id,
            actor_id="guardian-1",
            actor_type=ActorType.GUARDIAN,
            outcome=DecisionOutcome.ACCEPT,
            now=NOW + timedelta(minutes=1),
        )
        assert request is not None
        return request

    return _build


@pytest.mark.asyncio
async def test_ai_gateway_human_gate_and_fgcn_assignment_form_one_audited_path():
    engine = _engine()
    request = await _assignment_request()()

    assignment = engine.execute_named_action(request)

    assert assignment.task_id == "task-1"
    assert assignment.assignee_ref == "expert-1"
    assert engine.tasks["task-1"].status is TaskStatus.ACCEPTED
    assert engine.cases["case-1"].status is CaseStatus.ASSIGNED
    assert [event.action for event in engine.audit.all_events()] == [
        "OPEN_SERVICE_CASE",
        "CREATE_SERVICE_TASK",
        "CONFIRM_SERVICE_TASK_ASSIGNMENT",
        "ACCEPT_SERVICE_TASK",
        "ASSIGN_SERVICE_CASE",
    ]


def test_blueprint_must_be_published_and_task_must_come_from_its_snapshot():
    with pytest.raises(ServiceValidationError, match="fgcn_blueprint_must_be_published"):
        _blueprint(status="DRAFT")

    engine = _engine()
    with pytest.raises(ServiceValidationError, match="fgcn_task_key_not_in_published_blueprint"):
        engine.create_task(
            task_id="task-invalid",
            case_id="case-1",
            task_key="UNCONFIGURED_TASK",
            title="Invalid",
            description="Not configured.",
            role_key="DELIVERY_RESOURCE",
            acceptance_criteria=("criterion",),
            actor_id="steward-1",
        )


@pytest.mark.asyncio
async def test_assignment_rejects_cross_family_and_second_responsible_person():
    engine = _engine()
    request = await _assignment_request()()
    engine.execute_named_action(request)

    replayed = await _assignment_request()()
    assert engine.execute_named_action(replayed).assignment_id == "assignment:task-1:expert-1"

    second_proposal = await _assignment_request(
        provider_id="expert-2", proposal_id="proposal-fgcn-2"
    )()
    with pytest.raises(ServiceConflictError, match="fgcn_task_already_has_responsible_person"):
        engine.execute_named_action(second_proposal)

    foreign_scope_request = await _assignment_request(
        scope=GateScope(
            tenant_id="tenant-1",
            family_id="family-foreign",
            subject_ids=("child-1",),
            purpose="service_collaboration",
            consent_version="consent.v1",
            correlation_id="corr-foreign",
        ),
        provider_id="expert-2",
        proposal_id="proposal-fgcn-3",
    )()
    with pytest.raises(ServiceForbiddenError, match="fgcn_family_scope_violation"):
        engine.execute_named_action(foreign_scope_request)

    empty_subject_scope_request = await _assignment_request(
        scope=GateScope(
            tenant_id="tenant-1",
            family_id="family-1",
            subject_ids=(),
            purpose="service_collaboration",
            consent_version="consent.v1",
            correlation_id="corr-empty-subject",
        ),
        provider_id="expert-3",
        proposal_id="proposal-fgcn-4",
    )()
    with pytest.raises(ServiceForbiddenError, match="fgcn_subject_scope_violation"):
        engine.execute_named_action(empty_subject_scope_request)


@pytest.mark.asyncio
async def test_delivery_quality_contribution_and_shadow_allocation_are_gated():
    engine = _engine()
    request = await _assignment_request()()
    engine.execute_named_action(request)

    with pytest.raises(ServiceConflictError, match="fgcn_contribution_requires_verified_task"):
        engine.record_contribution(
            contribution_id="contribution-too-early",
            task_id="task-1",
            delivery_id="delivery-1",
            provider_ref="expert-1",
            role_key="DELIVERY_RESOURCE",
            started_at=NOW,
            completed_at=NOW + timedelta(minutes=1),
        )

    engine.submit_delivery(
        delivery_id="delivery-1",
        task_id="task-1",
        assignee_ref="expert-1",
        evidence_ref="evidence:delivery-1",
        submitted_at=NOW + timedelta(hours=1),
    )
    with pytest.raises(ServiceForbiddenError, match="fgcn_quality_reviewer_must_differ"):
        engine.verify_delivery(
            quality_review_id="review-invalid",
            task_id="task-1",
            reviewer_ref="expert-1",
            review_note="same person",
            reviewed_at=NOW + timedelta(hours=2),
        )
    with pytest.raises(ServiceConflictError, match="fgcn_non_pass_quality_requires_rework_flow"):
        engine.verify_delivery(
            quality_review_id="review-rework",
            task_id="task-1",
            reviewer_ref="quality-1",
            review_note="needs rework",
            quality_state=TaskQualityState.REWORK_REQUIRED,
            reviewed_at=NOW + timedelta(hours=2),
        )

    engine.verify_delivery(
        quality_review_id="review-1",
        task_id="task-1",
        reviewer_ref="quality-1",
        review_note="criteria passed",
        reviewed_at=NOW + timedelta(hours=2),
    )
    engine.record_contribution(
        contribution_id="contribution-1",
        task_id="task-1",
        delivery_id="delivery-1",
        provider_ref="expert-1",
        role_key="DELIVERY_RESOURCE",
        started_at=NOW,
        completed_at=NOW + timedelta(hours=1),
    )
    engine.close_case(case_id="case-1", actor_id="quality-1", closed_at=NOW + timedelta(hours=3))
    statement = engine.finalize_shadow_allocation(
        case_id="case-1",
        actor_id="operator-1",
        allocation_run_id="allocation-run-1",
        finalized_at=NOW + timedelta(hours=4),
    )

    assert statement.total_units == Decimal("100")
    assert sum(line.units for line in statement.lines) == Decimal("100")
    assert next(
        line
        for line in statement.lines
        if line.allocation_bucket is AllocationBucket.DELIVERY_RESOURCE
    ).units == Decimal("40.00")
    assert (
        next(
            line
            for line in statement.lines
            if line.allocation_bucket is AllocationBucket.QUALITY_RESERVE
        ).release_state.value
        == "HELD"
    )
    assert not any("amount" in field.lower() for field in statement.__dataclass_fields__)

    with pytest.raises(ServiceConflictError, match="fgcn_one_allocation_run_per_case"):
        engine.finalize_shadow_allocation(
            case_id="case-1",
            actor_id="operator-1",
            allocation_run_id="allocation-run-2",
        )


def test_scope_and_idempotency_replay_are_fail_closed():
    engine = _engine()
    case = engine.open_case(
        case_id="case-1",
        scope=_scope(),
        intent_ref="intent-1",
        plan_ref="plan-1",
        owner_id="steward-1",
        blueprint=_blueprint(),
        idempotency_key="open-case-1",
        opened_at=NOW,
    )
    assert case.case_id == "case-1"
    with pytest.raises(ServiceConflictError, match="fgcn_case_idempotency_replay_mismatch"):
        engine.open_case(
            case_id="case-1",
            scope=_scope(),
            intent_ref="intent-changed",
            plan_ref="plan-1",
            owner_id="steward-1",
            blueprint=_blueprint(),
            idempotency_key="open-case-1",
            opened_at=NOW,
        )


@pytest.mark.asyncio
async def test_completed_case_rejects_new_delivery_but_keeps_existing_replay() -> None:
    engine = _engine()
    request = await _assignment_request()()
    engine.execute_named_action(request)
    existing = engine.submit_delivery(
        delivery_id="delivery-terminal-1",
        task_id="task-1",
        assignee_ref="expert-1",
        evidence_ref="evidence:terminal-1",
        submitted_at=NOW + timedelta(hours=1),
    )
    # Simulate a rehydrated/racing state where the case is closed while a task
    # command is retried.  The same delivery remains a safe idempotent replay.
    engine.cases["case-1"] = replace(
        engine.cases["case-1"], status=CaseStatus.COMPLETED, closed_at=NOW + timedelta(hours=3)
    )
    engine.tasks["task-1"] = replace(engine.tasks["task-1"], status=TaskStatus.ACCEPTED)
    assert engine.submit_delivery(
        delivery_id=existing.delivery_id,
        task_id="task-1",
        assignee_ref="expert-1",
        evidence_ref="evidence:terminal-1",
    ) == existing
    with pytest.raises(ServiceConflictError, match="fgcn_delivery_case_is_terminal"):
        engine.submit_delivery(
            delivery_id="delivery-terminal-2",
            task_id="task-1",
            assignee_ref="expert-1",
            evidence_ref="evidence:terminal-2",
        )
