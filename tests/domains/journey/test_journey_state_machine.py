from __future__ import annotations

import pytest

from backend.domains.journey.domain.errors import JourneyConflictError
from backend.domains.journey.domain.models import (
    JourneyPlan,
    PhaseDecision,
    PhaseStatus,
    PlanStatus,
)


def test_draft_requires_confirmation_before_becoming_active() -> None:
    draft = JourneyPlan.draft("plan-1", "family-1", "onboarding-1", "priority-1")
    assert draft.status is PlanStatus.DRAFT
    assert all(phase.status is PhaseStatus.PENDING for phase in draft.phases)

    active = draft.confirm("actor-1")
    assert active.status is PlanStatus.ACTIVE
    assert active.phases[0].status is PhaseStatus.ACTIVE


def test_phase_transition_requires_review_due_and_family_decision() -> None:
    active = JourneyPlan.draft(
        "plan-1", "family-1", "onboarding-1", "priority-1"
    ).confirm("actor-1")
    with pytest.raises(JourneyConflictError, match="journey_phase_review_not_due"):
        active.review(PhaseDecision.CONTINUE)


def test_non_continue_review_pauses_instead_of_claiming_outcome() -> None:
    active = JourneyPlan.draft(
        "plan-1", "family-1", "onboarding-1", "priority-1"
    ).confirm("actor-1")
    phases = list(active.phases)
    phases[0] = type(phases[0])(phases[0].phase, PhaseStatus.REVIEW_DUE)
    due = type(active)(**{**active.__dict__, "phases": tuple(phases)})

    paused = due.review(PhaseDecision.HUMAN_REVIEW_REQUIRED)
    assert paused.status is PlanStatus.PAUSED
    assert paused.phases[0].status is PhaseStatus.BLOCKED
