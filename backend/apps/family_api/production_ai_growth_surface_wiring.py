"""One production-equivalent HTTP surface for the UI-05 → UI-09 AI loop."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.apps.family_api.growth_plan_ai_api import CompositionResolver
from backend.apps.family_api.production_achievement_feedback_write_wiring import (
    install_production_achievement_feedback_write_wiring,
)
from backend.apps.family_api.production_daily_action_http_wiring import (
    install_production_daily_action_http_wiring,
)
from backend.apps.family_api.production_growth_plan_http_wiring import (
    install_production_growth_plan_http_wiring,
)


def install_production_ai_growth_surface(
    app: FastAPI,
    *,
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    growth_plan_composition_resolver: CompositionResolver,
    clock: Callable[[], datetime],
) -> None:
    """Mount the complete family-facing AI growth loop with shared authorities."""

    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI instance")
    if not isinstance(engine, AsyncEngine):
        raise TypeError("engine must be an AsyncEngine")
    if not isinstance(session_factory, async_sessionmaker):
        raise TypeError("session_factory must be an async_sessionmaker")
    if not callable(growth_plan_composition_resolver) or not callable(clock):
        raise TypeError("AI growth surface composition and clock are required")

    install_production_growth_plan_http_wiring(
        app,
        engine=engine,
        session_factory=session_factory,
        composition_resolver=growth_plan_composition_resolver,
        clock=clock,
    )
    install_production_daily_action_http_wiring(
        app,
        engine=engine,
        session_factory=session_factory,
    )
    install_production_achievement_feedback_write_wiring(
        app,
        engine=engine,
        session_factory=session_factory,
    )


__all__ = ["install_production_ai_growth_surface"]
