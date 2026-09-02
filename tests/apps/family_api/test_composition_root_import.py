"""Composition-root acceptance tests for the clean 9f1ac40 snapshot.

These tests exercise the actual FastAPI application factory.  They do not
install synthetic Commerce, experience, FGCN, or legacy Journey adapters when
their reviewed dependencies are absent.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.apps.family_api import main

GROWTH_ONBOARDING_PATH = "/families/{family_id}/growth/onboardings"
FAMILY_ID = "00000000-0000-4000-8000-000000000011"


def test_composed_snapshot_imports_and_reports_dependency_status() -> None:
    app = main.create_app()

    assert app.state.composition_dependencies["commerce"] == {
        "available": False,
        "failure_mode": "fail_closed",
        "reason": "missing dependency: backend.domains.commerce",
    }
    assert app.state.composition_dependencies["experience"] == {
        "available": True,
        "failure_mode": "fail_closed",
        "reason": None,
    }
    assert app.state.composition_dependencies["fgcn"] == {
        "available": True,
        "failure_mode": "fail_closed",
        "reason": None,
    }
    assert app.state.composition_dependencies["journey_legacy"]["available"] is False

    paths = app.openapi()["paths"]
    assert GROWTH_ONBOARDING_PATH in paths
    assert "/families/{family_id}/experience/multimodal/drafts" in paths
    assert not any("commerce" in path for path in paths)
    readiness_operation = paths["/capabilities/{capability_name}/ready"]["get"]
    assert "503" in readiness_operation["responses"]


def test_production_growth_onboarding_remains_advertised_but_fails_closed(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    app = main.create_app()
    assert GROWTH_ONBOARDING_PATH in app.openapi()["paths"]

    with TestClient(app) as client:
        response = client.post(
            f"/families/{FAMILY_ID}/growth/onboardings",
            headers={
                "Authorization": "Bearer not-a-trusted-session",
                "Idempotency-Key": "composition-root-production-gap",
            },
            json={"intent_id": "intent-1"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "growth_onboarding_identity_not_configured"}


def test_capability_readiness_distinguishes_available_and_missing_dependencies() -> None:
    app = main.create_app()

    with TestClient(app) as client:
        for capability in ("commerce", "journey_legacy"):
            response = client.get(f"/capabilities/{capability}/ready")
            assert response.status_code == 503
            assert response.json() == {"detail": "capability_unavailable"}
        for capability in ("experience", "fgcn"):
            response = client.get(f"/capabilities/{capability}/ready")
            assert response.status_code == 200
            assert response.json() == {"status": "ready"}


def test_growth_onboarding_keeps_401_for_missing_bearer(monkeypatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    app = main.create_app()

    with TestClient(app) as client:
        response = client.post(
            f"/families/{FAMILY_ID}/growth/onboardings",
            headers={"Idempotency-Key": "composition-root-auth"},
            json={"intent_id": "intent-1"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "authorization_required"}
