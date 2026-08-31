"""Canonical first vertical slice for the family growth plan.

The service intentionally keeps persistence behind a small seam.  It is a
deterministic candidate for the plan-confirm/readback/review scenario; a
PostgreSQL adapter must preserve these scope, idempotency and event rules.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5

from ..domain.errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)


class JourneyPlanStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class PhaseReviewDecision(StrEnum):
    CONTINUE = "CONTINUE"
    ADJUST = "ADJUST"
    PAUSE = "PAUSE"


@dataclass(frozen=True, slots=True)
class JourneyPlan:
    plan_id: str
    tenant_id: str
    family_id: str
    actor_id: str
    focus_id: str
    goal_text: str
    status: JourneyPlanStatus = JourneyPlanStatus.DRAFT
    current_phase: int = 1
    review_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "focus_id": self.focus_id,
            "goal_text": self.goal_text,
            "status": self.status.value,
            "current_phase": self.current_phase,
            "review_count": self.review_count,
            "total_days": 21,
        }


@dataclass(frozen=True, slots=True)
class PhaseReview:
    review_id: str
    plan_id: str
    tenant_id: str
    family_id: str
    decision: PhaseReviewDecision
    observation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "review_id": self.review_id,
            "plan_id": self.plan_id,
            "decision": self.decision.value,
            "observation": self.observation,
        }


@dataclass(frozen=True, slots=True)
class _Replay:
    fingerprint: tuple[str, ...]
    result: dict[str, object]


@dataclass
class JourneyPlanService:
    """In-memory adapter used only for the first candidate and its tests."""

    outbox_writer: object | None = None
    _plans: dict[str, JourneyPlan] = field(default_factory=dict)
    _reviews: list[PhaseReview] = field(default_factory=list)
    _replays: dict[tuple[str, str, str], _Replay] = field(default_factory=dict)
    audit_events: list[dict[str, object]] = field(default_factory=list)
    outbox_events: list[dict[str, object]] = field(default_factory=list)

    def create_plan(
        self,
        *,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        focus_id: str,
        goal_text: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        if not focus_id.strip() or not goal_text.strip():
            raise JourneyValidationError("journey_focus_required")
        fingerprint = (focus_id, goal_text.strip())
        replay = self._replay(tenant_id, family_id, "create", idempotency_key, fingerprint)
        if replay is not None:
            return {**deepcopy(replay), "replayed": True}
        plan_id = str(uuid5(NAMESPACE_URL, f"journey-plan:{tenant_id}:{family_id}:{focus_id}"))
        plan = self._plans.get(plan_id)
        if plan is None:
            plan = JourneyPlan(plan_id, tenant_id, family_id, actor_id, focus_id, goal_text.strip())
            self._plans[plan_id] = plan
            try:
                self._commit("PLAN_CREATED", actor_id, tenant_id, family_id, plan_id)
            except Exception:
                self._plans.pop(plan_id, None)
                raise
        result = {"plan": plan.as_dict(), "created": True, "replayed": False}
        self._remember(tenant_id, family_id, "create", idempotency_key, fingerprint, result)
        return result

    def read_plan(self, *, tenant_id: str, family_id: str, plan_id: str) -> dict[str, object]:
        plan = self._required(plan_id, tenant_id, family_id)
        return {
            "plan": plan.as_dict(),
            "reviews": [r.as_dict() for r in self._reviews if r.plan_id == plan_id],
        }

    def confirm_plan(
        self, *, tenant_id: str, family_id: str, actor_id: str, plan_id: str, idempotency_key: str
    ) -> dict[str, object]:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        plan = self._required(plan_id, tenant_id, family_id)
        fingerprint = (plan_id,)
        replay = self._replay(tenant_id, family_id, "confirm", idempotency_key, fingerprint)
        if replay is not None:
            return {**deepcopy(replay), "replayed": True}
        if plan.status is not JourneyPlanStatus.DRAFT:
            raise JourneyConflictError("journey_plan_not_draft")
        updated = replace(plan, status=JourneyPlanStatus.ACTIVE)
        self._plans[plan_id] = updated
        try:
            self._commit("PLAN_CONFIRMED", actor_id, tenant_id, family_id, plan_id)
        except Exception:
            self._plans[plan_id] = plan
            raise
        result = {"plan": updated.as_dict(), "replayed": False}
        self._remember(tenant_id, family_id, "confirm", idempotency_key, fingerprint, result)
        return result

    def review_phase(
        self,
        *,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        plan_id: str,
        decision: PhaseReviewDecision,
        observation: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        plan = self._required(plan_id, tenant_id, family_id)
        if plan.status is not JourneyPlanStatus.ACTIVE:
            raise JourneyConflictError("journey_plan_not_active")
        if len(observation) > 2000:
            raise JourneyValidationError("journey_observation_too_long")
        fingerprint = (plan_id, decision.value, observation)
        replay = self._replay(tenant_id, family_id, "review", idempotency_key, fingerprint)
        if replay is not None:
            return {**deepcopy(replay), "replayed": True}
        review_id = str(uuid5(NAMESPACE_URL, f"journey-review:{plan_id}:{plan.review_count + 1}"))
        review = PhaseReview(
            review_id, plan_id, tenant_id, family_id, decision, observation.strip()
        )
        next_status = (
            JourneyPlanStatus.PAUSED
            if decision is not PhaseReviewDecision.CONTINUE
            else JourneyPlanStatus.ACTIVE
        )
        updated = replace(
            plan,
            status=next_status,
            current_phase=plan.current_phase + 1,
            review_count=plan.review_count + 1,
        )
        self._reviews.append(review)
        self._plans[plan_id] = updated
        try:
            self._commit("PHASE_REVIEWED", actor_id, tenant_id, family_id, review_id)
        except Exception:
            self._reviews.pop()
            self._plans[plan_id] = plan
            raise
        result = {"plan": updated.as_dict(), "review": review.as_dict(), "replayed": False}
        self._remember(tenant_id, family_id, "review", idempotency_key, fingerprint, result)
        return result

    def _required(self, plan_id: str, tenant_id: str, family_id: str) -> JourneyPlan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise JourneyNotFoundError("journey_plan_not_found")
        if plan.tenant_id != tenant_id or plan.family_id != family_id:
            raise JourneyForbiddenError("journey_plan_scope_denied")
        return plan

    def _commit(
        self, action: str, actor_id: str, tenant_id: str, family_id: str, resource_id: str
    ) -> None:
        audit = {
            "action": action,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "family_id": family_id,
            "resource_id": resource_id,
        }
        event = {**audit, "event_id": str(uuid5(NAMESPACE_URL, f"outbox:{action}:{resource_id}"))}
        self.audit_events.append(audit)
        try:
            if self.outbox_writer is not None:
                self.outbox_writer(event)
            self.outbox_events.append(event)
        except Exception:
            self.audit_events.pop()
            raise

    def _replay(
        self, tenant_id: str, family_id: str, action: str, key: str, fingerprint: tuple[str, ...]
    ) -> dict[str, object] | None:
        prior = self._replays.get((tenant_id, family_id, f"{action}:{key}"))
        if prior is None:
            return None
        if prior.fingerprint != fingerprint:
            raise JourneyConflictError("idempotency_conflict")
        return prior.result

    def _remember(
        self,
        tenant_id: str,
        family_id: str,
        action: str,
        key: str,
        fingerprint: tuple[str, ...],
        result: dict[str, object],
    ) -> None:
        self._replays[(tenant_id, family_id, f"{action}:{key}")] = _Replay(
            fingerprint, deepcopy(result)
        )

    @staticmethod
    def _validate_scope(tenant_id: str, family_id: str, actor_id: str, key: str) -> None:
        if any(not value.strip() for value in (tenant_id, family_id, actor_id, key)):
            raise JourneyValidationError("journey_scope_and_idempotency_required")
        if actor_id.lower().startswith("ai:"):
            raise JourneyForbiddenError("human_actor_required")
