"""Canonical, family-scoped 21-day Journey state.

The model records a cadence and the family's own decisions. It deliberately
does not calculate a family score, rank, diagnosis, or growth outcome. Those
boundaries are part of the aggregate so every adapter returns the same meaning.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from .errors import JourneyConflictError, JourneyValidationError

HORIZON_DAYS = 21


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class PhaseName(StrEnum):
    NOTICE = "NOTICE"
    PRACTICE = "PRACTICE"
    CONSOLIDATE = "CONSOLIDATE"


class PhaseStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REVIEW_DUE = "REVIEW_DUE"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class PhaseReviewDecision(StrEnum):
    CONTINUE = "CONTINUE"
    ADJUST = "ADJUST"
    PAUSE = "PAUSE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class JourneyPhase:
    phase: PhaseName
    start_day: int
    end_day: int
    review_due_day: int
    status: PhaseStatus


PHASE_DEFINITIONS: tuple[tuple[PhaseName, int, int, int], ...] = (
    (PhaseName.NOTICE, 1, 7, 7),
    (PhaseName.PRACTICE, 8, 14, 14),
    (PhaseName.CONSOLIDATE, 15, 21, 21),
)


@dataclass(frozen=True, slots=True)
class JourneyAction:
    action_id: str
    tenant_id: str
    family_id: str
    plan_id: str
    day_no: int
    action_text: str
    actor_id: str
    idempotency_key: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class PhaseReview:
    review_id: str
    tenant_id: str
    family_id: str
    plan_id: str
    phase: PhaseName
    decision: PhaseReviewDecision
    notes: str | None
    actor_id: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class JourneyPlan:
    plan_id: str
    tenant_id: str
    family_id: str
    onboarding_id: str
    priority_id: str
    status: PlanStatus
    current_day: int
    current_phase: PhaseName
    phases: tuple[JourneyPhase, ...]
    created_by: str
    created_at: datetime
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None

    @classmethod
    def draft(
        cls,
        *,
        plan_id: str,
        tenant_id: str,
        family_id: str,
        onboarding_id: str,
        priority_id: str,
        actor_id: str,
        now: datetime | None = None,
    ) -> JourneyPlan:
        for name, value in {
            "plan_id": plan_id,
            "tenant_id": tenant_id,
            "family_id": family_id,
            "onboarding_id": onboarding_id,
            "priority_id": priority_id,
            "actor_id": actor_id,
        }.items():
            _required(name, value)
        occurred_at = now or datetime.now(UTC)
        return cls(
            plan_id=plan_id,
            tenant_id=tenant_id,
            family_id=family_id,
            onboarding_id=onboarding_id,
            priority_id=priority_id,
            status=PlanStatus.DRAFT,
            current_day=1,
            current_phase=PhaseName.NOTICE,
            phases=tuple(
                JourneyPhase(phase, start, end, review_day, PhaseStatus.PENDING)
                for phase, start, end, review_day in PHASE_DEFINITIONS
            ),
            created_by=actor_id,
            created_at=occurred_at,
        )

    def confirm(self, actor_id: str, now: datetime | None = None) -> JourneyPlan:
        _required("actor_id", actor_id)
        if self.status is not PlanStatus.DRAFT:
            raise JourneyConflictError("journey_plan_not_draft")
        phases = _set_phase_status(self.phases, self.current_phase, PhaseStatus.ACTIVE)
        return replace(
            self,
            status=PlanStatus.ACTIVE,
            phases=phases,
            confirmed_by=actor_id,
            confirmed_at=now or datetime.now(UTC),
        )

    def record_action(self) -> tuple[JourneyPlan, int]:
        if self.status is not PlanStatus.ACTIVE:
            raise JourneyConflictError("journey_plan_not_active")
        if self.current_day > HORIZON_DAYS:
            raise JourneyConflictError("journey_horizon_reached")
        phase = _phase(self.phases, self.current_phase)
        if phase.status is not PhaseStatus.ACTIVE:
            raise JourneyConflictError("journey_phase_not_active")
        action_day = self.current_day
        next_status = (
            PhaseStatus.REVIEW_DUE if action_day >= phase.review_due_day else PhaseStatus.ACTIVE
        )
        phases = _set_phase_status(self.phases, self.current_phase, next_status)
        return replace(self, current_day=action_day + 1, phases=phases), action_day

    def review_phase(self, decision: PhaseReviewDecision) -> JourneyPlan:
        if self.status is not PlanStatus.ACTIVE:
            raise JourneyConflictError("journey_plan_not_active")
        current = _phase(self.phases, self.current_phase)
        if current.status is not PhaseStatus.REVIEW_DUE:
            raise JourneyConflictError("journey_phase_review_not_due")
        if decision is PhaseReviewDecision.ADJUST:
            return replace(
                self,
                phases=_set_phase_status(self.phases, self.current_phase, PhaseStatus.ACTIVE),
            )
        if decision in {
            PhaseReviewDecision.PAUSE,
            PhaseReviewDecision.HUMAN_REVIEW_REQUIRED,
        }:
            return replace(
                self,
                status=PlanStatus.PAUSED,
                phases=_set_phase_status(self.phases, self.current_phase, PhaseStatus.BLOCKED),
            )

        index = next(i for i, item in enumerate(PHASE_DEFINITIONS) if item[0] is self.current_phase)
        phases = _set_phase_status(self.phases, self.current_phase, PhaseStatus.COMPLETED)
        if index == len(PHASE_DEFINITIONS) - 1:
            return replace(self, status=PlanStatus.COMPLETED, phases=phases)
        next_phase = PHASE_DEFINITIONS[index + 1]
        phases = _set_phase_status(phases, next_phase[0], PhaseStatus.ACTIVE)
        return replace(
            self,
            current_phase=next_phase[0],
            current_day=next_phase[1],
            phases=phases,
        )


def _required(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise JourneyValidationError(f"{name}_required")


def _phase(phases: tuple[JourneyPhase, ...], name: PhaseName) -> JourneyPhase:
    for phase in phases:
        if phase.phase is name:
            return phase
    raise JourneyValidationError("journey_phase_missing")


def _set_phase_status(
    phases: tuple[JourneyPhase, ...], name: PhaseName, status: PhaseStatus
) -> tuple[JourneyPhase, ...]:
    return tuple(
        replace(phase, status=status) if phase.phase is name else phase for phase in phases
    )


__all__ = [
    "HORIZON_DAYS",
    "PHASE_DEFINITIONS",
    "JourneyAction",
    "JourneyPhase",
    "JourneyPlan",
    "PhaseName",
    "PhaseReview",
    "PhaseReviewDecision",
    "PhaseStatus",
    "PlanStatus",
]
