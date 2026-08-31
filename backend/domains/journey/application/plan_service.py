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


HUMAN_CONFIRMED_INTENT_BOUNDARY = "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"


@dataclass(frozen=True, slots=True)
class ConfirmedGrowthIntent:
    """The smallest hand-off from the assessment experience to Journey.

    The boundary is intentionally explicit: an AI hypothesis or an unreviewed
    assessment can never be consumed as a plan trigger.  The intent carries
    evidence and knowledge references so the family can understand why the
    plan exists and the next service can reproduce that explanation.
    """

    intent_id: str
    tenant_id: str
    family_id: str
    actor_id: str
    need_type: str
    goal_text: str
    evidence_refs: tuple[str, ...] = ()
    knowledge_refs: tuple[str, ...] = ()
    boundary: str = HUMAN_CONFIRMED_INTENT_BOUNDARY


class PracticeStatus(StrEnum):
    PLANNED = "PLANNED"
    RECORDED = "RECORDED"


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
    intent_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    knowledge_refs: tuple[str, ...] = ()

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
            "intent_id": self.intent_id,
            "evidence_refs": list(self.evidence_refs),
            "knowledge_refs": list(self.knowledge_refs),
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
class FamilyPractice:
    practice_id: str
    plan_id: str
    tenant_id: str
    family_id: str
    title: str
    rationale: str
    day_index: int
    status: PracticeStatus = PracticeStatus.PLANNED

    def as_dict(self) -> dict[str, object]:
        return {
            "practice_id": self.practice_id,
            "plan_id": self.plan_id,
            "title": self.title,
            "rationale": self.rationale,
            "day_index": self.day_index,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class PracticeRecord:
    record_id: str
    practice_id: str
    plan_id: str
    tenant_id: str
    family_id: str
    observation: str
    blocker: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "practice_id": self.practice_id,
            "plan_id": self.plan_id,
            "observation": self.observation,
            "blocker": self.blocker,
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
    _practices: dict[str, FamilyPractice] = field(default_factory=dict)
    _records: list[PracticeRecord] = field(default_factory=list)
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
        intent_id: str | None = None,
        evidence_refs: tuple[str, ...] = (),
        knowledge_refs: tuple[str, ...] = (),
    ) -> dict[str, object]:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        if not focus_id.strip() or not goal_text.strip():
            raise JourneyValidationError("journey_focus_required")
        fingerprint = (focus_id, goal_text.strip())
        replay = self._replay(tenant_id, family_id, "create", idempotency_key, fingerprint)
        if replay is not None:
            return {**deepcopy(replay), "replayed": True}
        plan_seed = intent_id or focus_id
        plan_id = str(uuid5(NAMESPACE_URL, f"journey-plan:{tenant_id}:{family_id}:{plan_seed}"))
        plan = self._plans.get(plan_id)
        if plan is None:
            plan = JourneyPlan(
                plan_id,
                tenant_id,
                family_id,
                actor_id,
                focus_id,
                goal_text.strip(),
                intent_id=intent_id,
                evidence_refs=tuple(evidence_refs),
                knowledge_refs=tuple(knowledge_refs),
            )
            self._plans[plan_id] = plan
            try:
                self._commit("PLAN_CREATED", actor_id, tenant_id, family_id, plan_id)
            except Exception:
                self._plans.pop(plan_id, None)
                raise
        result = {"plan": plan.as_dict(), "created": True, "replayed": False}
        self._remember(tenant_id, family_id, "create", idempotency_key, fingerprint, result)
        return result

    def create_plan_from_intent(
        self, *, intent: ConfirmedGrowthIntent, idempotency_key: str
    ) -> dict[str, object]:
        """Create a Journey plan only from a human-confirmed assessment intent."""
        if intent.boundary != HUMAN_CONFIRMED_INTENT_BOUNDARY:
            raise JourneyForbiddenError("unconfirmed_growth_intent")
        return self.create_plan(
            tenant_id=intent.tenant_id,
            family_id=intent.family_id,
            actor_id=intent.actor_id,
            focus_id=intent.need_type,
            goal_text=intent.goal_text,
            idempotency_key=idempotency_key,
            intent_id=intent.intent_id,
            evidence_refs=intent.evidence_refs,
            knowledge_refs=intent.knowledge_refs,
        )

    def create_plan_from_assessment_receipt(
        self,
        *,
        receipt: dict[str, object],
        tenant_id: str,
        family_id: str,
        actor_id: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        """Consume the assessment domain's confirmed-intent receipt.

        This is the product seam between UI-03 and the Journey, not a second
        assessment implementation.  The receipt must say that a human
        confirmed the hypothesis; a draft, dismissal, or malformed receipt is
        never silently converted into a plan.
        """
        intent_data = receipt.get("intent")
        if receipt.get("outcome") != "INTENT_CREATED" or not isinstance(intent_data, dict):
            raise JourneyForbiddenError("assessment_intent_not_confirmed")
        required = ("intent_id", "need_type", "boundary")
        if any(not intent_data.get(field) for field in required):
            raise JourneyValidationError("assessment_intent_receipt_incomplete")
        if intent_data["boundary"] != HUMAN_CONFIRMED_INTENT_BOUNDARY:
            raise JourneyForbiddenError("assessment_intent_boundary_invalid")
        evidence_refs = tuple(str(ref) for ref in intent_data.get("evidence_refs", ()))
        return self.create_plan_from_intent(
            intent=ConfirmedGrowthIntent(
                intent_id=str(intent_data["intent_id"]),
                tenant_id=tenant_id,
                family_id=family_id,
                actor_id=actor_id,
                need_type=str(intent_data["need_type"]),
                goal_text=str(intent_data.get("goal_text") or "基于家庭已确认的关注持续观察"),
                evidence_refs=evidence_refs,
                knowledge_refs=tuple(str(ref) for ref in intent_data.get("knowledge_refs", ())),
                boundary=str(intent_data["boundary"]),
            ),
            idempotency_key=idempotency_key,
        )

    def read_plan(self, *, tenant_id: str, family_id: str, plan_id: str) -> dict[str, object]:
        plan = self._required(plan_id, tenant_id, family_id)
        return {
            "plan": plan.as_dict(),
            "reviews": [r.as_dict() for r in self._reviews if r.plan_id == plan_id],
            "practices": [p.as_dict() for p in self._practices.values() if p.plan_id == plan_id],
            "records": [r.as_dict() for r in self._records if r.plan_id == plan_id],
        }

    def add_practice(
        self,
        *,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        plan_id: str,
        title: str,
        rationale: str,
        day_index: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        plan = self._required(plan_id, tenant_id, family_id)
        if plan.status is not JourneyPlanStatus.ACTIVE:
            raise JourneyConflictError("journey_plan_not_active")
        if not title.strip() or not rationale.strip() or not 1 <= day_index <= 21:
            raise JourneyValidationError("journey_practice_invalid")
        fingerprint = (plan_id, title.strip(), rationale.strip(), str(day_index))
        replay = self._replay(tenant_id, family_id, "practice", idempotency_key, fingerprint)
        if replay is not None:
            return {**deepcopy(replay), "replayed": True}
        practice_id = str(uuid5(NAMESPACE_URL, f"journey-practice:{plan_id}:{day_index}"))
        practice = FamilyPractice(
            practice_id,
            plan_id,
            tenant_id,
            family_id,
            title.strip(),
            rationale.strip(),
            day_index,
        )
        self._practices[practice_id] = practice
        try:
            self._commit("PRACTICE_PLANNED", actor_id, tenant_id, family_id, practice_id)
        except Exception:
            self._practices.pop(practice_id, None)
            raise
        result = {"practice": practice.as_dict(), "replayed": False}
        self._remember(tenant_id, family_id, "practice", idempotency_key, fingerprint, result)
        return result

    def record_practice(
        self,
        *,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        plan_id: str,
        practice_id: str,
        observation: str,
        blocker: str | None,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        plan = self._required(plan_id, tenant_id, family_id)
        practice = self._practices.get(practice_id)
        if practice is None or practice.plan_id != plan_id:
            raise JourneyNotFoundError("journey_practice_not_found")
        if plan.status is not JourneyPlanStatus.ACTIVE:
            raise JourneyConflictError("journey_plan_not_active")
        if not observation.strip() or len(observation) > 2000:
            raise JourneyValidationError("journey_practice_observation_invalid")
        fingerprint = (plan_id, practice_id, observation.strip(), (blocker or "").strip())
        replay = self._replay(tenant_id, family_id, "record", idempotency_key, fingerprint)
        if replay is not None:
            return {**deepcopy(replay), "replayed": True}
        record_id = str(
            uuid5(NAMESPACE_URL, f"journey-record:{practice_id}:{len(self._records) + 1}")
        )
        record = PracticeRecord(
            record_id,
            practice_id,
            plan_id,
            tenant_id,
            family_id,
            observation.strip(),
            blocker.strip() if blocker and blocker.strip() else None,
        )
        self._records.append(record)
        self._practices[practice_id] = replace(practice, status=PracticeStatus.RECORDED)
        try:
            self._commit("PRACTICE_RECORDED", actor_id, tenant_id, family_id, record_id)
        except Exception:
            self._records.pop()
            self._practices[practice_id] = practice
            raise
        result = {
            "practice": self._practices[practice_id].as_dict(),
            "record": record.as_dict(),
            "replayed": False,
        }
        self._remember(tenant_id, family_id, "record", idempotency_key, fingerprint, result)
        return result

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
