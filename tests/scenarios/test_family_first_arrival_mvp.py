"""Synthetic end-to-end scenarios for the first family arrival MVP.

These tests deliberately speak in the family's language rather than testing
individual helpers: a parent brings a concern, corrects an understanding,
chooses a practice, records what happened, and returns for a first review.
The fixture marker is part of the assertion so it cannot be mistaken for
production evidence.
"""

from __future__ import annotations

import pytest

from backend.domains.journey.application.plan_service import (
    ConfirmedGrowthIntent,
    JourneyPlanService,
)
from backend.domains.journey.domain.errors import JourneyForbiddenError

SYNTHETIC_SOURCE = "SYNTHETIC_TEST_FIXTURE"


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
