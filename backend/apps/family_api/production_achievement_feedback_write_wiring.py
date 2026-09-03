"""Production-equivalent wiring for append-only achievement feedback."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.apps.family_api.production_daily_action_http_wiring import (
    SqlAlchemyCurrentActionSubjectResolver,
    SqlAlchemyDailyActionIdentityResolver,
    SqlAlchemyDailyActionScopeResolver,
)
from backend.intelligence.experience.feedback_write import (
    SqlAlchemyAchievementFeedbackApplication,
)
from backend.intelligence.experience.feedback_write_api import (
    AchievementFeedbackHttpDependencies,
    build_achievement_feedback_write_router,
)


def install_production_achievement_feedback_write_wiring(
    app: FastAPI,
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Use the UI-09 Guardian/subject/Consent authority in every environment."""

    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI instance")
    if not isinstance(engine, AsyncEngine):
        raise TypeError("engine must be an AsyncEngine")
    if not isinstance(session_factory, async_sessionmaker):
        raise TypeError("session_factory must be an async_sessionmaker")
    app.include_router(
        build_achievement_feedback_write_router(
            AchievementFeedbackHttpDependencies(
                application=SqlAlchemyAchievementFeedbackApplication(session_factory),
                identity_resolver=SqlAlchemyDailyActionIdentityResolver(
                    engine,
                    session_factory,
                ),
                subject_resolver=SqlAlchemyCurrentActionSubjectResolver(session_factory),
                scope_resolver=SqlAlchemyDailyActionScopeResolver(
                    engine,
                    session_factory,
                ),
            )
        )
    )


__all__ = ["install_production_achievement_feedback_write_wiring"]
