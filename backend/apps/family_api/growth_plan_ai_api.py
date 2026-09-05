"""Authenticated HTTP boundary for the UI-05 AI growth-plan workflow."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.production_growth_plan_ai_wiring import (
    ProductionGrowthPlanAiComposition,
)
from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    HumanTask,
    SqlAlchemyHumanGate,
)
from backend.platform.audit import AuditRecorder


@dataclass(frozen=True, slots=True)
class GrowthPlanHttpIdentity:
    tenant_id: str
    family_id: str
    actor_id: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.tenant_id, self.family_id, self.actor_id)
        ):
            raise ValueError("trusted growth plan identity is incomplete")


IdentityResolver = Callable[
    [str, str | None, str | None, str | None],
    GrowthPlanHttpIdentity | Awaitable[GrowthPlanHttpIdentity],
]
ScopeResolver = Callable[
    [GrowthPlanHttpIdentity, str, str | None, str | None, str | None],
    ContextScope | Awaitable[ContextScope],
]
CompositionResolver = Callable[
    [GrowthPlanHttpIdentity, ContextScope],
    ProductionGrowthPlanAiComposition | Awaitable[ProductionGrowthPlanAiComposition],
]


@dataclass(frozen=True, slots=True)
class GrowthPlanAiHttpDependencies:
    session_factory: async_sessionmaker[AsyncSession]
    identity_resolver: IdentityResolver
    scope_resolver: ScopeResolver
    composition_resolver: CompositionResolver
    clock: Callable[[], datetime]

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("growth plan HTTP requires async_sessionmaker")
        if not all(
            callable(value)
            for value in (
                self.identity_resolver,
                self.scope_resolver,
                self.composition_resolver,
                self.clock,
            )
        ):
            raise TypeError("growth plan HTTP dependencies must be callable")


class SubjectRequest(BaseModel):
    subject_id: str = Field(min_length=1, max_length=160)


class HumanDecisionRequest(BaseModel):
    outcome: DecisionOutcome
    reason: str | None = Field(default=None, max_length=1000)


def build_growth_plan_ai_router(dependencies: GrowthPlanAiHttpDependencies) -> APIRouter:
    """Build one request-authenticated router without client-owned scope fields."""

    if not isinstance(dependencies, GrowthPlanAiHttpDependencies):
        raise TypeError("growth plan HTTP dependencies are required")
    router = APIRouter(prefix="/families", tags=["growth-plan-ai"])

    @router.post(
        "/{family_id}/growth/onboardings/{onboarding_id}/ai-plan-drafts",
        status_code=status.HTTP_201_CREATED,
    )
    async def generate_plan_draft(
        family_id: str,
        onboarding_id: str,
        body: SubjectRequest,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        identity, scope, composition = await _request_context(
            dependencies,
            family_id=family_id,
            subject_id=body.subject_id,
            authorization=authorization,
            correlation_id=x_correlation_id,
            causation_id=x_causation_id,
        )
        del identity
        evidence = await composition.build_evidence_reader().load(
            scope=scope,
            onboarding_id=onboarding_id,
        )
        return await composition.build_draft_adapter().generate(family_id, evidence)

    @router.post(
        "/{family_id}/growth/ai-plan-drafts/{draft_id}/review",
        status_code=status.HTTP_201_CREATED,
    )
    async def submit_plan_review(
        family_id: str,
        draft_id: str,
        body: SubjectRequest,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        _, scope, composition = await _request_context(
            dependencies,
            family_id=family_id,
            subject_id=body.subject_id,
            authorization=authorization,
            correlation_id=x_correlation_id,
            causation_id=x_causation_id,
        )
        task = await composition.build_review_application().submit(
            scope=scope,
            draft_id=draft_id,
        )
        return _task_projection(task)

    @router.post("/{family_id}/growth/human-tasks/{task_id}/decisions")
    async def decide_growth_plan_task(
        family_id: str,
        task_id: str,
        body: HumanDecisionRequest,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        identity = await _identity(
            dependencies,
            family_id,
            authorization,
            x_correlation_id,
            x_causation_id,
        )
        async with dependencies.session_factory() as session:
            gate = SqlAlchemyHumanGate(session)
            task = await gate.get(task_id)
            if (
                task.proposal.scope.tenant_id != identity.tenant_id
                or task.proposal.scope.family_id != identity.family_id
            ):
                raise HTTPException(status_code=404, detail="growth_plan_task_not_found")
            recorder = AuditRecorder()
            decided, request = await gate.decide(
                task_id,
                actor_id=identity.actor_id,
                actor_type=ActorType.GUARDIAN,
                outcome=body.outcome,
                reason=body.reason,
                recorder=recorder,
                now=dependencies.clock(),
            )
            await gate.flush_audit(recorder)
            await gate.commit()
        projection = _task_projection(decided)
        projection["accepted_action_queued"] = request is not None
        return projection

    return router


async def _request_context(
    dependencies: GrowthPlanAiHttpDependencies,
    *,
    family_id: str,
    subject_id: str,
    authorization: str | None,
    correlation_id: str | None,
    causation_id: str | None,
) -> tuple[GrowthPlanHttpIdentity, ContextScope, ProductionGrowthPlanAiComposition]:
    identity = await _identity(
        dependencies,
        family_id,
        authorization,
        correlation_id,
        causation_id,
    )
    try:
        scope = await _await(
            dependencies.scope_resolver(
                identity,
                subject_id,
                authorization,
                correlation_id,
                causation_id,
            )
        )
    except PermissionError as error:
        raise HTTPException(
            status_code=403,
            detail="growth_plan_scope_denied",
        ) from error
    if not isinstance(scope, ContextScope):
        raise TypeError("growth plan scope resolver must return ContextScope")
    if scope.tenant_id != identity.tenant_id or scope.family_id != identity.family_id:
        raise PermissionError("GROWTH_PLAN_HTTP_SCOPE_MISMATCH")
    if scope.subject_ids != (subject_id,):
        raise PermissionError("GROWTH_PLAN_HTTP_SUBJECT_MISMATCH")
    composition = await _await(dependencies.composition_resolver(identity, scope))
    if not isinstance(composition, ProductionGrowthPlanAiComposition):
        raise TypeError(
            "growth plan composition resolver must return ProductionGrowthPlanAiComposition"
        )
    return identity, scope, composition


async def _identity(
    dependencies: GrowthPlanAiHttpDependencies,
    family_id: str,
    authorization: str | None,
    correlation_id: str | None,
    causation_id: str | None,
) -> GrowthPlanHttpIdentity:
    try:
        identity = await _await(
            dependencies.identity_resolver(
                family_id,
                authorization,
                correlation_id,
                causation_id,
            )
        )
    except PermissionError as error:
        raise HTTPException(
            status_code=401,
            detail="growth_plan_authentication_required",
        ) from error
    if not isinstance(identity, GrowthPlanHttpIdentity):
        raise TypeError("growth plan identity resolver must return GrowthPlanHttpIdentity")
    if identity.family_id != family_id:
        raise HTTPException(status_code=403, detail="growth_plan_family_access_denied")
    return identity


async def _await(value: object) -> object:
    return await value if inspect.isawaitable(value) else value


def _task_projection(task: HumanTask) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "action_name": task.proposal.action_name,
        "draft_id": task.proposal.draft_id,
        "risk_level": task.proposal.risk_level,
        "expires_at": task.proposal.expires_at.isoformat(),
    }


__all__ = [
    "GrowthPlanAiHttpDependencies",
    "GrowthPlanHttpIdentity",
    "HumanDecisionRequest",
    "SubjectRequest",
    "build_growth_plan_ai_router",
]
