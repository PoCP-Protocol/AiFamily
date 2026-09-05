"""Accepted Human Gate action adapter for creating a JourneyPlan DRAFT."""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from backend.apps.family_api.growth_plan_activation_wiring import (
    JourneyPlanActivationHumanGateApplication,
)
from backend.apps.family_api.growth_plan_review_wiring import (
    CREATE_JOURNEY_PLAN_ACTION,
    SqlAlchemyGrowthPlanDraftRegistry,
)
from backend.domains.journey.application.service import JourneyActor
from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.human_gate import ActorType, GateScope, NamedActionRequest
from backend.intelligence.tool_runtime.accepted_dispatch import ActionExecutionReceipt


class GrowthPlanAcceptedActionError(RuntimeError):
    """An accepted request no longer satisfies its reviewed bindings."""


class JourneyDraftApplication(Protocol):
    async def create(
        self,
        actor: JourneyActor,
        onboarding_id: str,
        priority_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict: ...


CurrentScopeResolver = Callable[
    [NamedActionRequest],
    ContextScope | Awaitable[ContextScope],
]


@dataclass(frozen=True, slots=True)
class GrowthPlanAcceptedActionHandler:
    """Reverify the immutable draft, then ask Journey to create DRAFT only."""

    draft_registry: SqlAlchemyGrowthPlanDraftRegistry
    scope_resolver: CurrentScopeResolver
    journey: JourneyDraftApplication
    activation_review: JourneyPlanActivationHumanGateApplication | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if not callable(self.scope_resolver) or not callable(self.clock):
            raise TypeError("growth plan accepted-action resolvers must be callable")
        if not callable(getattr(self.journey, "create", None)):
            raise TypeError("journey draft application must expose create")

    async def __call__(self, request: NamedActionRequest) -> ActionExecutionReceipt:
        if not isinstance(request, NamedActionRequest):
            raise GrowthPlanAcceptedActionError("NAMED_ACTION_REQUEST_REQUIRED")
        if request.action_name != CREATE_JOURNEY_PLAN_ACTION:
            raise GrowthPlanAcceptedActionError("GROWTH_PLAN_ACTION_NAME_MISMATCH")
        if request.actor_type is not ActorType.GUARDIAN:
            raise GrowthPlanAcceptedActionError("GROWTH_PLAN_GUARDIAN_REQUIRED")

        scope = self.scope_resolver(request)
        if inspect.isawaitable(scope):
            scope = await scope
        if not isinstance(scope, ContextScope):
            raise GrowthPlanAcceptedActionError("CURRENT_GROWTH_PLAN_SCOPE_REQUIRED")
        _assert_gate_scope(request.scope, scope)
        arguments = dict(request.action_arguments)
        draft_id = _required_argument(arguments, "draft_id")
        stored = await self.draft_registry.resolve(
            scope=scope,
            draft_id=draft_id,
            now=self.clock(),
        )
        expected = {
            "draft_id": stored.identity.draft_id,
            "intent_id": stored.intent_id,
            "onboarding_id": stored.onboarding_id,
            "priority_id": stored.priority_id,
            "draft_digest": stored.stable_digest,
        }
        if arguments != expected:
            raise GrowthPlanAcceptedActionError("GROWTH_PLAN_ACTION_BINDING_MISMATCH")
        if request.provenance_ref != stored.identity.provenance_ref:
            raise GrowthPlanAcceptedActionError("GROWTH_PLAN_PROVENANCE_MISMATCH")

        projection = await self.journey.create(
            JourneyActor(actor_id=request.actor_id, family_id=scope.family_id),
            stored.onboarding_id,
            stored.priority_id,
            _domain_idempotency_key("create", request.idempotency_key),
            request.scope.correlation_id,
        )
        plan = projection.get("plan")
        if not isinstance(plan, dict) or plan.get("status") != "DRAFT":
            raise GrowthPlanAcceptedActionError("JOURNEY_DRAFT_CREATION_BOUNDARY_VIOLATED")
        plan_id = plan.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id.strip():
            raise GrowthPlanAcceptedActionError("JOURNEY_DRAFT_ID_MISSING")
        if self.activation_review is not None:
            await self.activation_review.submit(
                scope=scope,
                plan_id=plan_id,
                source_draft_id=stored.identity.draft_id,
                source_draft_digest=stored.stable_digest,
                provenance_ref=stored.identity.provenance_ref,
            )
        return ActionExecutionReceipt(
            request_id=request.request_id,
            action_name=request.action_name,
            result_ref=plan_id,
        )


def _assert_gate_scope(gate_scope: GateScope, current: ContextScope) -> None:
    current.assert_active()
    if (
        gate_scope.tenant_id != current.tenant_id
        or gate_scope.family_id != current.family_id
        or gate_scope.subject_ids != current.subject_ids
        or gate_scope.purpose != current.purpose
        or gate_scope.consent_version != current.consent_version
    ):
        raise GrowthPlanAcceptedActionError("GROWTH_PLAN_CURRENT_SCOPE_MISMATCH")


def _required_argument(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise GrowthPlanAcceptedActionError(f"{name.upper()}_REQUIRED")
    return value


def _domain_idempotency_key(operation: str, source: str) -> str:
    digest = hashlib.sha256(source.encode()).hexdigest()
    return f"growth-plan-{operation}:{digest}"


__all__ = [
    "GrowthPlanAcceptedActionError",
    "GrowthPlanAcceptedActionHandler",
    "JourneyDraftApplication",
]
