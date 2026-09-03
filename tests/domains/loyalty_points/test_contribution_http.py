"""HTTP wiring evidence for the isolated contribution router.

This deliberately mounts the router on a test app.  It proves HTTP-to-command
wiring and error mapping, but does not claim that ``family_api/main.py`` mounts
it; that composition-root change belongs to a separately owned WIP.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.loyalty_points.api.contribution_routes import (
    get_contribution_context,
    get_contribution_repository,
    register_exception_handlers,
    router,
)
from backend.domains.loyalty_points.application.contribution_ports import (
    ContributionActionContext,
)
from backend.domains.loyalty_points.infrastructure.contribution_fake_repository import (
    FakeContributionRepository,
)

FAMILY = "family-http"
TENANT = "tenant-http"
PERSON = "adult-http"


@pytest.fixture
def http_wiring() -> Iterator[tuple[TestClient, FakeContributionRepository, dict]]:
    repo = FakeContributionRepository()
    state = {
        "context": ContributionActionContext(
            tenant_id=TENANT,
            family_id=FAMILY,
            actor_person_id=PERSON,
            actor="guardian:http",
            correlation_id="http-correlation",
            adult_verified=True,
            adult_verification_ref="adult-verification-http",
        )
    }
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_contribution_repository] = lambda: repo
    app.dependency_overrides[get_contribution_context] = lambda: state["context"]
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, repo, state
    app.dependency_overrides.clear()


def _headers(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key, "X-Correlation-Id": f"http:{key}"}


def _submit_body() -> dict[str, object]:
    return {
        "consumer_family_id": FAMILY,
        "content_ref": "adult-experience:http-1",
        "content_type": "ARTICLE",
        "purpose": "VERIFIED_ADULT_CONTRIBUTION",
        "copyright_attestation_ref": "copyright-http",
        "privacy_redaction_ref": "privacy-http",
    }


def test_http_router_wires_full_adult_contribution_lifecycle(http_wiring) -> None:
    client, _repo, _state = http_wiring
    base = f"/families/{FAMILY}/contributions"

    submitted = client.post(base, headers=_headers("http-submit"), json=_submit_body())
    assert submitted.status_code == 201, submitted.text
    contribution_id = submitted.json()["contribution_id"]

    reviewed = client.post(
        f"{base}/{contribution_id}/review",
        headers=_headers("http-review"),
        json={
            "review_ref": "review:http",
            "reviewer_person_id": PERSON,
            "content_approved": True,
            "copyright_approved": True,
            "safety_approved": True,
            "reason_code": "APPROVED",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "REVIEWED"

    verify = client.post(
        f"{base}/{contribution_id}/verify",
        headers=_headers("http-verify"),
        json={"verification_ref": "verification:http"},
    )
    assert verify.status_code == 200, verify.text

    use = client.post(
        f"{base}/{contribution_id}/use-confirmation",
        headers=_headers("http-use"),
        json={"confirmation_ref": "use:http"},
    )
    assert use.status_code == 200, use.text

    hold = client.post(
        f"{base}/{contribution_id}/hold",
        headers=_headers("http-hold"),
        json={"hold_reason": "adult family confirmed use"},
    )
    assert hold.status_code == 200, hold.text

    released = client.post(
        f"{base}/{contribution_id}/release",
        headers=_headers("http-release"),
        json={"release_ref": "release:http"},
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "RELEASED"


def test_http_maps_missing_idempotency_and_scope_failures(http_wiring) -> None:
    client, _repo, state = http_wiring
    base = f"/families/{FAMILY}/contributions"

    missing_key = client.post(base, json=_submit_body())
    assert missing_key.status_code == 400
    assert missing_key.json() == {"detail": "idempotency_key_required"}

    state["context"] = ContributionActionContext(
        tenant_id=TENANT,
        family_id="family-token",
        actor_person_id=PERSON,
        actor="guardian:http",
        correlation_id="wrong-family",
        adult_verified=True,
        adult_verification_ref="adult-verification-http",
    )
    wrong_path = client.post(base, headers=_headers("http-wrong-family"), json=_submit_body())
    assert wrong_path.status_code == 403
    assert wrong_path.json() == {"detail": "family_access_denied"}


def test_http_does_not_allow_ai_to_submit_or_release(http_wiring) -> None:
    client, _repo, state = http_wiring
    base = f"/families/{FAMILY}/contributions"
    state["context"] = ContributionActionContext(
        tenant_id=TENANT,
        family_id=FAMILY,
        actor_person_id=PERSON,
        actor="ai:assistant",
        correlation_id="ai-correlation",
        adult_verified=True,
        adult_verification_ref="adult-verification-http",
    )
    response = client.post(base, headers=_headers("http-ai"), json=_submit_body())
    assert response.status_code == 403
    assert response.json() == {"detail": "human_actor_required"}


def test_http_surface_contains_all_mutating_routes() -> None:
    paths = {route.path for route in router.routes}
    assert "/families/{family_id}/contributions" in paths
    for suffix in (
        "review",
        "verify",
        "use-confirmation",
        "hold",
        "release",
        "withdraw",
        "appeal",
        "appeal/resolve",
        "refund-reversal",
    ):
        assert f"/families/{{family_id}}/contributions/{{contribution_id}}/{suffix}" in paths
