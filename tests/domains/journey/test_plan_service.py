from __future__ import annotations

import pytest

from backend.domains.journey.application.plan_service import (
    HUMAN_CONFIRMED_INTENT_BOUNDARY,
    ConfirmedGrowthIntent,
    JourneyPlanService,
    PhaseReviewDecision,
)
from backend.domains.journey.domain.errors import JourneyConflictError, JourneyForbiddenError


def test_confirmed_assessment_intent_flows_into_practice_and_review() -> None:
    service = JourneyPlanService()
    plan_result = service.create_plan_from_intent(
        intent=ConfirmedGrowthIntent(
            intent_id="intent-1",
            tenant_id="tenant-a",
            family_id="family-a",
            actor_id="parent-a",
            need_type="PARENT_CHILD_COMMUNICATION",
            goal_text="在冲突时先听懂彼此，再共同决定",
            evidence_refs=("evidence-1",),
            knowledge_refs=("TH-001", "MD-001"),
        ),
        idempotency_key="plan-from-intent-1",
    )
    plan_id = plan_result["plan"]["plan_id"]
    assert plan_result["plan"]["evidence_refs"] == ["evidence-1"]
    assert plan_result["plan"]["knowledge_refs"] == ["TH-001", "MD-001"]

    service.confirm_plan(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        plan_id=plan_id,
        idempotency_key="confirm-1",
    )
    practice_result = service.add_practice(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        plan_id=plan_id,
        title="今晚冲突时，先复述孩子想表达的事",
        rationale="这一步对应测评中确认的沟通卡点，不把完成次数当作成长结论",
        day_index=1,
        idempotency_key="practice-1",
    )
    practice_id = practice_result["practice"]["practice_id"]
    recorded = service.record_practice(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        plan_id=plan_id,
        practice_id=practice_id,
        observation="孩子愿意多说了一句，我也发现自己更快进入辩解状态",
        blocker="睡前时间太晚",
        idempotency_key="record-1",
    )
    assert recorded["record"]["blocker"] == "睡前时间太晚"
    readback = service.read_plan(tenant_id="tenant-a", family_id="family-a", plan_id=plan_id)
    assert len(readback["practices"]) == 1
    assert len(readback["records"]) == 1
    assert readback["records"][0]["observation"].startswith("孩子愿意")


def test_unconfirmed_intent_cannot_create_plan() -> None:
    service = JourneyPlanService()
    with pytest.raises(JourneyForbiddenError, match="unconfirmed_growth_intent"):
        service.create_plan_from_intent(
            intent=ConfirmedGrowthIntent(
                intent_id="intent-2",
                tenant_id="tenant-a",
                family_id="family-a",
                actor_id="parent-a",
                need_type="HOMEWORK_PROCESS",
                goal_text="改善作业冲突",
                boundary="AI_DRAFT_ONLY",
            ),
            idempotency_key="plan-from-intent-2",
        )


def test_confirmed_intent_boundary_is_explicit() -> None:
    assert HUMAN_CONFIRMED_INTENT_BOUNDARY == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"


def test_confirm_readback_and_phase_review_are_family_scoped() -> None:
    service = JourneyPlanService()
    created = service.create_plan(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        focus_id="focus-1",
        goal_text="先听懂彼此，再共同决定",
        idempotency_key="create-1",
    )
    plan_id = created["plan"]["plan_id"]

    confirmed = service.confirm_plan(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        plan_id=plan_id,
        idempotency_key="confirm-1",
    )
    assert confirmed["plan"]["status"] == "ACTIVE"
    assert (
        service.read_plan(tenant_id="tenant-a", family_id="family-a", plan_id=plan_id)["plan"][
            "status"
        ]
        == "ACTIVE"
    )

    reviewed = service.review_phase(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        plan_id=plan_id,
        decision=PhaseReviewDecision.ADJUST,
        observation="需要降低一次练习的节奏",
        idempotency_key="review-1",
    )
    assert reviewed["review"]["decision"] == "ADJUST"
    assert reviewed["plan"]["status"] == "PAUSED"
    assert len(service.audit_events) == 3
    assert len(service.outbox_events) == 3

    replayed = service.confirm_plan(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        plan_id=plan_id,
        idempotency_key="confirm-1",
    )
    assert replayed["replayed"] is True

    with pytest.raises(JourneyConflictError, match="idempotency_conflict"):
        service.create_plan(
            tenant_id="tenant-a",
            family_id="family-a",
            actor_id="parent-a",
            focus_id="different-focus",
            goal_text="不同目标",
            idempotency_key="create-1",
        )


def test_outbox_failure_rolls_back_audit_side_effect() -> None:
    def fail(_: object) -> None:
        raise RuntimeError("outbox unavailable")

    service = JourneyPlanService(outbox_writer=fail)
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        service.create_plan(
            tenant_id="tenant-a",
            family_id="family-a",
            actor_id="parent-a",
            focus_id="focus-1",
            goal_text="共同决定",
            idempotency_key="create-1",
        )
    assert service.audit_events == []
    assert service.outbox_events == []
    assert service._plans == {}


def test_cross_family_read_is_denied() -> None:
    service = JourneyPlanService()
    result = service.create_plan(
        tenant_id="tenant-a",
        family_id="family-a",
        actor_id="parent-a",
        focus_id="focus-1",
        goal_text="共同决定",
        idempotency_key="create-1",
    )
    with pytest.raises(Exception, match="journey_plan_not_found|journey_plan_scope_denied"):
        service.read_plan(
            tenant_id="tenant-a",
            family_id="family-b",
            plan_id=result["plan"]["plan_id"],
        )
