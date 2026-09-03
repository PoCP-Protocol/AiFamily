"""UI-09 daily action contracts owned by the Action domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from ..domain.errors import ActionConflictError, ActionValidationError


@dataclass(frozen=True, slots=True)
class ActionActor:
    actor_id: str
    family_id: str


class ActionActorScope(Protocol):
    actor_id: str
    family_id: str


@dataclass(frozen=True, slots=True)
class ActionEventScope:
    tenant_id: str
    region_id: str
    subject_person_id: str
    purpose: str
    consent_version: str
    deletion_ref: str
    locale: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.tenant_id,
                self.region_id,
                self.subject_person_id,
                self.purpose,
                self.consent_version,
                self.deletion_ref,
                self.locale,
            )
        ):
            raise ActionValidationError("daily_action_event_scope_incomplete")

    def as_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "region_id": self.region_id,
            "subject_person_id": self.subject_person_id,
            "purpose": self.purpose,
            "consent_version": self.consent_version,
            "deletion_ref": self.deletion_ref,
            "locale": self.locale,
        }


class DailyActionState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    NOT_COMPLETED = "NOT_COMPLETED"
    CANCELLED = "CANCELLED"


class DailyActionTransition(StrEnum):
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"


class DailyActionCompletion(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    NOT_COMPLETED = "NOT_COMPLETED"


_TRANSITIONS = {
    (DailyActionState.NOT_STARTED, DailyActionTransition.START): DailyActionState.IN_PROGRESS,
    (DailyActionState.NOT_STARTED, DailyActionTransition.CANCEL): DailyActionState.CANCELLED,
    (DailyActionState.IN_PROGRESS, DailyActionTransition.PAUSE): DailyActionState.PAUSED,
    (DailyActionState.IN_PROGRESS, DailyActionTransition.CANCEL): DailyActionState.CANCELLED,
    (DailyActionState.PAUSED, DailyActionTransition.RESUME): DailyActionState.IN_PROGRESS,
    (DailyActionState.PAUSED, DailyActionTransition.CANCEL): DailyActionState.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class DailyActionProjection:
    task_id: str
    family_id: str
    subject_person_id: str
    journey_plan_id: str
    journey_phase: str
    day_index: int
    assignment_text: str
    execution_status: DailyActionState
    task_version: int
    due_date: str
    reflection: str | None = None
    source_draft_id: str | None = None
    source_draft_digest: str | None = None
    source_provenance_ref: str | None = None
    source_consent_version: str | None = None

    @property
    def task_state(self) -> str:
        if self.execution_status is DailyActionState.COMPLETED:
            return "CHECKED_IN"
        return self.execution_status.value

    @property
    def checkin_allowed(self) -> bool:
        return self.execution_status is DailyActionState.IN_PROGRESS

    @property
    def allowed_actions(self) -> tuple[str, ...]:
        return tuple(
            transition.value
            for current, transition in _TRANSITIONS
            if current is self.execution_status
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "family_id": self.family_id,
            "subject_person_id": self.subject_person_id,
            "journey_plan_id": self.journey_plan_id,
            "journey_phase": self.journey_phase,
            "day_index": self.day_index,
            "assignment_text": self.assignment_text,
            "task_state": self.task_state,
            "execution_status": self.execution_status.value,
            "checkin_allowed": self.checkin_allowed,
            "allowed_actions": list(self.allowed_actions),
            "task_version": self.task_version,
            "due_date": self.due_date,
            "reflection": self.reflection,
            "boundary": "ACTION_IS_NOT_OUTCOME",
        }


def transition_state(
    current: DailyActionState,
    transition: DailyActionTransition,
) -> DailyActionState:
    try:
        return _TRANSITIONS[(current, transition)]
    except KeyError as error:
        raise ActionConflictError(
            f"daily_action_transition_invalid:{current.value}:{transition.value}"
        ) from error


def completion_state(
    current: DailyActionState,
    completion: DailyActionCompletion,
) -> DailyActionState:
    if current is not DailyActionState.IN_PROGRESS:
        raise ActionConflictError("daily_action_checkin_requires_in_progress")
    return DailyActionState(completion.value)


def require_event_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ActionValidationError("daily_action_occurred_at_timezone_required")
    return value


__all__ = [
    "ActionActor",
    "ActionActorScope",
    "ActionEventScope",
    "DailyActionCompletion",
    "DailyActionProjection",
    "DailyActionState",
    "DailyActionTransition",
    "completion_state",
    "require_event_time",
    "transition_state",
]
