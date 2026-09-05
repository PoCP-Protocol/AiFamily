"""Strict HTTP contract for AI achievement feedback projections."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict

from backend.intelligence.experience.achievement import Achievement
from backend.intelligence.experience.feedback_read import FeedbackReadRuntime


class AchievementFeedbackRuntimeResolver(Protocol):
    async def resolve(self, family_id: str) -> FeedbackReadRuntime: ...


class AchievementFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    achievement_id: str
    key: str
    occurrence_id: str
    title: str
    message: str
    evidence_refs: tuple[str, ...]
    earned_at: datetime


class AchievementFeedbackCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str
    visibility: Literal["FAMILY_PRIVATE"]
    achievements: tuple[AchievementFeedbackResponse, ...]


class AchievementNotificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: str
    achievement_id: str
    title: str
    message: str
    status: Literal["UNREAD"]
    created_at: datetime


class AchievementNotificationCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str
    visibility: Literal["FAMILY_PRIVATE"]
    unread: tuple[AchievementNotificationResponse, ...]


class AchievementNotificationReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: str
    achievement_id: str
    status: Literal["READ"]
    read_at: datetime


class ExperienceAnalyticsMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_key: str
    value_count: int


class ExperienceAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str
    visibility: Literal["FAMILY_PRIVATE"]
    metrics: tuple[ExperienceAnalyticsMetric, ...]


def get_feedback_runtime_resolver() -> AchievementFeedbackRuntimeResolver | None:
    """No identity/consent resolver is installed by default; fail closed."""

    return None


router = APIRouter(prefix="/families", tags=["experience-feedback"])


async def _runtime(
    family_id: str,
    resolver: AchievementFeedbackRuntimeResolver | None,
) -> FeedbackReadRuntime:
    if resolver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="experience_feedback_runtime_not_configured",
        )
    try:
        runtime = await resolver.resolve(family_id)
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="family_access_denied",
        ) from error
    except Exception as error:  # noqa: BLE001 - resolver boundary fails closed
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="experience_feedback_runtime_unavailable",
        ) from error
    if not isinstance(runtime, FeedbackReadRuntime) or runtime.scope.family_id != family_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="experience_feedback_runtime_invalid",
        )
    return runtime


@router.get(
    "/{family_id}/experience/achievements",
    response_model=AchievementFeedbackCollection,
)
async def list_achievements(
    family_id: str,
    resolver: AchievementFeedbackRuntimeResolver | None = Depends(
        get_feedback_runtime_resolver
    ),
) -> AchievementFeedbackCollection:
    runtime = await _runtime(family_id, resolver)
    achievements = await runtime.reader.achievements(runtime.scope)
    return AchievementFeedbackCollection(
        family_id=family_id,
        visibility="FAMILY_PRIVATE",
        achievements=tuple(_achievement_response(item) for item in achievements),
    )


@router.get(
    "/{family_id}/experience/notifications",
    response_model=AchievementNotificationCollection,
)
async def list_notifications(
    family_id: str,
    resolver: AchievementFeedbackRuntimeResolver | None = Depends(
        get_feedback_runtime_resolver
    ),
) -> AchievementNotificationCollection:
    runtime = await _runtime(family_id, resolver)
    unread = await runtime.reader.unread_notifications(runtime.scope)
    return AchievementNotificationCollection(
        family_id=family_id,
        visibility="FAMILY_PRIVATE",
        unread=tuple(
            AchievementNotificationResponse(
                notification_id=item.notification_id,
                achievement_id=item.achievement_id,
                title=item.title,
                message=item.message,
                status="UNREAD",
                created_at=item.created_at,
            )
            for item in unread
        ),
    )


@router.post(
    "/{family_id}/experience/notifications/{notification_id}/read",
    response_model=AchievementNotificationReadResponse,
)
async def mark_notification_read(
    family_id: str,
    notification_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    resolver: AchievementFeedbackRuntimeResolver | None = Depends(
        get_feedback_runtime_resolver
    ),
) -> AchievementNotificationReadResponse:
    """Mark a notification read in the scope-local read model.

    The state transition is naturally idempotent: retries converge to the same
    READ receipt.  The key is still required so mobile callers can correlate
    retries and satisfy the platform mutation contract.
    """

    if idempotency_key is None or not idempotency_key.strip() or len(idempotency_key) > 256:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="idempotency_key_required",
        )
    runtime = await _runtime(family_id, resolver)
    try:
        item = await runtime.reader.mark_notification_read(
            notification_id, runtime.scope
        )
    except ValueError as error:
        if str(error) == "ACHIEVEMENT_NOTIFICATION_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="achievement_notification_not_found",
            ) from error
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid_achievement_notification",
        ) from error
    except Exception as error:  # noqa: BLE001 - read-model boundary fails closed
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="experience_feedback_runtime_unavailable",
        ) from error
    if item.status != "READ" or item.read_at is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="experience_feedback_runtime_invalid",
        )
    return AchievementNotificationReadResponse(
        notification_id=item.notification_id,
        achievement_id=item.achievement_id,
        status="READ",
        read_at=item.read_at,
    )


@router.get(
    "/{family_id}/experience/analytics",
    response_model=ExperienceAnalyticsResponse,
)
async def get_analytics(
    family_id: str,
    resolver: AchievementFeedbackRuntimeResolver | None = Depends(
        get_feedback_runtime_resolver
    ),
) -> ExperienceAnalyticsResponse:
    runtime = await _runtime(family_id, resolver)
    metrics = await runtime.reader.analytics(runtime.scope)
    return ExperienceAnalyticsResponse(
        family_id=family_id,
        visibility="FAMILY_PRIVATE",
        metrics=tuple(
            ExperienceAnalyticsMetric(metric_key=key, value_count=value)
            for key, value in metrics
        ),
    )


def _achievement_response(achievement: Achievement) -> AchievementFeedbackResponse:
    return AchievementFeedbackResponse(
        achievement_id=achievement.achievement_id,
        key=achievement.key.value,
        occurrence_id=achievement.occurrence_id,
        title=achievement.title,
        message=achievement.message,
        evidence_refs=achievement.evidence_refs,
        earned_at=achievement.earned_at,
    )


__all__ = [
    "AchievementFeedbackCollection",
    "AchievementFeedbackResponse",
    "AchievementFeedbackRuntimeResolver",
    "AchievementNotificationCollection",
    "AchievementNotificationResponse",
    "AchievementNotificationReadResponse",
    "ExperienceAnalyticsMetric",
    "ExperienceAnalyticsResponse",
    "get_feedback_runtime_resolver",
    "list_achievements",
    "list_notifications",
    "mark_notification_read",
    "get_analytics",
    "router",
]
