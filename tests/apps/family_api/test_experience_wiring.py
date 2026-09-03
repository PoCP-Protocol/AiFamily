from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api.experience_wiring import (
    install_experience_runtime_resolver,
    install_synthetic_experience_runtime,
    mount_experience_router,
)
from backend.intelligence.experience.api import get_multimodal_draft_runtime_resolver
from backend.intelligence.experience.standard_assets import (
    build_family_experience_assets,
    family_experience_output_schema,
)
from backend.intelligence.experience.synthetic_runtime import SyntheticRuntimeResolver

_ASSETS = build_family_experience_assets()


class _ExplicitResolver:
    async def resolve(self, family_id: str):
        raise AssertionError(f"resolver should not be called in wiring test: {family_id}")


def _payload(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "prompt_version": _ASSETS.prompt.version,
        "schema_version": _ASSETS.schema.version,
        "payload": {"media_ref": "fixture:image-001"},
        "output_schema": family_experience_output_schema(),
        "modalities": ["TEXT", "IMAGE"],
        "estimated_input_tokens": 128,
        "media_inputs": [
            {
                "media_type": "IMAGE",
                "uri": "media:fixture:wiring-001",
                "mime_type": "image/jpeg",
                "sha256": "a" * 64,
            }
        ],
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


def test_install_helper_accepts_only_explicit_non_synthetic_resolver() -> None:
    app = FastAPI()
    resolver = _ExplicitResolver()

    install_experience_runtime_resolver(app, resolver)

    assert app.dependency_overrides[get_multimodal_draft_runtime_resolver]() is resolver


def test_install_helper_rejects_synthetic_resolver() -> None:
    with pytest.raises(ValueError, match="synthetic experience resolver"):
        install_experience_runtime_resolver(
            FastAPI(),
            # The synthetic path has its own environment guard and must not be
            # smuggled into the generic composition-root hook.
            SyntheticRuntimeResolver(
                tenant_id="tenant-wiring",
                subject_ids=("child-wiring",),
            ),
        )


def test_create_app_keeps_explicit_resolver_after_environment_wiring(monkeypatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    from backend.apps.family_api.main import create_app

    resolver = _ExplicitResolver()
    app = create_app(experience_runtime_resolver=resolver)

    assert app.dependency_overrides[get_multimodal_draft_runtime_resolver]() is resolver
