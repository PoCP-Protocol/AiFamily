from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api.experience_wiring import (
    install_synthetic_experience_runtime,
    mount_experience_router,
)


def _payload(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "prompt_version": "prompt.v1",
        "schema_version": "schema.v1",
        "payload": {"media_ref": "fixture:image-001"},
        "output_schema": {
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
        "modalities": ["TEXT", "IMAGE"],
        "estimated_input_tokens": 128,
    }


def test_mount_helper_exposes_experience_route_and_test_runtime() -> None:
    app = FastAPI()
    mount_experience_router(app)
    install_synthetic_experience_runtime(
        app,
        tenant_id="tenant-wiring",
        subject_ids=("guardian-wiring", "child-wiring"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/families/family-wiring/experience/multimodal/drafts",
            json=_payload("run-wiring-001"),
        )

    assert response.status_code == 200
    assert response.json()["scope"]["family_id"] == "family-wiring"
    assert response.json()["status"] == "DRAFT"
    assert response.json()["requires_human_confirmation"] is True
    assert "/families/{family_id}/experience/multimodal/drafts" in app.openapi()["paths"]


def test_mount_helper_rejects_non_test_synthetic_wiring() -> None:
    with pytest.raises(ValueError, match="only supports the test environment"):
        install_synthetic_experience_runtime(
            FastAPI(),
            tenant_id="tenant-wiring",
            subject_ids=("child-wiring",),
            environment="production",
        )
