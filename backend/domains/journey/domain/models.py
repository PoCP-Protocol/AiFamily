from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from .errors import JourneyConflictError


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class PhaseName(StrEnum):
    SEE = "SEE"
    PARENT_FIRST = "PARENT_FIRST"
    CO_CREATE = "CO_CREATE"
    STABILIZE = "STABILIZE"


class PhaseStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REVIEW_DUE = "REVIEW_DUE"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class PhaseDecision(StrEnum):
    CONTINUE = "CONTINUE"
    ADJUST = "ADJUST"
    PAUSE = "PAUSE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class GrowthPriorityDecision(StrEnum):
    P03 = "P03"
    R03 = "R03"
    R04 = "R04"
    R05 = "R05"
    NO_PRIORITY_YET = "NO_PRIORITY_YET"


PHASE_ORDER = (
    PhaseName.SEE,
    PhaseName.PARENT_FIRST,
    PhaseName.CO_CREATE,
    PhaseName.STABILIZE,
)


@dataclass(frozen=True)
class JourneyPhase:
    phase: PhaseName
    status: PhaseStatus


@dataclass(frozen=True)
class JourneyPlan:
    plan_id: str
    family_id: str
    onboarding_id: str
    priority_id: str
    status: PlanStatus
    current_phase: PhaseName
    phases: tuple[JourneyPhase, ...]
    confirmed_by_actor_id: str | None
    confirmed_at: datetime | None

    @classmethod
    def draft(
        cls, plan_id: str, family_id: str, onboarding_id: str, priority_id: str
    ) -> JourneyPlan:
        return cls(
            plan_id=plan_id,
            family_id=family_id,
            onboarding_id=onboarding_id,
            priority_id=priority_id,
            status=PlanStatus.DRAFT,
            current_phase=PhaseName.SEE,
            phases=tuple(JourneyPhase(name, PhaseStatus.PENDING) for name in PHASE_ORDER),
            confirmed_by_actor_id=None,
            confirmed_at=None,
        )

    def confirm(self, actor_id: str) -> JourneyPlan:
        if self.status is not PlanStatus.DRAFT:
            raise JourneyConflictError("journey_plan_not_draft")
        return replace(
            self,
            status=PlanStatus.ACTIVE,
            phases=self._replace_phase(self.current_phase, PhaseStatus.ACTIVE),
            confirmed_by_actor_id=actor_id,
            confirmed_at=datetime.now(UTC),
        )

    def review(self, decision: PhaseDecision) -> JourneyPlan:
        if self.status is not PlanStatus.ACTIVE:
            raise JourneyConflictError("journey_plan_not_active")
        current = next(item for item in self.phases if item.phase is self.current_phase)
        if current.status is not PhaseStatus.REVIEW_DUE:
            raise JourneyConflictError("journey_phase_review_not_due")
        if decision is PhaseDecision.CONTINUE:
            index = PHASE_ORDER.index(self.current_phase)
            phases = self._replace_phase(self.current_phase, PhaseStatus.COMPLETED)
            if index == len(PHASE_ORDER) - 1:
                return replace(self, status=PlanStatus.COMPLETED, phases=phases)
            next_phase = PHASE_ORDER[index + 1]
            phases = tuple(
                replace(item, status=PhaseStatus.ACTIVE) if item.phase is next_phase else item
                for item in phases
            )
            return replace(self, current_phase=next_phase, phases=phases)
        return replace(
            self,
            status=PlanStatus.PAUSED,
            phases=self._replace_phase(self.current_phase, PhaseStatus.BLOCKED),
        )

    def _replace_phase(
        self, phase: PhaseName, status: PhaseStatus
    ) -> tuple[JourneyPhase, ...]:
        return tuple(
            replace(item, status=status) if item.phase is phase else item
            for item in self.phases
        )
