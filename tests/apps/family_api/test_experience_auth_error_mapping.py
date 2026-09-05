"""P0 HTTP semantics for the trusted experience scope boundary.

These tests deliberately use a resolver that returns only a governed scope
error.  They do not install a synthetic runtime or provider, so they remain an
independent acceptance contract while production wiring is being completed.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api.trusted_experience_scope import ExperienceScopeError
from backend.intelligence.experience.api import (
    get_multimodal_draft_runtime_resolver,
    router,
)


@dataclass(frozen=True)
class _FailingScopeResolver:
    reason: str

    async def resolve(self, _family_id: str) -> None:
        raise ExperienceScopeError(self.reason)


def _client(reason: str) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime_resolver] = lambda: _FailingScopeResolver(
        reason
    )
    return TestClient(app)


def _body() -> dict[str, object]:
    return {
        "run_id": "run-auth-boundary",
        "prompt_version": "experience.v1",
        "schema_version": "experience.v1",
        "payload": {"expression": "我们想先被理解。"},
        "output_schema": {"type": "object", "properties": {"next_step": {"type": "string"}}},
        "modalities": ["TEXT"],
        "estimated_input_tokens": 8,
    }


@pytest.mark.parametrize(
    ("reason", "status_code", "detail"),
    (
        ("AUTHENTICATED_PRINCIPAL_UNAVAILABLE", 401, "authentication_required"),
        ("TENANT_SCOPE_UNAVAILABLE", 403, "family_access_denied"),
        ("CONSENT_REQUIRED", 403, "CONSENT_REQUIRED"),
    ),
)
def test_scope_boundary_maps_auth_tenant_and_consent_errors(
    reason: str,
    status_code: int,
    detail: str,
) -> None:
    response = _client(reason).post(
        "/families/family-a/experience/multimodal/drafts",
        json=_body(),
        headers={"Idempotency-Key": "auth-boundary-1"},
    )

    assert response.status_code == status_code, response.text
    assert response.json()["detail"] == detail
    if status_code == 401:
        assert response.headers["www-authenticate"] == "Bearer"
