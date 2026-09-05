"""Authenticated UI-09 HTTP boundary owned by the Action domain."""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.apps.family_api.growth_plan_ai_api import GrowthPlanHttpIdentity
from backend.domains.action.application.daily_action import (
    ActionActor,
    ActionEventScope,
    DailyActionCompletion,
    DailyActionTransition,
)
from backend.domains.action.domain.errors import (
    ActionConflictError,
    ActionForbiddenError,
    ActionNotFoundError,
    ActionValidationError,
)
from backend.domains.action.infrastructure.postgres import (
    SqlAlchemyDailyActionApplication,
)
from backend.intelligence.context_engine.contracts import ContextScope

IdentityResolver = Callable[
    [str, str | None, str | None, str | None],
    GrowthPlanHttpIdentity | Awaitable[GrowthPlanHttpIdentity],
]
SubjectResolver = Callable[
    [GrowthPlanHttpIdentity],
    str | Awaitable[str],
]
ScopeResolver = Callable[
    [GrowthPlanHttpIdentity, str, str | None, str | None, str | None],
    ContextScope | Awaitable[ContextScope],
]


@dataclass(frozen=True, slots=True)
class DailyActionHttpDependencies:
    application: SqlAlchemyDailyActionApplication
    identity_resolver: IdentityResolver
    subject_resolver: SubjectResolver
    scope_resolver: ScopeResolver

    def __post_init__(self) -> None:
        if not isinstance(self.application, SqlAlchemyDailyActionApplication):
            raise TypeError("daily action HTTP requires SqlAlchemyDailyActionApplication")
        if not all(
            callable(value)
            for value in (
                self.identity_resolver,
                self.subject_resolver,
                self.scope_resolver,
            )
        ):
            raise TypeError("daily action HTTP resolvers must be callable")


class StateTransitionRequest(BaseModel):
    action: DailyActionTransition
    occurred_at: datetime
    expected_task_version: int | None = Field(default=None, ge=1)


class CheckInRequest(BaseModel):
    completion_status: DailyActionCompletion
    reflection: str = Field(default="", max_length=2000)
    occurred_at: datetime
    expected_task_version: int | None = Field(default=None, ge=1)


def build_daily_action_router(dependencies: DailyActionHttpDependencies) -> APIRouter:
    if not isinstance(dependencies, DailyActionHttpDependencies):
        raise TypeError("daily action HTTP dependencies are required")
    router = APIRouter(prefix="/families", tags=["daily-action"])

    @router.get("/{family_id}/today")
    async def get_today(
        family_id: str,
        authorization: str | None = Header(default=None),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        identity, subject_id, scope = await _request_scope(
            dependencies,
            family_id=family_id,
            authorization=authorization,
            correlation_id=x_correlation_id,
            causation_id=x_causation_id,
        )
        return await dependencies.application.get_today(
            actor=ActionActor(identity.actor_id, identity.family_id),
            tenant_id=identity.tenant_id,
            subject_person_id=subject_id,
            consent_version=scope.consent_version,
            approval_ref=f"consent:{scope.consent_version}",
            correlation_id=scope.correlation_id,
        )

    @router.post("/{family_id}/tasks/{task_id}/state")
    async def change_state(
        family_id: str,
        task_id: str,
        body: StateTransitionRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        identity, _, scope = await _request_scope(
            dependencies,
            family_id=family_id,
            authorization=authorization,
            correlation_id=x_correlation_id,
            causation_id=x_causation_id,
        )
        key = _require_idempotency_key(idempotency_key)
        try:
            return await dependencies.application.transition(
                actor=ActionActor(identity.actor_id, identity.family_id),
                tenant_id=identity.tenant_id,
                task_id=task_id,
                transition=body.action,
                expected_task_version=_expected_version(
                    body.expected_task_version,
                    key,
                ),
                event_scope=_action_event_scope(scope, subject_id=scope.subject_ids[0]),
                occurred_at=body.occurred_at,
                idempotency_key=key,
                correlation_id=scope.correlation_id,
            )
        except Exception as error:
            _raise_action_http_error(error)
            raise

    @router.post("/{family_id}/tasks/{task_id}/check-in")
    async def check_in(
        family_id: str,
        task_id: str,
        body: CheckInRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> dict[str, object]:
        identity, _, scope = await _request_scope(
            dependencies,
            family_id=family_id,
            authorization=authorization,
            correlation_id=x_correlation_id,
            causation_id=x_causation_id,
        )
        key = _require_idempotency_key(idempotency_key)
        try:
            return await dependencies.application.check_in(
                actor=ActionActor(identity.actor_id, identity.family_id),
                tenant_id=identity.tenant_id,
                task_id=task_id,
                completion=body.completion_status,
                reflection=body.reflection,
                expected_task_version=_expected_version(
                    body.expected_task_version,
                    key,
                ),
                event_scope=_action_event_scope(scope, subject_id=scope.subject_ids[0]),
                occurred_at=body.occurred_at,
                idempotency_key=key,
                correlation_id=scope.correlation_id,
            )
        except Exception as error:
            _raise_action_http_error(error)
            raise

    return router


async def _request_scope(
    dependencies: DailyActionHttpDependencies,
    *,
    family_id: str,
    authorization: str | None,
    correlation_id: str | None,
    causation_id: str | None,
) -> tuple[GrowthPlanHttpIdentity, str, ContextScope]:
    request_correlation_id = correlation_id or f"ui09:{uuid4()}"
    request_causation_id = causation_id or request_correlation_id
    try:
        identity = await _await(
            dependencies.identity_resolver(
                family_id,
                authorization,
                request_correlation_id,
                request_causation_id,
            )
        )
    except PermissionError as error:
        raise HTTPException(
            status_code=401,
            detail="daily_action_authentication_required",
        ) from error
    if not isinstance(identity, GrowthPlanHttpIdentity):
        raise TypeError("daily action identity resolver returned an invalid identity")
    if identity.family_id != family_id:
        raise HTTPException(status_code=403, detail="daily_action_family_access_denied")
    try:
        subject_id = await _await(dependencies.subject_resolver(identity))
        scope = await _await(
            dependencies.scope_resolver(
                identity,
                subject_id,
                authorization,
                request_correlation_id,
                request_causation_id,
            )
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail="daily_action_scope_denied") from error
    if not isinstance(subject_id, str) or not subject_id.strip():
        raise TypeError("daily action subject resolver returned an invalid subject")
    if not isinstance(scope, ContextScope):
        raise TypeError("daily action scope resolver returned an invalid scope")
    if (
        scope.tenant_id != identity.tenant_id
        or scope.family_id != identity.family_id
        or scope.subject_ids != (subject_id,)
    ):
        raise HTTPException(status_code=403, detail="daily_action_scope_mismatch")
    scope.assert_active()
    return identity, subject_id, scope


def _require_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise HTTPException(status_code=400, detail="idempotency_key_required")
    return value.strip()


def _expected_version(explicit: int | None, idempotency_key: str) -> int:
    if explicit is not None:
        return explicit
    match = re.search(r"-v(?P<version>[1-9][0-9]*)(?:-|$)", idempotency_key)
    if match is None:
        raise HTTPException(status_code=400, detail="expected_task_version_required")
    return int(match.group("version"))


def _raise_action_http_error(error: Exception) -> None:
    if isinstance(error, ActionValidationError):
        raise HTTPException(status_code=400, detail=error.code) from error
    if isinstance(error, ActionForbiddenError):
        raise HTTPException(status_code=403, detail=error.code) from error
    if isinstance(error, ActionNotFoundError):
        raise HTTPException(status_code=404, detail=error.code) from error
    if isinstance(error, ActionConflictError):
        raise HTTPException(status_code=409, detail=error.code) from error


def _action_event_scope(scope: ContextScope, *, subject_id: str) -> ActionEventScope:
    return ActionEventScope(
        tenant_id=scope.tenant_id,
        region_id=scope.region_id,
        subject_person_id=subject_id,
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        deletion_ref=scope.deletion_ref,
        locale=scope.effective_content_locale,
    )


async def _await(value: object) -> object:
    return await value if inspect.isawaitable(value) else value


__all__ = [
    "CheckInRequest",
    "DailyActionHttpDependencies",
    "StateTransitionRequest",
    "build_daily_action_router",
]
