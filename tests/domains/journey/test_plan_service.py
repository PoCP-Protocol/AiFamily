from __future__ import annotations

import pytest

from backend.domains.journey.application.plan_service import (
    JourneyPlanService,
    PhaseReviewDecision,
)
from backend.domains.journey.domain.errors import JourneyConflictError


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
