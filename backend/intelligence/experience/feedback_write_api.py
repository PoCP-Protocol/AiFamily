"""Authenticated write API for family-private achievement feedback."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.apps.family_api.growth_plan_ai_api import GrowthPlanHttpIdentity
from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceScope,
    FeedbackSignalType,
)
from backend.intelligence.experience.feedback_write import (
    AchievementFeedbackConflict,
    AchievementFeedbackNotFound,
    AchievementFeedbackReceipt,
    AchievementFeedbackValidation,
    SqlAlchemyAchievementFeedbackApplication,
)
from backend.intelligence.model_gateway.contracts import DataClass

IdentityResolver = Callable[
    [str, str | None, str | None, str | None],
    GrowthPlanHttpIdentity | Awaitable[GrowthPlanHttpIdentity],
]
SubjectResolver = Callable[[GrowthPlanHttpIdentity], str | Awaitable[str]]
ScopeResolver = Callable[
    [GrowthPlanHttpIdentity, str, str | None, str | None, str | None],
    ContextScope | Awaitable[ContextScope],
]


@dataclass(frozen=True, slots=True)
class AchievementFeedbackHttpDependencies:
    application: SqlAlchemyAchievementFeedbackApplication
    identity_resolver: IdentityResolver
    subject_resolver: SubjectResolver
    scope_resolver: ScopeResolver

    def __post_init__(self) -> None:
        if not isinstance(self.application, SqlAlchemyAchievementFeedbackApplication):
            raise TypeError("achievement feedback application is required")
        if not all(
            callable(item)
            for item in (self.identity_resolver, self.subject_resolver, self.scope_resolver)
        ):
            raise TypeError("achievement feedback resolvers must be callable")


class AchievementFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: FeedbackSignalType
    reason_code: str | None = Field(default=None, min_length=1, max_length=128)
    occurred_at: datetime


class AchievementFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: str
    achievement_id: str
    signal: FeedbackSignalType
    human_task_id: str | None
    result_state: str
    occurred_at: datetime


def build_achievement_feedback_write_router(
    dependencies: AchievementFeedbackHttpDependencies,
) -> APIRouter:
    router = APIRouter(prefix="/families", tags=["experience-feedback"])

    @router.post(
        "/{family_id}/experience/achievements/{achievement_id}/feedback",
        response_model=AchievementFeedbackResponse,
    )
    async def record_achievement_feedback(
        family_id: str,
        achievement_id: str,
        body: AchievementFeedbackRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        x_correlation_id: str | None = Header(default=None),
        x_causation_id: str | None = Header(default=None),
    ) -> AchievementFeedbackResponse:
        key = _idempotency_key(idempotency_key)
        try:
            identity = await _resolve(
                dependencies.identity_resolver(
                    family_id,
                    authorization,
                    x_correlation_id,
                    x_causation_id,
                )
            )
            subject_id = await _resolve(dependencies.subject_resolver(identity))
            scope = await _resolve(
                dependencies.scope_resolver(
                    identity,
                    subject_id,
                    authorization,
                    x_correlation_id,
                    x_causation_id,
                )
            )
            receipt = await dependencies.application.record(
                scope=_experience_scope(scope),
                actor_id=identity.actor_id,
                achievement_id=achievement_id,
                signal=body.signal,
                reason_code=body.reason_code,
                idempotency_key=key,
                occurred_at=body.occurred_at,
            )
        except AchievementFeedbackNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except AchievementFeedbackConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except AchievementFeedbackValidation as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except PermissionError as error:
            raise HTTPException(status_code=403, detail="family_access_denied") from error
        return _response(receipt)

    return router


def _experience_scope(scope: object) -> ExperienceScope:
    if not isinstance(scope, ContextScope):
        raise AchievementFeedbackValidation("context_scope_required")
    return ExperienceScope(
        global_id=f"achievement-feedback:{scope.tenant_id}:{scope.family_id}",
        tenant_id=scope.tenant_id,
        region_id=scope.region_id,
        family_id=scope.family_id,
        subject_ids=scope.subject_ids,
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        consent_granted=scope.consent_granted,
        data_class=cast(DataClass, scope.data_class.value),
        locale=scope.locale,
        content_locale=scope.effective_content_locale,
        model_locale=scope.effective_model_locale,
        policy_locale=scope.effective_policy_locale,
        deletion_ref=DeletionRef(scope.deletion_ref, "consent-bound"),
        correlation_id=scope.correlation_id,
        causation_id=scope.causation_id,
    )


def _response(receipt: AchievementFeedbackReceipt) -> AchievementFeedbackResponse:
    return AchievementFeedbackResponse(
        feedback_id=receipt.feedback_id,
        achievement_id=receipt.achievement_id,
        signal=receipt.signal,
        human_task_id=receipt.human_task_id,
        result_state="REPLAYED" if receipt.replayed else "RECORDED",
        occurred_at=receipt.occurred_at,
    )


def _idempotency_key(value: str | None) -> str:
    if value is None or not value.strip() or len(value) > 256:
        raise HTTPException(status_code=422, detail="idempotency_key_required")
    return value.strip()


async def _resolve(value: object) -> object:
    return await value if inspect.isawaitable(value) else value


__all__ = [
    "AchievementFeedbackHttpDependencies",
    "AchievementFeedbackRequest",
    "AchievementFeedbackResponse",
    "build_achievement_feedback_write_router",
]
