from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.dev_wiring import ENV_VAR
from backend.apps.family_api.main import create_app

ENGAGEMENT_PATH = "/families/{family_id}/experience/engagement/drafts"
ENGAGEMENT_URL = "/families/family-api/experience/engagement/drafts"


def test_engagement_route_is_exposed_in_openapi() -> None:
    paths = create_app().openapi()["paths"]
    assert ENGAGEMENT_PATH in paths
    operation = paths[ENGAGEMENT_PATH]["post"]
    assert "experience" in operation["tags"]
    assert operation["operationId"] == (
        "create_engagement_draft_families__family_id__experience_engagement_drafts_post"
    )


def test_production_engagement_route_fails_closed_without_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "production")
    response = TestClient(create_app()).post(
        ENGAGEMENT_URL,
        json={"request_id": "request-1", "event_ids": ["event-1"]},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "engagement_runtime_not_configured"


def test_test_environment_keeps_engagement_route_callable_with_synthetic_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "test")
    client = TestClient(create_app())
    session = client.post(
        "/auth/account-session",
        json={"external_ref": "guardian-test:family-test"},
        headers={"Idempotency-Key": "engagement-session-1"},
    )
    assert session.status_code == 200
    token = session.json()["token"]

    response = client.post(
        "/families/family-test/experience/engagement/drafts",
        json={"request_id": "engagement-test-1", "event_ids": ["event-test-1"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "DRAFT"
    assert response.json()["scope"]["data_class"] == "SYNTHETIC"
    assert response.json()["requires_human_confirmation"] is True


def test_create_app_exposes_explicit_production_engagement_wiring_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "production")
    calls: list[object] = []

    def wiring(app: object) -> None:
        calls.append(app)

    app = create_app(engagement_runtime_wiring=wiring)

    assert calls == [app]


def test_create_app_rejects_conflicting_engagement_wiring_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "production")
    with pytest.raises(ValueError, match="mutually exclusive"):
        create_app(
            engagement_runtime_resolver=object(),  # type: ignore[arg-type]
            engagement_runtime_wiring=lambda _: None,
        )
