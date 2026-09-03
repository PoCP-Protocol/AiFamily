from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.apps.family_api.production_ai_growth_surface_wiring import (
    install_production_ai_growth_surface,
)


def test_composite_surface_mounts_ui05_ui09_and_feedback_routes_together() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()

    async def composition_resolver(_identity, _scope):
        raise AssertionError("route installation must not resolve a model runtime")

    install_production_ai_growth_surface(
        app,
        engine=engine,
        session_factory=session_factory,
        growth_plan_composition_resolver=composition_resolver,
        clock=lambda: datetime.now(UTC),
    )

    methods_by_path = {
        path: frozenset(method.upper() for method in methods)
        for path, methods in app.openapi()["paths"].items()
    }
    assert methods_by_path[
        "/families/{family_id}/growth/onboardings/{onboarding_id}/ai-plan-drafts"
    ] == {"POST"}
    assert methods_by_path[
        "/families/{family_id}/growth/ai-plan-drafts/{draft_id}/review"
    ] == {"POST"}
    assert methods_by_path[
        "/families/{family_id}/growth/human-tasks/{task_id}/decisions"
    ] == {"POST"}
    assert methods_by_path["/families/{family_id}/today"] == {"GET"}
    assert methods_by_path[
        "/families/{family_id}/tasks/{task_id}/check-in"
    ] == {"POST"}
    assert methods_by_path[
        "/families/{family_id}/experience/achievements/{achievement_id}/feedback"
    ] == {"POST"}


def test_composite_surface_rejects_partial_or_synthetic_composition() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    with pytest.raises(TypeError, match="composition and clock"):
        install_production_ai_growth_surface(
            FastAPI(),
            engine=engine,
            session_factory=session_factory,
            growth_plan_composition_resolver=None,  # type: ignore[arg-type]
            clock=lambda: datetime.now(UTC),
        )
