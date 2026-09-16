from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.apps.family_api.assessment_review_confirmation import (
    AcceptedAssessmentReview,
    HumanGateConfirmedGrowthHypothesisHandler,
)
from backend.domains.assessment.application.growth_hypothesis_commands import (
    DecideGrowthHypothesisCommand,
)
from backend.domains.assessment.domain.entities import GrowthHypothesisEvidence
from backend.domains.assessment.domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
)
from backend.intelligence.agent_runtime.persistence import AgentRunRecord, AgentRunStatus
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.human_gate import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    GateStatus,
    HumanDecision,
    HumanTask,
    NamedActionRequest,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.platform.identity.context import ActorType as PlatformActorType

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
SESSION_ID = "60000000-0000-4000-8000-000000000001"
HYPOTHESIS_REF = f"ASSESSMENT:{SESSION_ID}:FAMILY_SUPPORT_NEEDS:v2:H1"


class Repository:
    def __init__(self, evidence: GrowthHypothesisEvidence) -> None:
        self.evidence = evidence

    async def load_hypothesis_evidence(self, family_id, tenant_id, session_id=None):
        del family_id, tenant_id
        return self.evidence if session_id == self.evidence.assessment_session_id else None


class ReviewReader:
    def __init__(self, accepted: AcceptedAssessmentReview) -> None:
        self.accepted = accepted

    async def load(self, task_id, *, tenant_id, family_id):
        del tenant_id, family_id
        if task_id != self.accepted.task.task_id:
            raise AssessmentConflictError("human_task_reference_invalid")
        return self.accepted


class Delegate:
    def __init__(self) -> None:
        self.commands: list[DecideGrowthHypothesisCommand] = []

    async def decide(self, command: DecideGrowthHypothesisCommand) -> dict:
        self.commands.append(command)
        return {"outcome": "INTENT_CREATED", "replayed": len(self.commands) > 1}


def evidence() -> GrowthHypothesisEvidence:
    return GrowthHypothesisEvidence(
        assessment_session_id=SESSION_ID,
        subject_person_id="child-1",
        subject_display_name="小宇",
        submitted_at=NOW - timedelta(hours=1),
        tool_ref="FAMILY_SUPPORT_NEEDS",
        tool_version=2,
        assessment_response_id="response-1",
        focus_ref="PARENT_CHILD_COMMUNICATION",
        assessment_evidence_id="evidence-1",
        need_type_ref="COMMUNICATION_SUPPORT",
        need_type_version=1,
        title="沟通支持",
        description="先观察家庭沟通节奏。",
        required_capability_keys=["FAMILY_DIALOGUE"],
        response_set=[],
    )


def scope(*, family_id: str = "family-1", consent_version: str = "consent-v1"):
    return ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id=family_id,
        subject_ids=("child-1",),
        purpose="assessment",
        consent_version=consent_version,
        consent_granted=True,
        data_class=DataClass.MINOR_PERSONAL_DATA,
        locale="zh-CN",
        deletion_ref="delete-1",
        correlation_id="corr-1",
        causation_id="cause-1",
    )


def accepted_review(
    *,
    status: GateStatus = GateStatus.DECIDED,
    outcome: DecisionOutcome = DecisionOutcome.ACCEPT,
    actor_id: str = "guardian-1",
    family_id: str = "family-1",
    consent_version: str = "consent-v1",
    expires_at: datetime = NOW + timedelta(hours=1),
    assessment_ref: str = SESSION_ID,
    prompt_version: str = "1",
    schema_version: str = "1",
) -> AcceptedAssessmentReview:
    gate_scope = GateScope(
        tenant_id="tenant-1",
        family_id=family_id,
        subject_ids=("child-1",),
        purpose="assessment",
        consent_version=consent_version,
        correlation_id="corr-1",
        region_id="CN",
        deletion_ref="delete-1",
    )
    arguments = {
        "agent_run_ref": "run-1",
        "agent_request_ref": "request-1",
        "draft_ref": "draft-1",
        "recommendation_status": "PROPOSED",
    }
    proposal = ActionProposal(
        proposal_id="proposal-1",
        draft_id="draft-1",
        draft_status="DRAFT",
        action_name="CONFIRM_GROWTH_HYPOTHESIS",
        action_arguments=arguments,
        scope=gate_scope,
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref="provenance-1",
        created_at=expires_at - timedelta(hours=1),
        expires_at=expires_at,
    )
    decision = None
    action = None
    if status is GateStatus.DECIDED:
        decision = HumanDecision(
            decision_id="decision-1",
            task_id="task-1",
            actor_id=actor_id,
            actor_type=ActorType.GUARDIAN,
            outcome=outcome,
            reason="not accepted" if outcome is not DecisionOutcome.ACCEPT else None,
            decided_at=NOW - timedelta(minutes=1),
        )
        if outcome is DecisionOutcome.ACCEPT:
            action = NamedActionRequest(
                request_id="action-request-1",
                action_name="CONFIRM_GROWTH_HYPOTHESIS",
                action_arguments=arguments,
                task_id="task-1",
                proposal_id="proposal-1",
                decision_id="decision-1",
                actor_id=actor_id,
                actor_type=ActorType.GUARDIAN,
                scope=gate_scope,
                provenance_ref="provenance-1",
                idempotency_key="server-owned-action-key",
            )
    task = HumanTask(
        task_id="task-1",
        proposal=proposal,
        status=status,
        decision=decision,
        action_request=action,
        created_at=proposal.created_at,
    )
    run = AgentRunRecord(
        run_id="run-1",
        request_id="request-1",
        agent_id="parent_advisor",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="assessment_interpretation",
        trace_id="trace-1",
        status=AgentRunStatus.SUCCEEDED,
        started_at=NOW - timedelta(minutes=3),
        completed_at=NOW - timedelta(minutes=2),
        error_code=None,
        draft=ModelDraft(
            output={"assessment_ref": assessment_ref},
            provenance=AiProvenance(
                provider_id="provider-1",
                model="model-1",
                model_version="1",
                prompt_version=prompt_version,
                schema_version=schema_version,
                context_snapshot_ref="snapshot-1",
                latency_ms=1,
                data_class="MINOR_PERSONAL_DATA",
                use_case="assessment_interpretation",
            ),
        ),
        idempotency_key="agent-run-key",
        task_fingerprint="fingerprint-1",
    )
    return AcceptedAssessmentReview(task=task, run=run)


def command(**changes) -> DecideGrowthHypothesisCommand:
    value = DecideGrowthHypothesisCommand(
        family_id="family-1",
        tenant_id="tenant-1",
        actor_id="guardian-1",
        assessment_session_id=SESSION_ID,
        hypothesis_ref=HYPOTHESIS_REF,
        decision_type="CONFIRM",
        correlation_id="corr-1",
        idempotency_key="client-selected-key",
        actor_type=PlatformActorType.HUMAN,
        scope_ref="family://tenant-1/family-1/assessment",
        signal_version=2,
        reviewed_draft_ref="draft-1",
        draft_version=1,
        provenance_ref="provenance-1",
        human_gate_receipt_ref="task-1",
    )
    return replace(value, **changes)


def handler(
    *,
    accepted: AcceptedAssessmentReview | None = None,
    current_scope: ContextScope | None = None,
) -> tuple[HumanGateConfirmedGrowthHypothesisHandler, Delegate]:
    delegate = Delegate()
    review = accepted or accepted_review()
    resolved_scope = current_scope or scope()
    return (
        HumanGateConfirmedGrowthHypothesisHandler(
            delegate=delegate,  # type: ignore[arg-type]
            repository=Repository(evidence()),  # type: ignore[arg-type]
            review_reader=ReviewReader(review),
            current_scope_resolver=lambda family_id, subject_id: resolved_scope,
            expected_prompt_version="1",
            expected_schema_version="1",
            clock=lambda: NOW,
        ),
        delegate,
    )


@pytest.mark.asyncio
async def test_accepted_action_owns_business_idempotency_across_client_replay() -> None:
    application, delegate = handler()

    first = await application.decide(command())
    replay = await application.decide(command(idempotency_key="another-client-key"))

    assert first["outcome"] == "INTENT_CREATED"
    assert replay["replayed"] is True
    assert [item.idempotency_key for item in delegate.commands] == [
        "server-owned-action-key",
        "server-owned-action-key",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("accepted", "current_scope", "changes", "error_type", "error_code"),
    [
        (
            accepted_review(status=GateStatus.OPEN),
            None,
            {},
            AssessmentConflictError,
            "human_task_acceptance_required",
        ),
        (
            accepted_review(outcome=DecisionOutcome.REJECT),
            None,
            {},
            AssessmentConflictError,
            "human_task_acceptance_required",
        ),
        (
            accepted_review(expires_at=NOW),
            None,
            {},
            AssessmentConflictError,
            "human_task_expired",
        ),
        (
            accepted_review(family_id="family-2"),
            None,
            {},
            AssessmentForbiddenError,
            "human_task_family_mismatch",
        ),
        (
            accepted_review(actor_id="guardian-2"),
            None,
            {},
            AssessmentForbiddenError,
            "human_task_actor_mismatch",
        ),
        (
            None,
            scope(consent_version="consent-v2"),
            {},
            AssessmentConflictError,
            "human_task_scope_stale",
        ),
        (
            None,
            None,
            {"draft_version": 2},
            AssessmentConflictError,
            "reviewed_draft_version_mismatch",
        ),
        (
            accepted_review(assessment_ref="another-session"),
            None,
            {},
            AssessmentConflictError,
            "reviewed_draft_assessment_mismatch",
        ),
        (
            accepted_review(prompt_version="2"),
            None,
            {},
            AssessmentConflictError,
            "reviewed_draft_execution_version_stale",
        ),
    ],
)
async def test_invalid_review_never_reaches_growth_command(
    accepted,
    current_scope,
    changes,
    error_type,
    error_code,
) -> None:
    application, delegate = handler(accepted=accepted, current_scope=current_scope)

    with pytest.raises(error_type) as exc:
        await application.decide(command(**changes))

    assert exc.value.code == error_code
    assert delegate.commands == []


@pytest.mark.asyncio
async def test_missing_task_reference_and_edit_fail_closed() -> None:
    application, delegate = handler()

    with pytest.raises(AssessmentConflictError, match="human_task_binding_required"):
        await application.decide(command(human_gate_receipt_ref=""))
    with pytest.raises(AssessmentConflictError, match="edited_hypothesis_review_required"):
        await application.decide(command(decision_type="EDIT", parent_note="家长改写"))

    assert delegate.commands == []
