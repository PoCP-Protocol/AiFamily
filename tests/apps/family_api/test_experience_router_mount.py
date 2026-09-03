"""Composition-root checks for the governed multimodal experience router.

The experience HTTP adapter already has its own contract tests.  These checks
cover the remaining application-factory boundary: the router must be visible
in OpenAPI and, until a trusted scope/context/gateway runtime is composed, the
same route must fail closed with a 503 rather than inventing a runtime.

At the time this test was introduced, ``main.py`` still had an uncommitted
router-mount WIP owned by another task.  The two mount-dependent assertions
therefore use non-strict ``xfail`` while the path is absent; once the two-line
composition-root patch lands, they automatically execute as ordinary checks.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.dev_wiring import ENV_VAR
from backend.apps.family_api.main import create_app

EXPERIENCE_PATH = "/families/{family_id}/experience/multimodal/drafts"
EXPERIENCE_URL = "/families/family-test/experience/multimodal/drafts"


def _valid_draft_payload() -> dict[str, object]:
    return {
        "run_id": "run-app-mount-001",
        "prompt_version": "prompt.v1",
        "schema_version": "schema.v1",
        "payload": {"message": "请帮我理解这张家庭照片"},
        "output_schema": {
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
        "modalities": ["TEXT", "IMAGE"],
        "estimated_input_tokens": 128,
        "media_inputs": [
            {
                "media_type": "IMAGE",
                "uri": "media:fixture:app-mount-001",
                "mime_type": "image/jpeg",
                "sha256": "a" * 64,
            }
        ],
    }


def _require_mount(app: object) -> None:
    """Record the known composition-root blocker without hiding other failures."""

    # ``FastAPI`` is intentionally accepted as object here to keep this helper
    # independent of a concrete app subclass used by future composition roots.
    paths = app.openapi()["paths"]  # type: ignore[attr-defined]
    if EXPERIENCE_PATH not in paths:
        pytest.xfail(
            "experience router is not mounted in family_api.main yet; "
            "pending the composition-root import/include_router patch"
        )


def test_experience_router_is_exposed_in_openapi() -> None:
    app = create_app()

    _require_mount(app)

    operation = app.openapi()["paths"][EXPERIENCE_PATH]["post"]
    assert "experience" in operation["tags"]
    assert (
        operation["operationId"]
        == "create_multimodal_draft_families__family_id__experience_multimodal_drafts_post"
    )


def test_unconfigured_experience_runtime_fails_closed_with_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Production composition deliberately has no synthetic dev overrides.  A
    # mounted route must still return the adapter's explicit 503 until trusted
    # identity/consent/context/gateway dependencies are supplied.
    monkeypatch.setenv(ENV_VAR, "production")
    app = create_app()

    _require_mount(app)

    response = TestClient(app).post(EXPERIENCE_URL, json=_valid_draft_payload())

    assert response.status_code == 503
    assert response.json()["detail"] == "multimodal_experience_runtime_not_configured"


def test_health_and_ready_remain_available() -> None:
    client = TestClient(create_app())

    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_create_app_rejects_ambiguous_experience_runtime_wiring() -> None:
    with pytest.raises(
        ValueError, match="experience_runtime_resolver and experience_runtime_wiring"
    ):
        create_app(
            experience_runtime_resolver=object(),  # type: ignore[arg-type]
            experience_runtime_wiring=lambda _application: None,
        )
