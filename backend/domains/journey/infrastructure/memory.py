"""Synthetic repository used by unit and contract tests only.

This adapter is intentionally not wired into ``family_api``. A production
composition root must provide a PostgreSQL implementation with one transaction
covering the plan/action/review fact, idempotency receipt, audit event, and
outbox event.
"""

from __future__ import annotations

from ..domain.models import JourneyAction, JourneyPlan, PhaseReview


class InMemoryJourneyRepository:
    """Tenant-scoped repository with deterministic read semantics."""

    def __init__(self) -> None:
        self._plans: dict[str, JourneyPlan] = {}
        self._actions: dict[str, list[JourneyAction]] = {}
        self._reviews: dict[str, list[PhaseReview]] = {}
        self._priorities: set[tuple[str, str, str, str]] = set()
        self._idempotency: dict[tuple[str, str, str, str], tuple[str, dict]] = {}

    def add_confirmed_priority(
        self, *, tenant_id: str, family_id: str, onboarding_id: str, priority_id: str
    ) -> None:
        self._priorities.add((tenant_id, family_id, onboarding_id, priority_id))

    async def has_confirmed_priority(
        self, tenant_id: str, family_id: str, onboarding_id: str, priority_id: str
    ) -> bool:
        return (tenant_id, family_id, onboarding_id, priority_id) in self._priorities

    async def get_current(
        self, tenant_id: str, family_id: str, onboarding_id: str | None = None
    ) -> JourneyPlan | None:
        candidates = [
            plan
            for plan in self._plans.values()
            if plan.tenant_id == tenant_id
            and plan.family_id == family_id
            and (onboarding_id is None or plan.onboarding_id == onboarding_id)
        ]
        return max(candidates, key=lambda item: item.created_at, default=None)

    async def get(self, tenant_id: str, family_id: str, plan_id: str) -> JourneyPlan | None:
        plan = self._plans.get(plan_id)
        if plan is None or plan.tenant_id != tenant_id or plan.family_id != family_id:
            return None
        return plan

    async def save_plan(self, plan: JourneyPlan) -> None:
        self._plans[plan.plan_id] = plan

    async def append_action(self, action: JourneyAction) -> None:
        actions = self._actions.setdefault(action.plan_id, [])
        if any(item.idempotency_key == action.idempotency_key for item in actions):
            return
        actions.append(action)

    async def list_actions(
        self, tenant_id: str, family_id: str, plan_id: str
    ) -> list[JourneyAction]:
        return [
            action
            for action in self._actions.get(plan_id, [])
            if action.tenant_id == tenant_id and action.family_id == family_id
        ]

    async def append_review(self, review: PhaseReview) -> None:
        reviews = self._reviews.setdefault(review.plan_id, [])
        if any(item.review_id == review.review_id for item in reviews):
            return
        reviews.append(review)

    async def list_reviews(self, tenant_id: str, family_id: str, plan_id: str) -> list[PhaseReview]:
        return [
            review
            for review in self._reviews.get(plan_id, [])
            if review.tenant_id == tenant_id and review.family_id == family_id
        ]

    async def load_idempotency(
        self, tenant_id: str, family_id: str, operation: str, key: str
    ) -> tuple[str, dict] | None:
        return self._idempotency.get((tenant_id, family_id, operation, key))

    async def save_idempotency(
        self,
        tenant_id: str,
        family_id: str,
        operation: str,
        key: str,
        fingerprint: str,
        response: dict,
    ) -> None:
        self._idempotency.setdefault(
            (tenant_id, family_id, operation, key), (fingerprint, response)
        )


__all__ = ["InMemoryJourneyRepository"]
