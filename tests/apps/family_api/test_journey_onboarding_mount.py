from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.apps.family_api import main
from backend.apps.family_api.growth_onboarding_wiring import (
    InMemoryGrowthOnboardingActorResolver,
    build_fake_growth_onboarding_runtime,
)
from backend.domains.journey.api.growth_onboarding_routes import (
    GrowthOnboardingActorContext,
)
from backend.domains.journey.api.growth_onboarding_routes import (
    router as growth_onboarding_router,
)
from backend.domains.journey.domain.growth_onboarding import (
    CONFIRMED_INTENT_BOUNDARY,
    ConfirmedGrowthIntent,
    GrowthOnboardingScope,
)

PATH = "/families/{family_id}/growth/onboardings"
FAMILY_ID = "00000000-0000-4000-8000-000000000011"
TENANT_ID = "00000000-0000-4000-8000-000000000010"
ACTOR_ID = "00000000-0000-4000-8000-000000000012"
SUBJECT_ID = "00000000-0000-4000-8000-000000000013"
INTENT_ID = "00000000-0000-4000-8000-000000000001"


def _intent() -> ConfirmedGrowthIntent:
    return ConfirmedGrowthIntent(
        intent_id=INTENT_ID,
        tenant_id=TENANT_ID,
        family_id=FAMILY_ID,
        subject_person_id=SUBJECT_ID,
        need_type="COMMUNICATION_SUPPORT",
        goal_text="先完整听完，再确认彼此听到的内容。",
        required_capability_keys=("CAP_PARENT_CHILD_COMMUNICATION",),
        status="OPEN",
        confirmed_by=ACTOR_ID,
        confirmed_at=datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
        boundary=CONFIRMED_INTENT_BOUNDARY,
    )


def _dev_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    intent = _intent()
    runtime = build_fake_growth_onboarding_runtime([intent])
    scope = GrowthOnboardingScope(TENANT_ID, FAMILY_ID, ACTOR_ID)
    runtime.policy.allow(scope)
    runtime.consent.grant(
        scope,
        SUBJECT_ID,
        "GROWTH_TRACKING",
        granted_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    actor_resolver = InMemoryGrowthOnboardingActorResolver(
        {
            "parent-token": GrowthOnboardingActorContext(
                tenant_id=TENANT_ID,
                family_id=FAMILY_ID,
                actor_id=ACTOR_ID,
            )
        }
    )
    return (
        main.create_app(
            growth_onboarding_runtime=runtime,
            growth_onboarding_actor_resolver=actor_resolver,
        ),
        runtime,
    )


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer parent-token",
        "Idempotency-Key": key,
        "X-Correlation-Id": f"correlation:{key}",
    }


def _mounted_routes(app) -> list[APIRoute]:
    def walk(routes) -> list[APIRoute]:
        mounted: list[APIRoute] = []
        for route in routes:
            if isinstance(route, APIRoute):
                mounted.append(route)
            elif hasattr(route, "original_router"):
                mounted.extend(walk(route.original_router.routes))
        return mounted

    return [
        route
        for route in walk(app.routes)
        if route.path == PATH and "POST" in (route.methods or set())
    ]


def test_dev_mount_is_discoverable_callable_once_and_replays_without_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, runtime = _dev_app(monkeypatch)
    client = TestClient(app)

    assert PATH in app.openapi()["paths"]
    assert len(_mounted_routes(app)) == 1

    first = client.post(
        f"/families/{FAMILY_ID}/growth/onboardings",
        headers=_headers("mount-start"),
        json={"intent_id": INTENT_ID},
    )
    replay = client.post(
        f"/families/{FAMILY_ID}/growth/onboardings",
        headers=_headers("mount-start"),
        json={"intent_id": INTENT_ID},
    )

    assert first.status_code == 200, first.text
    assert runtime.transaction.audit_log[0]["correlation_id"] == "correlation:mount-start"
    assert runtime.transaction.outbox_events[0]["correlation_id"] == "correlation:mount-start"
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["event"] == first.json()["event"]
    assert len(runtime.repository.onboardings) == 1
    assert len(runtime.transaction.audit_log) == 1
    assert len(runtime.transaction.outbox_events) == 1


def test_dev_mount_preserves_auth_scope_and_idempotency_header_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _runtime = _dev_app(monkeypatch)
    client = TestClient(app)
    url = f"/families/{FAMILY_ID}/growth/onboardings"
    payload = {"intent_id": INTENT_ID}

    missing_auth = client.post(url, json=payload)
    missing_key = client.post(
        url,
        headers={"Authorization": "Bearer parent-token"},
        json=payload,
    )
    cross_family = client.post(
        "/families/00000000-0000-4000-8000-000000000099/growth/onboardings",
        headers=_headers("cross-family"),
        json=payload,
    )

    assert missing_auth.status_code == 401
    assert missing_auth.json() == {"detail": "authorization_required"}
    assert missing_key.status_code == 400
    assert missing_key.json() == {"detail": "invalid_idempotency_key"}
    assert cross_family.status_code == 403
    assert cross_family.json() == {"detail": "family_access_denied"}


def test_production_without_explicit_database_keeps_route_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = main.create_app()

    assert PATH in app.openapi()["paths"]
    assert len(_mounted_routes(app)) == 1

    response = TestClient(app).post(
        f"/families/{FAMILY_ID}/growth/onboardings",
        headers=_headers("production-unconfigured"),
        json={"intent_id": INTENT_ID},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "growth_onboarding_identity_not_configured"}


def test_production_postgres_uses_production_installer_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/aifamily")
    calls: list[str | None] = []

    def install_production(app, *, database_url: str | None = None) -> None:
        calls.append(database_url)
        app.include_router(growth_onboarding_router)

    monkeypatch.setattr(main, "install_growth_onboarding_production_wiring", install_production)

    app = main.create_app()

    assert calls == ["postgresql+asyncpg://example/aifamily"]
    assert len(_mounted_routes(app)) == 1


def test_dev_postgres_uses_durable_installer_before_dev_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/aifamily")
    calls: list[str | None] = []

    def install_production(app, *, database_url: str | None = None) -> None:
        calls.append(database_url)
        app.include_router(growth_onboarding_router)

    def fail_if_fake_installed(*_args, **_kwargs):
        raise AssertionError("explicit PostgreSQL must not select dev fake onboarding")

    monkeypatch.setattr(main, "install_growth_onboarding_production_wiring", install_production)
    monkeypatch.setattr(main, "install_growth_onboarding_dev_wiring", fail_if_fake_installed)

    app = main.create_app()

    assert calls == ["postgresql+asyncpg://example/aifamily"]
    assert len(_mounted_routes(app)) == 1


def test_dev_postgres_overrides_assessment_fake_with_durable_wiring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example/aifamily")
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(main, "get_engine", lambda _url: "postgres-engine")
    monkeypatch.setattr(main, "get_sessionmaker", lambda _url: "postgres-sessions")
    monkeypatch.setattr(
        main,
        "SqlAlchemyAssessmentIdentityResolver",
        lambda engine, session_factory: (engine, session_factory),
    )
    monkeypatch.setattr(
        main,
        "SqlAlchemyAssessmentIdentityResolver",
        lambda engine, session_factory: (engine, session_factory),
    )

    def install_durable_assessment(app, **kwargs) -> None:  # noqa: ANN001
        calls.append(kwargs)

    monkeypatch.setattr(main, "install_postgres_assessment_http_wiring", install_durable_assessment)

    main.create_app()

    assert len(calls) == 1
    assert calls[0]["engine"] == "postgres-engine"
    assert calls[0]["identity_resolver"] == ("postgres-engine", "postgres-sessions")
    assert calls[0]["interpretation_factory"].__name__ == "DeterministicInterpretationAdapter"
