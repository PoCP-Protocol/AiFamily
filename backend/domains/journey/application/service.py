from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from ..domain.errors import JourneyConflictError, JourneyNotFoundError
from ..domain.models import GrowthPriorityDecision, JourneyPlan, PhaseDecision


class JourneyRepository(Protocol):
    async def get_current(self, family_id: str) -> JourneyPlan | None: ...

    async def get(self, family_id: str, plan_id: str) -> JourneyPlan | None: ...

    async def save(self, plan: JourneyPlan) -> None: ...

    async def is_active_priority(
        self, family_id: str, onboarding_id: str, priority_id: str
    ) -> bool: ...

    async def get_active_priority(
        self, family_id: str, onboarding_id: str
    ) -> tuple[str, str] | None: ...

    async def is_active_onboarding(self, family_id: str, onboarding_id: str) -> bool: ...

    async def get_priority_candidate(
        self, family_id: str, onboarding_id: str
    ) -> tuple[str, str, str] | None: ...

    async def activate_priority(
        self,
        family_id: str,
        onboarding_id: str,
        priority_id: str,
        profile_id: str,
        subject_person_id: str,
        dimension_id: str,
        actor_id: str,
    ) -> None: ...

    async def count_completed_actions(self, family_id: str, plan_id: str) -> int: ...


class JourneyPolicy(Protocol):
    async def assert_can_read(self, family_id: str, actor_id: str) -> None: ...

    async def assert_can_manage(self, family_id: str, actor_id: str) -> None: ...

    async def assert_creation_preconditions(
        self, family_id: str, onboarding_id: str, actor_id: str
    ) -> None: ...


@dataclass(frozen=True)
class JourneyActor:
    actor_id: str
    family_id: str


class JourneyService:
    def __init__(self, repository: JourneyRepository, policy: JourneyPolicy):
        self._repository = repository
        self._policy = policy
        self._priority_replays: dict[str, tuple[tuple[str, ...], dict]] = {}

    async def get_current(self, actor: JourneyActor) -> dict:
        await self._policy.assert_can_read(actor.family_id, actor.actor_id)
        return _projection(actor.family_id, await self._repository.get_current(actor.family_id))

    async def get_growth_priority(self, actor: JourneyActor, onboarding_id: str) -> dict:
        await self._policy.assert_can_read(actor.family_id, actor.actor_id)
        await self._assert_active_onboarding(actor.family_id, onboarding_id)
        active = await self._repository.get_active_priority(actor.family_id, onboarding_id)
        candidate = await self._repository.get_priority_candidate(actor.family_id, onboarding_id)
        return {
            "family_id": actor.family_id,
            "onboarding_id": onboarding_id,
            "draft": _priority_draft(actor.family_id, onboarding_id, candidate),
            "active_priority": (
                {"priority_id": active[0], "dimension_id": active[1], "status": "ACTIVE"}
                if active
                else None
            ),
            "boundary": "PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS_NOT_SCORE",
        }

    async def confirm_growth_priority(
        self,
        actor: JourneyActor,
        onboarding_id: str,
        draft_id: str,
        decision: GrowthPriorityDecision,
        idempotency_key: str,
        correlation_id: str | None = None,
    ) -> dict:
        await self._policy.assert_can_manage(actor.family_id, actor.actor_id)
        await self._assert_active_onboarding(actor.family_id, onboarding_id)
        fingerprint = (
            actor.family_id,
            onboarding_id,
            draft_id,
            decision.value,
            actor.actor_id,
        )
        replay = self._priority_replays.get(idempotency_key)
        if replay is not None:
            if replay[0] != fingerprint:
                raise JourneyConflictError("idempotency_conflict")
            return replay[1]
        candidate = await self._repository.get_priority_candidate(actor.family_id, onboarding_id)
        draft = _priority_draft(actor.family_id, onboarding_id, candidate)
        if draft["draft_id"] != draft_id:
            raise JourneyConflictError("growth_priority_draft_stale")
        if decision is not GrowthPriorityDecision.NO_PRIORITY_YET:
            if candidate is None or candidate[1] != decision.value:
                raise JourneyConflictError("growth_priority_decision_not_eligible")
            await self._policy.assert_creation_preconditions(
                actor.family_id, onboarding_id, actor.actor_id
            )
            priority_id = str(uuid4())
            await self._repository.activate_priority(
                actor.family_id,
                onboarding_id,
                priority_id,
                candidate[0],
                candidate[2],
                decision.value,
                actor.actor_id,
            )
            priority = {
                "priority_id": priority_id,
                "dimension_id": decision.value,
                "status": "ACTIVE",
            }
        else:
            priority = None
        response = {"priority": priority, "decision": decision.value, "draft": draft}
        self._priority_replays[idempotency_key] = (fingerprint, response)
        return response

    async def get_plan_preview(self, actor: JourneyActor, onboarding_id: str) -> dict:
        await self._policy.assert_can_read(actor.family_id, actor.actor_id)
        await self._assert_active_onboarding(actor.family_id, onboarding_id)
        active = await self._repository.get_active_priority(actor.family_id, onboarding_id)
        return _plan_preview(actor.family_id, onboarding_id, active)

    async def get_service_journey(self, actor: JourneyActor, onboarding_id: str) -> dict:
        await self._policy.assert_can_read(actor.family_id, actor.actor_id)
        await self._assert_active_onboarding(actor.family_id, onboarding_id)
        plan = await self._repository.get_current(actor.family_id)
        if plan is None or plan.onboarding_id != onboarding_id:
            return _service_journey_projection(
                actor.family_id, onboarding_id, None, completed_actions=0
            )
        completed_actions = await self._repository.count_completed_actions(
            actor.family_id, plan.plan_id
        )
        return _service_journey_projection(
            actor.family_id, onboarding_id, plan, completed_actions
        )

    async def refresh_plan_preview(
        self,
        actor: JourneyActor,
        onboarding_id: str,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> dict:
        preview = await self.get_plan_preview(actor, onboarding_id)
        return {**preview, "refreshed": True, "external_effect": False}

    async def create(
        self,
        actor: JourneyActor,
        onboarding_id: str,
        priority_id: str,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> dict:
        await self._policy.assert_can_manage(actor.family_id, actor.actor_id)
        await self._policy.assert_creation_preconditions(
            actor.family_id, onboarding_id, actor.actor_id
        )
        if not await self._repository.is_active_priority(
            actor.family_id, onboarding_id, priority_id
        ):
            raise JourneyNotFoundError("active_growth_priority_not_found")
        existing = await self._repository.get_current(actor.family_id)
        if existing is not None and existing.onboarding_id == onboarding_id:
            return _projection(actor.family_id, existing)
        plan = JourneyPlan.draft(
            str(uuid4()), actor.family_id, onboarding_id, priority_id
        )
        await self._repository.save(plan)
        return _projection(actor.family_id, plan)

    async def confirm(
        self,
        actor: JourneyActor,
        plan_id: str,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> dict:
        await self._policy.assert_can_manage(actor.family_id, actor.actor_id)
        plan = await self._required_plan(actor.family_id, plan_id)
        updated = plan.confirm(actor.actor_id)
        await self._repository.save(updated)
        return _projection(actor.family_id, updated)

    async def review(
        self,
        actor: JourneyActor,
        plan_id: str,
        decision: PhaseDecision,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> dict:
        await self._policy.assert_can_manage(actor.family_id, actor.actor_id)
        plan = await self._required_plan(actor.family_id, plan_id)
        updated = plan.review(decision)
        await self._repository.save(updated)
        return {**_projection(actor.family_id, updated), "decision": decision.value}

    async def _required_plan(self, family_id: str, plan_id: str) -> JourneyPlan:
        plan = await self._repository.get(family_id, plan_id)
        if plan is None:
            raise JourneyNotFoundError("journey_plan_not_found")
        return plan

    async def _assert_active_onboarding(self, family_id: str, onboarding_id: str) -> None:
        if not await self._repository.is_active_onboarding(family_id, onboarding_id):
            raise JourneyNotFoundError("active_growth_onboarding_not_found")


def _projection(family_id: str, plan: JourneyPlan | None) -> dict:
    projected = None
    if plan is not None:
        projected = {
            "plan_id": plan.plan_id,
            "status": plan.status.value,
            "current_phase": plan.current_phase.value,
            "phases": [
                {"phase": item.phase.value, "status": item.status.value}
                for item in plan.phases
            ],
        }
    return {
        "family_id": family_id,
        "plan": projected,
        "fact_boundary": "JOURNEY_PROGRESS_IS_SCHEDULE_STATE_NOT_GROWTH_OUTCOME",
        "recommendation_boundary": (
            "NEXT_PHASE_IS_A_FAMILY_DECISION_NOT_AN_AUTOMATIC_RECOMMENDATION"
        ),
        "model_gateway_status": "NOOP",
    }


_FOCUS_ACTIONS = {
    "P03": "先描述看到的状态，再邀请对方说说感受。",
    "R03": "今天先完整听完，再用一句话确认自己听到了什么。",
    "R04": "一起选一个十分钟时段，讨论一件最想调整的小事。",
    "R05": "遇到分歧时先暂停，约定一个更平静的时间继续。",
}


def _priority_draft(
    family_id: str, onboarding_id: str, candidate: tuple[str, str, str] | None
) -> dict:
    decision = candidate[1] if candidate else GrowthPriorityDecision.NO_PRIORITY_YET.value
    draft_id = str(
        uuid5(
            NAMESPACE_URL,
            f"journey-priority:{family_id}:{onboarding_id}:{candidate}:{decision}:M2_104_DETERMINISTIC_V2",
        )
    )
    return {
        "draft_id": draft_id,
        "decision": decision,
        "candidate": (
            {
                "profile_id": candidate[0],
                "dimension_id": candidate[1],
                "eligibility": "ELIGIBLE",
            }
            if candidate
            else None
        ),
        "policy_version": "M2_104_DETERMINISTIC_V2",
        "boundary": "PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS",
    }


def _plan_preview(
    family_id: str, onboarding_id: str, active: tuple[str, str] | None
) -> dict:
    action = _FOCUS_ACTIONS.get(active[1]) if active else None
    stages = []
    if action:
        stages = [
            {"stage_id": "SEE", "small_action": action},
            {"stage_id": "ADJUST", "small_action": "每周留出一次十分钟的小回顾。"},
            {"stage_id": "CO_CREATE", "small_action": "一起决定下周想尝试的一件事。"},
            {"stage_id": "STABILIZE", "small_action": "选出最想延续的一项家庭约定。"},
        ]
    return {
        "projection_version": "UI05_PLAN_PREVIEW_V1",
        "family_id": family_id,
        "onboarding_id": onboarding_id,
        "state": "FAMILY_REVIEW" if active else "REVIEW_REQUIRED",
        "source_priority_id": active[0] if active else None,
        "structure": {"horizon_days": 90, "stages": stages},
        "model_gateway_status": "NOOP_NOT_INVOKED",
        "next_allowed_action": (
            "REQUEST_FAMILY_DECISION" if active else "HUMAN_REVIEW_REQUIRED"
        ),
        "boundary": "PLAN_PREVIEW_IS_RULE_BASED_DRAFT_NOT_OUTCOME_OR_COMMITMENT",
    }


def _service_journey_projection(
    family_id: str,
    onboarding_id: str,
    plan: JourneyPlan | None,
    completed_actions: int,
) -> dict:
    is_ready = plan is not None and plan.status.value in {"ACTIVE", "PAUSED"}
    label = (
        f"已留下 {completed_actions} 次家庭行动记录"
        if completed_actions
        else "从本周的一件小行动开始"
    )
    return {
        "projection_version": "UI05_SERVICE_JOURNEY_V1",
        "family_id": family_id,
        "onboarding_id": onboarding_id,
        "visibility": "FAMILY_PRIVATE",
        "state": "READY" if is_ready else "REVIEW_REQUIRED",
        "process_summary": {
            "label": label,
            "completed_actions": completed_actions,
            "boundary": "PROCESS_PROJECTION_NOT_SCORE_OR_OUTCOME",
        },
        "source_plan_id": plan.plan_id if plan else None,
        "current_phase": plan.current_phase.value if plan else None,
        "boundary": "SERVICE_JOURNEY_IS_PRIVATE_PROCESS_SUPPORT_NOT_GROWTH_OUTCOME",
    }
