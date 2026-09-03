"""Read-only application boundary for achievement feedback projections."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.experience.achievement import Achievement
from backend.intelligence.experience.achievement_persistence import (
    SqlAlchemyAchievementProjection,
)
from backend.intelligence.experience.contracts import DeletionRef, ExperienceScope
from backend.intelligence.experience.projections import (
    SqlAlchemyAchievementNotificationProjection,
    SqlAlchemyExperienceAnalyticsProjection,
    StoredAchievementNotification,
)
from backend.intelligence.model_gateway.contracts import DataClass


class ExperienceFeedbackReader(Protocol):
    async def achievements(self, scope: ExperienceScope) -> tuple[Achievement, ...]: ...

    async def unread_notifications(
        self, scope: ExperienceScope
    ) -> tuple[StoredAchievementNotification, ...]: ...

    async def mark_notification_read(
        self, notification_id: str, scope: ExperienceScope
    ) -> StoredAchievementNotification: ...

    async def analytics(self, scope: ExperienceScope) -> tuple[tuple[str, int], ...]: ...


ScopeResolver = Callable[
    [str], ExperienceScope | ContextScope | Awaitable[ExperienceScope | ContextScope]
]


@dataclass(frozen=True, slots=True)
class FeedbackReadRuntime:
    scope: ExperienceScope
    reader: ExperienceFeedbackReader


class SqlAlchemyExperienceFeedbackReader:
    """Session-per-call reader for production and integration environments."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def achievements(self, scope: ExperienceScope) -> tuple[Achievement, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyAchievementProjection(session).earned(scope)

    async def unread_notifications(
        self, scope: ExperienceScope
    ) -> tuple[StoredAchievementNotification, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyAchievementNotificationProjection(session).unread(scope)

    async def mark_notification_read(
        self, notification_id: str, scope: ExperienceScope
    ) -> StoredAchievementNotification:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyAchievementNotificationProjection(session).mark_read(
                notification_id, scope
            )

    async def analytics(self, scope: ExperienceScope) -> tuple[tuple[str, int], ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyExperienceAnalyticsProjection(session).counts(scope)


@dataclass(frozen=True, slots=True)
class ProductionFeedbackReadRuntimeResolver:
    """Resolve authenticated scope before opening a read-model session."""

    scope_resolver: ScopeResolver
    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not callable(self.scope_resolver):
            raise TypeError("scope_resolver must be callable")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")

    async def resolve(self, family_id: str) -> FeedbackReadRuntime:
        resolved = self.scope_resolver(family_id)
        scope = await resolved if inspect.isawaitable(resolved) else resolved
        if isinstance(scope, ContextScope):
            scope = _experience_scope(scope)
        if not isinstance(scope, ExperienceScope):
            raise TypeError("scope_resolver must return ExperienceScope or ContextScope")
        if scope.family_id != family_id:
            raise PermissionError("resolved scope does not match requested family")
        _assert_active(scope)
        return FeedbackReadRuntime(
            scope=scope,
            reader=SqlAlchemyExperienceFeedbackReader(self.session_factory),
        )


@dataclass(frozen=True, slots=True)
class SharedExperienceFeedbackRuntimeResolver:
    """Derive feedback access from the already-composed Draft runtime.

    Deployments can pass the exact same ``ProductionExperienceRuntimeResolver``
    used by multimodal Draft endpoints.  Identity, consent, deletion and family
    binding are therefore evaluated once by one authority instead of being
    reimplemented for feedback reads.
    """

    experience_runtime_resolver: object
    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not callable(getattr(self.experience_runtime_resolver, "resolve", None)):
            raise TypeError("experience_runtime_resolver must implement resolve(family_id)")
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")

    async def resolve(self, family_id: str) -> FeedbackReadRuntime:
        runtime = self.experience_runtime_resolver
        resolved = runtime.resolve(family_id)
        draft_runtime = await resolved if inspect.isawaitable(resolved) else resolved
        scope = getattr(draft_runtime, "scope", None)
        if isinstance(scope, ContextScope):
            scope = _experience_scope(scope)
        if not isinstance(scope, ExperienceScope):
            raise TypeError("shared experience runtime must expose a valid scope")
        _assert_active(scope)
        if scope.family_id != family_id:
            raise PermissionError("resolved scope does not match requested family")
        return FeedbackReadRuntime(
            scope=scope,
            reader=SqlAlchemyExperienceFeedbackReader(self.session_factory),
        )


def _experience_scope(scope: ContextScope) -> ExperienceScope:
    """Adapt the shared authenticated ContextScope to the experience contract."""

    return ExperienceScope(
        global_id=f"context:{scope.tenant_id}:{scope.family_id}",
        tenant_id=scope.tenant_id,
        region_id=scope.region_id,
        family_id=scope.family_id,
        subject_ids=scope.subject_ids,
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        consent_granted=scope.consent_granted,
        data_class=DataClass(scope.data_class.value),
        locale=scope.locale,
        content_locale=scope.effective_content_locale,
        model_locale=scope.effective_model_locale,
        policy_locale=scope.effective_policy_locale,
        deletion_ref=DeletionRef(scope.deletion_ref, "experience.v1"),
        correlation_id=scope.correlation_id,
        causation_id=scope.causation_id,
    )


def _assert_active(scope: ExperienceScope) -> None:
    if not scope.consent_granted:
        raise PermissionError("consent is not active")


__all__ = [
    "ExperienceFeedbackReader",
    "FeedbackReadRuntime",
    "ProductionFeedbackReadRuntimeResolver",
    "SharedExperienceFeedbackRuntimeResolver",
    "SqlAlchemyExperienceFeedbackReader",
]
