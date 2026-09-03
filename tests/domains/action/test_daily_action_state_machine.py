from datetime import UTC, datetime

import pytest

from backend.domains.action.application.daily_action import (
    DailyActionCompletion,
    DailyActionProjection,
    DailyActionState,
    DailyActionTransition,
    completion_state,
    require_event_time,
    transition_state,
)
from backend.domains.action.domain.errors import ActionConflictError, ActionValidationError


def test_daily_action_supports_pause_without_streak_penalty_or_score() -> None:
    started = transition_state(DailyActionState.NOT_STARTED, DailyActionTransition.START)
    paused = transition_state(started, DailyActionTransition.PAUSE)
    resumed = transition_state(paused, DailyActionTransition.RESUME)

    assert started is DailyActionState.IN_PROGRESS
    assert paused is DailyActionState.PAUSED
    assert resumed is DailyActionState.IN_PROGRESS
    projection = DailyActionProjection(
        task_id="action-1",
        family_id="family-1",
        subject_person_id="child-1",
        journey_plan_id="plan-1",
        journey_phase="SEE",
        day_index=1,
        assignment_text="先听完一句话，再回应。",
        execution_status=paused,
        task_version=2,
        due_date="2026-09-03",
    ).as_dict()
    assert projection["allowed_actions"] == ["RESUME", "CANCEL"]
    assert "score" not in projection
    assert "rank" not in projection
    assert projection["boundary"] == "ACTION_IS_NOT_OUTCOME"


def test_checkin_requires_started_action_and_maps_completed_to_checked_in() -> None:
    with pytest.raises(ActionConflictError, match="requires_in_progress"):
        completion_state(DailyActionState.NOT_STARTED, DailyActionCompletion.COMPLETED)

    completed = completion_state(
        DailyActionState.IN_PROGRESS,
        DailyActionCompletion.COMPLETED,
    )
    projection = DailyActionProjection(
        task_id="action-1",
        family_id="family-1",
        subject_person_id="child-1",
        journey_plan_id="plan-1",
        journey_phase="SEE",
        day_index=1,
        assignment_text="先听完一句话，再回应。",
        execution_status=completed,
        task_version=3,
        due_date="2026-09-03",
    )
    assert projection.task_state == "CHECKED_IN"
    assert projection.checkin_allowed is False
    assert projection.allowed_actions == ()


def test_terminal_or_invalid_transition_fails_closed() -> None:
    with pytest.raises(ActionConflictError, match="transition_invalid"):
        transition_state(DailyActionState.COMPLETED, DailyActionTransition.START)
    with pytest.raises(ActionConflictError, match="transition_invalid"):
        transition_state(DailyActionState.NOT_STARTED, DailyActionTransition.PAUSE)


def test_event_time_requires_timezone() -> None:
    assert require_event_time(datetime(2026, 9, 3, tzinfo=UTC)).tzinfo is UTC
    with pytest.raises(ActionValidationError, match="timezone_required"):
        require_event_time(datetime(2026, 9, 3))
