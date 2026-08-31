"""Synthetic end-to-end scenarios for the first family arrival MVP.

These tests deliberately speak in the family's language rather than testing
individual helpers: a parent brings a concern, corrects an understanding,
chooses a practice, records what happened, and returns for a first review.
The fixture marker is part of the assertion so it cannot be mistaken for
production evidence.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from backend.domains.assessment.application.commands import (
    AssessmentCommandHandler,
    MutationMeta,
    SaveAssessmentResponseCommand,
    StartAssessmentCommand,
    SubmitAssessmentCommand,
)
from backend.domains.assessment.application.growth_hypothesis_commands import (
    DecideGrowthHypothesisCommand,
    GrowthHypothesisCommandHandler,
)
from backend.domains.assessment.application.queries import (
    AssessmentQueryHandler,
    GetUi03ProjectionQuery,
)
from backend.domains.assessment.infrastructure.deterministic_interpretation import (
    DeterministicInterpretationAdapter,
)
from backend.domains.assessment.infrastructure.fake_repository import FakeAssessmentRepository
from backend.domains.journey.application.plan_service import (
    ConfirmedGrowthIntent,
    JourneyPlanService,
)
from backend.domains.journey.domain.errors import JourneyForbiddenError

SYNTHETIC_SOURCE = "SYNTHETIC_TEST_FIXTURE"


async def test_real_assessment_handlers_feed_the_journey_scenario() -> None:
    """Exercise the existing Assessment application layer, not a copied receipt."""
    repository = FakeAssessmentRepository()
    repository.seed_family("synthetic-tenant-b", "synthetic-family-b")
    child_id = str(uuid4())
    repository.seed_subject("synthetic-family-b", child_id, "小明")
    repository.seed_need_type(
        "COMMUNICATION",
        "NEED_PARENT_CHILD_COMMUNICATION",
        "亲子沟通支持",
        "先从倾听开始",
        ["LISTENING_COACH"],
    )
    assessment = AssessmentCommandHandler(repository)
    interpretation = DeterministicInterpretationAdapter()
    query = AssessmentQueryHandler(repository, interpretation)
    hypothesis = GrowthHypothesisCommandHandler(repository, interpretation)

    def meta(key: str) -> MutationMeta:
        return MutationMeta("synthetic-correlation", key, SYNTHETIC_SOURCE)

    started = await assessment.start(
        StartAssessmentCommand(
            "synthetic-family-b",
            "synthetic-tenant-b",
            "actor-1",
            child_id,
            None,
            meta("assessment-start"),
        )
    )
    session_id = started["session"]["assessment_session_id"]
    await assessment.save_response(
        SaveAssessmentResponseCommand(
            "synthetic-family-b",
            "synthetic-tenant-b",
            "actor-1",
            session_id,
            "FOCUS",
            "SINGLE_CHOICE",
            "COMMUNICATION",
            meta("assessment-focus"),
        )
    )
    await assessment.submit(
        SubmitAssessmentCommand(
            "synthetic-family-b",
            "synthetic-tenant-b",
            "actor-1",
            session_id,
            meta("assessment-submit"),
        )
    )
    projection = await query.get_ui03_projection(
        GetUi03ProjectionQuery("synthetic-family-b", "synthetic-tenant-b", "actor-1")
    )
    receipt = await hypothesis.decide(
        DecideGrowthHypothesisCommand(
            "synthetic-family-b",
            "synthetic-tenant-b",
            "actor-1",
            session_id,
            projection["hypothesis"]["hypothesis_ref"],
            "CONFIRM",
            "synthetic-correlation",
            "assessment-confirm",
        )
    )
    assert receipt["outcome"] == "INTENT_CREATED"

    journey = JourneyPlanService()
    plan = journey.create_plan_from_assessment_receipt(
        receipt=receipt,
        tenant_id="synthetic-tenant-b",
        family_id="synthetic-family-b",
        actor_id="actor-1",
        idempotency_key="journey-from-assessment",
    )
    assert plan["plan"]["intent_id"] == receipt["intent"]["intent_id"]
    assert plan["plan"]["focus_id"] == "NEED_PARENT_CHILD_COMMUNICATION"


def test_parent_can_complete_first_arrival_growth_loop_with_simulated_data() -> None:
    family = {
        "source": SYNTHETIC_SOURCE,
        "tenant_id": "synthetic-tenant-a",
        "family_id": "synthetic-family-a",
        "actor_id": "synthetic-parent-a",
        "concern": "每次聊作业最后都会变成争吵",
    }
    service = JourneyPlanService()

    # Simulated assessment/AI hand-off: this is a hypothesis the parent has
    # already corrected and confirmed, not an automatically accepted diagnosis.
    plan_result = service.create_plan_from_intent(
        intent=ConfirmedGrowthIntent(
            intent_id="synthetic-intent-1",
            tenant_id=family["tenant_id"],
            family_id=family["family_id"],
            actor_id=family["actor_id"],
            need_type="HOMEWORK_PROCESS",
            goal_text="先把作业冲突拆成可观察的过程，再共同调整",
            evidence_refs=("synthetic-assessment-evidence-1",),
            knowledge_refs=("TH-006", "MD-006"),
        ),
        idempotency_key="synthetic-plan-1",
    )
    plan_id = plan_result["plan"]["plan_id"]
    assert plan_result["plan"]["evidence_refs"] == ["synthetic-assessment-evidence-1"]
    assert plan_result["plan"]["knowledge_refs"] == ["TH-006", "MD-006"]

    service.confirm_plan(
        tenant_id=family["tenant_id"],
        family_id=family["family_id"],
        actor_id=family["actor_id"],
        plan_id=plan_id,
        idempotency_key="synthetic-confirm-1",
    )
    practice = service.add_practice(
        tenant_id=family["tenant_id"],
        family_id=family["family_id"],
        actor_id=family["actor_id"],
        plan_id=plan_id,
        title="今晚先复述孩子对作业最难受的部分",
        rationale="回应测评中确认的作业过程冲突，而不是追求完成次数",
        day_index=1,
        idempotency_key="synthetic-practice-1",
    )
    service.record_practice(
        tenant_id=family["tenant_id"],
        family_id=family["family_id"],
        actor_id=family["actor_id"],
        plan_id=plan_id,
        practice_id=practice["practice"]["practice_id"],
        observation="孩子说出最难的是题目太多，我也发现自己先给建议了",
        blocker="晚饭后剩余时间不足",
        idempotency_key="synthetic-record-1",
    )
    readback = service.read_plan(
        tenant_id=family["tenant_id"], family_id=family["family_id"], plan_id=plan_id
    )
    assert readback["plan"]["focus_id"] == "HOMEWORK_PROCESS"
    assert readback["records"][0]["observation"].startswith("孩子说出")
    assert readback["records"][0]["blocker"] == "晚饭后剩余时间不足"
    assert family["source"] == SYNTHETIC_SOURCE


def test_simulated_dismissal_and_cross_family_access_are_fail_closed() -> None:
    service = JourneyPlanService()
    with pytest.raises(JourneyForbiddenError, match="assessment_intent_not_confirmed"):
        service.create_plan_from_assessment_receipt(
            receipt={"outcome": "NO_ACTION", "intent": None},
            tenant_id="synthetic-tenant-a",
            family_id="synthetic-family-a",
            actor_id="synthetic-parent-a",
            idempotency_key="synthetic-dismissed-1",
        )

    created = service.create_plan(
        tenant_id="synthetic-tenant-a",
        family_id="synthetic-family-a",
        actor_id="synthetic-parent-a",
        focus_id="PARENT_CHILD_COMMUNICATION",
        goal_text="先听懂彼此",
        idempotency_key="synthetic-plan-2",
    )
    with pytest.raises(Exception, match="journey_plan_not_found|journey_plan_scope_denied"):
        service.read_plan(
            tenant_id="synthetic-tenant-a",
            family_id="synthetic-family-b",
            plan_id=created["plan"]["plan_id"],
        )
