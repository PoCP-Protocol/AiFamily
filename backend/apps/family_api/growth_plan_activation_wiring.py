"""Second guardian gate for activating an AI-originated JourneyPlan draft."""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.growth_plan_review_wiring import (
    SqlAlchemyGrowthPlanDraftRegistry,
)
from backend.domains.journey.application.service import JourneyActor
from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.human_gate import (
    ActionProposal,
    ActorType,
    GateScope,
    HumanTask,
    NamedActionRequest,
    SqlAlchemyHumanGate,
)
from backend.intelligence.tool_runtime.accepted_dispatch import ActionExecutionReceipt
from backend.platform.audit import AuditRecorder

CONFIRM_JOURNEY_PLAN_ACTION = "CONFIRM_AI_JOURNEY_PLAN"


class GrowthPlanActivationError(RuntimeError):
    """The activation request no longer matches its reviewed draft and scope."""


class JourneyActivationApplication(Protocol):
    async def get_current(self, actor: JourneyActor) -> dict: ...

    async def confirm(
        self,
        actor: JourneyActor,
        plan_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict: ...


class DailyActionInitializer(Protocol):
    async def initialize_from_ai_plan(
        self,
        *,
        actor: JourneyActor,
        tenant_id: str,
        plan_id: str,
        assignment_text: str,
        source_draft_id: str,
        source_draft_digest: str,
        source_provenance_ref: str,
        source_consent_version: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> object: ...


CurrentScopeResolver = Callable[
    [NamedActionRequest], ContextScope | Awaitable[ContextScope]
]


@dataclass(frozen=True, slots=True)
class JourneyPlanActivationHumanGateApplication:
    """Open a distinct guardian review task after a Journey DRAFT exists."""

    session_factory: async_sessionmaker[AsyncSession]
    clock: Callable[[], datetime]
    review_ttl: timedelta = timedelta(days=7)

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("journey activation review requires async_sessionmaker")
        if not callable(self.clock):
            raise TypeError("journey activation review clock must be callable")
        if self.review_ttl <= timedelta(0):
            raise ValueError("journey activation review TTL must be positive")

    async def submit(
        self,
        *,
        scope: ContextScope,
        plan_id: str,
        source_draft_id: str,
        source_draft_digest: str,
        provenance_ref: str,
    ) -> HumanTask:
        scope.assert_active()
        for value, name in (
            (plan_id, "plan_id"),
            (source_draft_id, "source_draft_id"),
            (source_draft_digest, "source_draft_digest"),
            (provenance_ref, "provenance_ref"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise GrowthPlanActivationError(f"{name.upper()}_REQUIRED")
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise GrowthPlanActivationError("ACTIVATION_REVIEW_TIMEZONE_REQUIRED")
        proposal = ActionProposal(
            proposal_id=f"journey-activation:{source_draft_digest}:{plan_id}",
            draft_id=plan_id,
            draft_status="DRAFT",
            action_name=CONFIRM_JOURNEY_PLAN_ACTION,
            action_arguments={
                "plan_id": plan_id,
                "source_draft_id": source_draft_id,
                "source_draft_digest": source_draft_digest,
            },
            scope=GateScope(
                tenant_id=scope.tenant_id,
                family_id=scope.family_id,
                subject_ids=scope.subject_ids,
                purpose=scope.purpose,
                consent_version=scope.consent_version,
                correlation_id=scope.correlation_id,
            ),
            allowed_actor_types=(ActorType.GUARDIAN,),
            risk_level="HIGH",
            provenance_ref=provenance_ref,
            created_at=now.astimezone(UTC),
            expires_at=(now + self.review_ttl).astimezone(UTC),
        )
        async with self.session_factory() as session:
            recorder = AuditRecorder()
            gate = SqlAlchemyHumanGate(session)
            task = await gate.submit(proposal, recorder=recorder)
            await gate.flush_audit(recorder)
            await gate.commit()
            return task


@dataclass(frozen=True, slots=True)
class JourneyPlanActivationAcceptedActionHandler:
    """Revalidate the source AI draft and current DRAFT before activation."""

    draft_registry: SqlAlchemyGrowthPlanDraftRegistry
    scope_resolver: CurrentScopeResolver
    journey: JourneyActivationApplication
    daily_action_initializer: DailyActionInitializer | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if not callable(self.scope_resolver) or not callable(self.clock):
            raise TypeError("journey activation resolvers must be callable")
        if not callable(getattr(self.journey, "get_current", None)) or not callable(
            getattr(self.journey, "confirm", None)
        ):
            raise TypeError("journey activation application is incomplete")

    async def __call__(self, request: NamedActionRequest) -> ActionExecutionReceipt:
        if request.action_name != CONFIRM_JOURNEY_PLAN_ACTION:
            raise GrowthPlanActivationError("JOURNEY_ACTIVATION_ACTION_NAME_MISMATCH")
        if request.actor_type is not ActorType.GUARDIAN:
            raise GrowthPlanActivationError("JOURNEY_ACTIVATION_GUARDIAN_REQUIRED")
        scope = self.scope_resolver(request)
        if inspect.isawaitable(scope):
            scope = await scope
        if not isinstance(scope, ContextScope):
            raise GrowthPlanActivationError("CURRENT_JOURNEY_ACTIVATION_SCOPE_REQUIRED")
        _assert_scope(request.scope, scope)

        arguments = dict(request.action_arguments)
        plan_id = _required(arguments, "plan_id")
        source_draft_id = _required(arguments, "source_draft_id")
        source_digest = _required(arguments, "source_draft_digest")
        if set(arguments) != {"plan_id", "source_draft_id", "source_draft_digest"}:
            raise GrowthPlanActivationError("JOURNEY_ACTIVATION_ARGUMENTS_INVALID")
        stored = await self.draft_registry.resolve(
            scope=scope,
            draft_id=source_draft_id,
            now=self.clock(),
        )
        if stored.stable_digest != source_digest:
            raise GrowthPlanActivationError("JOURNEY_ACTIVATION_DRAFT_DIGEST_MISMATCH")
        if request.provenance_ref != stored.identity.provenance_ref:
            raise GrowthPlanActivationError("JOURNEY_ACTIVATION_PROVENANCE_MISMATCH")

        actor = JourneyActor(actor_id=request.actor_id, family_id=scope.family_id)
        current = await self.journey.get_current(actor)
        current_plan = current.get("plan")
        if (
            not isinstance(current_plan, dict)
            or current_plan.get("plan_id") != plan_id
            or current_plan.get("status") != "DRAFT"
        ):
            raise GrowthPlanActivationError("JOURNEY_ACTIVATION_REQUIRES_CURRENT_DRAFT")
        projection = await self.journey.confirm(
            actor,
            plan_id,
            _domain_idempotency_key("confirm", request.idempotency_key),
            request.scope.correlation_id,
        )
        activated = projection.get("plan")
        if not isinstance(activated, dict) or activated.get("status") != "ACTIVE":
            raise GrowthPlanActivationError("JOURNEY_ACTIVATION_BOUNDARY_VIOLATED")
        if self.daily_action_initializer is not None:
            await self.daily_action_initializer.initialize_from_ai_plan(
                actor=actor,
                tenant_id=scope.tenant_id,
                plan_id=plan_id,
                assignment_text=_first_small_action(stored),
                source_draft_id=stored.identity.draft_id,
                source_draft_digest=stored.stable_digest,
                source_provenance_ref=stored.identity.provenance_ref,
                source_consent_version=scope.consent_version,
                idempotency_key=_domain_idempotency_key("action", request.idempotency_key),
                correlation_id=request.scope.correlation_id,
            )
        return ActionExecutionReceipt(
            request_id=request.request_id,
            action_name=request.action_name,
            result_ref=plan_id,
        )


def _assert_scope(reviewed: GateScope, current: ContextScope) -> None:
    current.assert_active()
    if (
        reviewed.tenant_id != current.tenant_id
        or reviewed.family_id != current.family_id
        or reviewed.subject_ids != current.subject_ids
        or reviewed.purpose != current.purpose
        or reviewed.consent_version != current.consent_version
    ):
        raise GrowthPlanActivationError("JOURNEY_ACTIVATION_CURRENT_SCOPE_MISMATCH")


def _required(arguments: dict[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise GrowthPlanActivationError(f"{name.upper()}_REQUIRED")
    return value


def _first_small_action(stored) -> str:
    stages = stored.model_draft.draft.output.get("stages")
    if not isinstance(stages, list) or not stages or not isinstance(stages[0], dict):
        raise GrowthPlanActivationError("JOURNEY_ACTIVATION_ACTION_DRAFT_MISSING")
    actions = stages[0].get("small_actions")
    if not isinstance(actions, list) or not actions:
        raise GrowthPlanActivationError("JOURNEY_ACTIVATION_ACTION_DRAFT_MISSING")
    value = actions[0]
    if not isinstance(value, str) or not value.strip():
        raise GrowthPlanActivationError("JOURNEY_ACTIVATION_ACTION_DRAFT_MISSING")
    return value.strip()


def _domain_idempotency_key(operation: str, source: str) -> str:
    digest = hashlib.sha256(source.encode()).hexdigest()
    return f"growth-plan-{operation}:{digest}"


__all__ = [
    "CONFIRM_JOURNEY_PLAN_ACTION",
    "DailyActionInitializer",
    "GrowthPlanActivationError",
    "JourneyActivationApplication",
    "JourneyPlanActivationAcceptedActionHandler",
    "JourneyPlanActivationHumanGateApplication",
]
