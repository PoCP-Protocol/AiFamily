"""Standalone HTTP adapter for Scene C result-page next-step choice.

The composition root supplies identity, scope, consent, canonical FamilyNeed,
Intent persistence, and deletion-reference ports.  This file is intentionally
not mounted into the shared ``main.py`` by the Route C change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.platform.identity import ActorContext

from ..application.scene_c import (
    SceneCApplication,
    SceneCConflictError,
    SceneCError,
    SceneCForbiddenError,
    SceneCNotFoundError,
    SceneCValidationError,
)


class SceneCActorResolver(Protocol):
    async def __call__(
        self, authorization: str | None, family_id: str, correlation_id: str
    ) -> ActorContext: ...


@dataclass(frozen=True, slots=True)
class SceneCHttpDependencies:
    resolve_actor: SceneCActorResolver
    application: SceneCApplication


class ChooseNextStepBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need_id: str = Field(min_length=1, max_length=128)
    subject_person_id: str = Field(min_length=1, max_length=128)
    next_step: str = Field(min_length=1, max_length=64)


class WithdrawNextStepBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


def build_scene_c_router(dependencies: SceneCHttpDependencies) -> APIRouter:
    router = APIRouter(prefix="/families")

    @router.post("/{family_id}/result/next-step-choice")
    async def choose_next_step(
        family_id: str,
        body: ChooseNextStepBody,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
    ) -> dict:
        correlation_id = x_correlation_id or idempotency_key or ""
        actor = await _resolve_actor(
            dependencies.resolve_actor, authorization, family_id, correlation_id
        )
        try:
            receipt = await dependencies.application.choose_next_step(
                actor=actor,
                family_id=family_id,
                need_id=body.need_id,
                subject_person_id=body.subject_person_id,
                next_step=body.next_step,
                idempotency_key=idempotency_key or "",
            )
            return receipt.as_dict()
        except SceneCError as error:
            raise _http_error(error) from error

    @router.get("/{family_id}/result/next-step-choice/{intent_id}")
    async def readback_next_step(
        family_id: str,
        intent_id: str,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
    ) -> dict:
        correlation_id = x_correlation_id or idempotency_key or ""
        actor = await _resolve_actor(
            dependencies.resolve_actor, authorization, family_id, correlation_id
        )
        try:
            receipt = await dependencies.application.readback(
                actor=actor,
                family_id=family_id,
                intent_id=intent_id,
                idempotency_key=idempotency_key or "",
            )
            return receipt.as_dict()
        except SceneCError as error:
            raise _http_error(error) from error

    @router.post("/{family_id}/result/next-step-choice/{intent_id}/withdraw")
    async def withdraw_next_step(
        family_id: str,
        intent_id: str,
        body: WithdrawNextStepBody,
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
    ) -> dict:
        correlation_id = x_correlation_id or idempotency_key or ""
        actor = await _resolve_actor(
            dependencies.resolve_actor, authorization, family_id, correlation_id
        )
        try:
            receipt = await dependencies.application.withdraw(
                actor=actor,
                family_id=family_id,
                intent_id=intent_id,
                reason=body.reason,
                idempotency_key=idempotency_key or "",
            )
            return receipt.as_dict()
        except SceneCError as error:
            raise _http_error(error) from error

    return router


async def _resolve_actor(
    resolver: SceneCActorResolver,
    authorization: str | None,
    family_id: str,
    correlation_id: str,
) -> ActorContext:
    try:
        return await resolver(authorization, family_id, correlation_id)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=401, detail="identity_unavailable") from error


def _http_error(error: SceneCError) -> HTTPException:
    if isinstance(error, SceneCValidationError):
        status = 400
    elif isinstance(error, SceneCForbiddenError):
        status = 403
    elif isinstance(error, SceneCNotFoundError):
        status = 404
    elif isinstance(error, SceneCConflictError):
        status = 409
    else:
        status = 400
    return HTTPException(status_code=status, detail=str(error) or error.code)


__all__ = [
    "ChooseNextStepBody",
    "SceneCActorResolver",
    "SceneCHttpDependencies",
    "WithdrawNextStepBody",
    "build_scene_c_router",
]
