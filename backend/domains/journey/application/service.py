"""Use cases for the family-confirmed 21-day Journey.

This slice closes the MVP path after a confirmed growth priority:
create -> read -> family confirm -> record a first small action -> phase
review. AI may supply the upstream perspective, but this service only accepts
the human-confirmed priority and never promotes a model draft to a fact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from ..domain.errors import JourneyConflictError, JourneyForbiddenError, JourneyNotFoundError
from ..domain.models import (
    JourneyAction,
    JourneyPlan,
    PhaseReview,
    PhaseReviewDecision,
)
from .ports import JourneyActor, JourneyPolicy, JourneyRepository

PLAN_POLICY_VERSION = "JOURNEY_21_DAY_MVP_V1"
PLAN_BOUNDARY = "PLAN_IS_FAMILY_CONFIRMED_CADENCE_NOT_DIAGNOSIS_OR_OUTCOME"
ACTION_BOUNDARY = "ACTION_RECORD_IS_PROCESS_EVIDENCE_NOT_GROWTH_OUTCOME"
REVIEW_BOUNDARY = "PHASE_TRANSITION_REQUIRES_FAMILY_DECISION"


@dataclass(frozen=True, slots=True)
class JourneyService:
    repository: JourneyRepository
    policy: JourneyPolicy

    async def get_current(self, actor: JourneyActor) -> dict:
        await self.policy.assert_can_read(actor)
        plan = await self.repository.get_current(actor.tenant_id, actor.family_id)
        return _projection(actor, plan, await self._lists(plan))

    async def get_plan(self, actor: JourneyActor, plan_id: str) -> dict:
        await self.policy.assert_can_read(actor)
        plan = await self._required(actor, plan_id)
        return _projection(actor, plan, await self._lists(plan))

    async def create_plan(
        self,
        actor: JourneyActor,
        *,
        onboarding_id: str,
        priority_id: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> dict:
        await self.policy.assert_can_manage(actor)
        _key(idempotency_key)
        fingerprint = _fingerprint(
            "create", actor, onboarding_id=onboarding_id, priority_id=priority_id
        )
        replay = await self._replay(actor, "create_plan", idempotency_key, fingerprint)
        if replay is not None:
            return replay
        if not await self.repository.has_confirmed_priority(
            actor.tenant_id, actor.family_id, onboarding_id, priority_id
        ):
            raise JourneyNotFoundError("confirmed_growth_priority_not_found")
        existing = await self.repository.get_current(
            actor.tenant_id, actor.family_id, onboarding_id
        )
        if existing is not None:
            if existing.priority_id != priority_id:
                raise JourneyConflictError("journey_plan_already_exists_for_onboarding")
            response = {"plan": _plan(existing), "created": False, "replayed": False}
            await self._save_replay(actor, "create_plan", idempotency_key, fingerprint, response)
            return response

        plan = JourneyPlan.draft(
            plan_id=str(uuid4()),
            tenant_id=actor.tenant_id,
            family_id=actor.family_id,
            onboarding_id=onboarding_id,
            priority_id=priority_id,
            actor_id=actor.actor_id,
            now=now,
        )
        await self.repository.save_plan(plan)
        response = {"plan": _plan(plan), "created": True, "replayed": False}
        await self._save_replay(actor, "create_plan", idempotency_key, fingerprint, response)
        return response

    async def confirm_plan(
        self,
        actor: JourneyActor,
        plan_id: str,
        *,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> dict:
        await self.policy.assert_can_manage(actor)
        _key(idempotency_key)
        fingerprint = _fingerprint("confirm", actor, plan_id=plan_id)
        replay = await self._replay(actor, "confirm_plan", idempotency_key, fingerprint)
        if replay is not None:
            return replay
        plan = await self._required(actor, plan_id)
        updated = plan.confirm(actor.actor_id, now)
        await self.repository.save_plan(updated)
        response = {"plan": _plan(updated), "replayed": False}
        await self._save_replay(actor, "confirm_plan", idempotency_key, fingerprint, response)
        return response

    async def record_action(
        self,
        actor: JourneyActor,
        plan_id: str,
        *,
        action_text: str,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> dict:
        await self.policy.assert_can_manage(actor)
        _key(idempotency_key)
        if not isinstance(action_text, str) or not action_text.strip():
            raise JourneyConflictError("journey_action_text_required")
        if len(action_text.strip()) > 500:
            raise JourneyConflictError("journey_action_text_too_long")
        fingerprint = _fingerprint(
            "record_action", actor, plan_id=plan_id, action_text=action_text.strip()
        )
        replay = await self._replay(actor, "record_action", idempotency_key, fingerprint)
        if replay is not None:
            return replay
        plan = await self._required(actor, plan_id)
        updated, day_no = plan.record_action()
        action = JourneyAction(
            action_id=str(uuid4()),
            tenant_id=actor.tenant_id,
            family_id=actor.family_id,
            plan_id=plan_id,
            day_no=day_no,
            action_text=action_text.strip(),
            actor_id=actor.actor_id,
            idempotency_key=idempotency_key,
            recorded_at=now or datetime.now(UTC),
        )
        await self.repository.save_plan(updated)
        await self.repository.append_action(action)
        response = {
            "action": _action(action),
            "plan": _plan(updated),
            "replayed": False,
            "boundary": ACTION_BOUNDARY,
        }
        await self._save_replay(actor, "record_action", idempotency_key, fingerprint, response)
        return response

    async def review_phase(
        self,
        actor: JourneyActor,
        plan_id: str,
        *,
        decision: PhaseReviewDecision,
        notes: str | None,
        idempotency_key: str,
        now: datetime | None = None,
    ) -> dict:
        await self.policy.assert_can_manage(actor)
        _key(idempotency_key)
        if notes is not None and len(notes) > 500:
            raise JourneyConflictError("journey_review_notes_too_long")
        fingerprint = _fingerprint(
            "review_phase",
            actor,
            plan_id=plan_id,
            decision=decision.value,
            notes=notes or "",
        )
        replay = await self._replay(actor, "review_phase", idempotency_key, fingerprint)
        if replay is not None:
            return replay
        plan = await self._required(actor, plan_id)
        updated = plan.review_phase(decision)
        review = PhaseReview(
            review_id=str(uuid4()),
            tenant_id=actor.tenant_id,
            family_id=actor.family_id,
            plan_id=plan_id,
            phase=plan.current_phase,
            decision=decision,
            notes=notes.strip() if notes else None,
            actor_id=actor.actor_id,
            reviewed_at=now or datetime.now(UTC),
        )
        await self.repository.save_plan(updated)
        await self.repository.append_review(review)
        response = {
            "review": _review(review),
            "plan": _plan(updated),
            "replayed": False,
            "boundary": REVIEW_BOUNDARY,
        }
        await self._save_replay(actor, "review_phase", idempotency_key, fingerprint, response)
        return response

    async def _required(self, actor: JourneyActor, plan_id: str) -> JourneyPlan:
        plan = await self.repository.get(actor.tenant_id, actor.family_id, plan_id)
        if plan is None:
            raise JourneyNotFoundError("journey_plan_not_found")
        return plan

    async def _lists(
        self, plan: JourneyPlan | None
    ) -> tuple[list[JourneyAction], list[PhaseReview]]:
        if plan is None:
            return [], []
        return (
            await self.repository.list_actions(plan.tenant_id, plan.family_id, plan.plan_id),
            await self.repository.list_reviews(plan.tenant_id, plan.family_id, plan.plan_id),
        )

    async def _replay(
        self, actor: JourneyActor, operation: str, key: str, fingerprint: str
    ) -> dict | None:
        item = await self.repository.load_idempotency(
            actor.tenant_id, actor.family_id, operation, key
        )
        if item is None:
            return None
        old_fingerprint, response = item
        if old_fingerprint != fingerprint:
            raise JourneyConflictError("idempotency_conflict")
        return {**response, "replayed": True}

    async def _save_replay(
        self,
        actor: JourneyActor,
        operation: str,
        key: str,
        fingerprint: str,
        response: dict,
    ) -> None:
        await self.repository.save_idempotency(
            actor.tenant_id, actor.family_id, operation, key, fingerprint, response
        )


class HumanFamilyPolicy:
    """Small default policy for composition tests; production supplies its own."""

    async def assert_can_read(self, actor: JourneyActor) -> None:
        _actor_present(actor)

    async def assert_can_manage(self, actor: JourneyActor) -> None:
        _actor_present(actor)
        if actor.actor_type != "HUMAN":
            raise JourneyForbiddenError("journey_mutation_requires_human_actor")


def _actor_present(actor: JourneyActor) -> None:
    if not actor.actor_id or not actor.tenant_id or not actor.family_id:
        raise JourneyForbiddenError("journey_actor_context_required")


def _key(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise JourneyConflictError("invalid_idempotency_key")


def _fingerprint(operation: str, actor: JourneyActor, **payload: str) -> str:
    value = {"operation": operation, "actor": actor.actor_id, **payload}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _plan(plan: JourneyPlan) -> dict:
    return {
        "plan_id": plan.plan_id,
        "tenant_id": plan.tenant_id,
        "family_id": plan.family_id,
        "onboarding_id": plan.onboarding_id,
        "priority_id": plan.priority_id,
        "status": plan.status.value,
        "horizon_days": 21,
        "current_day": plan.current_day,
        "current_phase": plan.current_phase.value,
        "phases": [
            {
                "phase": phase.phase.value,
                "start_day": phase.start_day,
                "end_day": phase.end_day,
                "review_due_day": phase.review_due_day,
                "status": phase.status.value,
            }
            for phase in plan.phases
        ],
        "confirmed_by": plan.confirmed_by,
        "confirmed_at": plan.confirmed_at.isoformat() if plan.confirmed_at else None,
        "policy_version": PLAN_POLICY_VERSION,
        "boundary": PLAN_BOUNDARY,
    }


def _action(action: JourneyAction) -> dict:
    return {
        "action_id": action.action_id,
        "plan_id": action.plan_id,
        "day_no": action.day_no,
        "action_text": action.action_text,
        "actor_id": action.actor_id,
        "recorded_at": action.recorded_at.isoformat(),
    }


def _review(review: PhaseReview) -> dict:
    return {
        "review_id": review.review_id,
        "plan_id": review.plan_id,
        "phase": review.phase.value,
        "decision": review.decision.value,
        "notes": review.notes,
        "actor_id": review.actor_id,
        "reviewed_at": review.reviewed_at.isoformat(),
    }


def _projection(
    actor: JourneyActor,
    plan: JourneyPlan | None,
    lists: tuple[list[JourneyAction], list[PhaseReview]],
) -> dict:
    actions, reviews = lists
    return {
        "family_id": actor.family_id,
        "plan": _plan(plan) if plan else None,
        "actions": [_action(item) for item in actions],
        "reviews": [_review(item) for item in reviews],
        "process_boundary": "JOURNEY_PROGRESS_IS_SCHEDULE_STATE_NOT_GROWTH_OUTCOME",
        "outcome_status": "NOT_MEASURED",
    }


__all__ = ["HumanFamilyPolicy", "JourneyService"]
