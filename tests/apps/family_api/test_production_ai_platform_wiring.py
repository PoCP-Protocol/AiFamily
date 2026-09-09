"""Contract tests for the single production AI composition root."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.apps.family_api.main import create_app
from backend.apps.family_api.production_ai_platform_wiring import ProductionAiPlatformWiring


def _wiring():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    return engine, ProductionAiPlatformWiring(
        engine=engine,
        session_factory=sessions,
        assessment_identity_resolver=lambda *_args: None,
        assessment_composition_resolver=lambda *_args: None,
        growth_plan_composition_resolver=lambda *_args: None,
        clock=lambda: datetime.now(UTC),
    )


def test_single_entry_point_mounts_the_complete_ai_surface() -> None:
    engine, wiring = _wiring()
    try:
        app = FastAPI()
        wiring.install(app)
        assert (
            "/families/{family_id}/growth/onboardings/{onboarding_id}/ai-plan-drafts"
            in app.openapi()["paths"]
        )
        assert (
            "/families/{family_id}/growth/human-tasks/{task_id}/decisions" in app.openapi()["paths"]
        )
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def test_create_app_rejects_mixed_ai_composition_hooks() -> None:
    engine, wiring = _wiring()
    try:
        with pytest.raises(ValueError, match="cannot be combined"):
            create_app(
                production_ai_platform_wiring=wiring,
                assessment_production_ai_wiring=lambda _app: None,
            )
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def test_platform_wiring_can_own_the_vertical_composition() -> None:
    engine, wiring = _wiring()
    try:
        assert wiring.vertical_family_growth_composition is None
        app = FastAPI()
        wiring.install(app)
        assert not hasattr(app.state, "vertical_family_growth_runtime")
    finally:
        import asyncio

        asyncio.run(engine.dispose())


def test_create_app_rejects_a_second_vertical_composition_root() -> None:
    engine, wiring = _wiring()
    try:
        with pytest.raises(ValueError, match="owns vertical family-growth"):
            create_app(
                production_ai_platform_wiring=wiring,
                production_vertical_family_growth_composition=object(),  # type: ignore[arg-type]
            )
    finally:
        import asyncio

        asyncio.run(engine.dispose())
