from __future__ import annotations

from ..domain.models import JourneyPlan


class InMemoryJourneyRepository:
    def __init__(self) -> None:
        self.plans: dict[str, JourneyPlan] = {}
        self.active_priorities: set[tuple[str, str, str]] = set()
        self.priority_dimensions: dict[tuple[str, str, str], str] = {}
        self.active_onboardings: set[tuple[str, str]] = set()
        self.priority_candidates: dict[tuple[str, str], tuple[str, str, str]] = {}
        self.completed_actions: dict[str, int] = {}

    async def get_current(self, family_id: str) -> JourneyPlan | None:
        return next(
            (plan for plan in reversed(tuple(self.plans.values())) if plan.family_id == family_id),
            None,
        )

    async def get(self, family_id: str, plan_id: str) -> JourneyPlan | None:
        plan = self.plans.get(plan_id)
        return plan if plan is not None and plan.family_id == family_id else None

    async def save(self, plan: JourneyPlan) -> None:
        self.plans[plan.plan_id] = plan

    async def is_active_priority(
        self, family_id: str, onboarding_id: str, priority_id: str
    ) -> bool:
        return (family_id, onboarding_id, priority_id) in self.active_priorities

    async def get_active_priority(
        self, family_id: str, onboarding_id: str
    ) -> tuple[str, str] | None:
        match = next(
            (
                priority_id
                for item_family, item_onboarding, priority_id in self.active_priorities
                if item_family == family_id and item_onboarding == onboarding_id
            ),
            None,
        )
        if match is None:
            return None
        dimension = self.priority_dimensions.get((family_id, onboarding_id, match), "R03")
        return match, dimension

    async def is_active_onboarding(self, family_id: str, onboarding_id: str) -> bool:
        return (family_id, onboarding_id) in self.active_onboardings

    async def get_priority_candidate(
        self, family_id: str, onboarding_id: str
    ) -> tuple[str, str, str] | None:
        return self.priority_candidates.get((family_id, onboarding_id))

    async def activate_priority(
        self,
        family_id: str,
        onboarding_id: str,
        priority_id: str,
        profile_id: str,
        subject_person_id: str,
        dimension_id: str,
        actor_id: str,
    ) -> None:
        existing = {
            item
            for item in self.active_priorities
            if item[0] == family_id and item[1] == onboarding_id
        }
        self.active_priorities.difference_update(existing)
        self.active_priorities.add((family_id, onboarding_id, priority_id))
        self.priority_dimensions[(family_id, onboarding_id, priority_id)] = dimension_id

    async def count_completed_actions(self, family_id: str, plan_id: str) -> int:
        plan = self.plans.get(plan_id)
        if plan is None or plan.family_id != family_id:
            return 0
        return self.completed_actions.get(plan_id, 0)
