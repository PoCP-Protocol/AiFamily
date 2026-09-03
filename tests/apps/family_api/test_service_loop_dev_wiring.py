"""The Batch 2 SERVICE booking loop, over real HTTP, end to end.

## Why this test exists

The six SERVICE endpoints were mounted but returned 500 to every caller: four of
their dependencies raise by design (`service/api/dependencies.py`), and nothing
supplied them outside unit tests. `main.py` said so explicitly — "Mounting buys
route registration and OpenAPI visibility, not availability."

`backend/apps/family_api/dev_wiring.py` supplies those four in a dev environment
via `app.dependency_overrides`, which is the mechanism `dependencies.py` itself
names as intended. This test is the evidence that the loop actually works —
without it, per R4, the capability does not exist no matter how many endpoints
are registered.

## What it asserts, and why each one matters

1. **The full chain returns 2xx** — provider → offering → slot → booking →
   confirm, then the customer projection shows the booking. A green unit test on
   each command would not have caught the 500s, because the 500 came from
   dependency resolution, which only happens over HTTP.
2. **The dev wiring did not fail open.** This is the part worth guarding: it
   would be easy to make the loop work by handing out a family scope to anyone.
   So: no token → 401, and a token for family A must not reach family B → 403.
3. **`human_only` still denies an AI actor on a gated action.** `confirm_booking_request`
   commits a named human being's time (R8). The dev wiring always issues a HUMAN
   actor, so this case is constructed deliberately by overriding the actor —
   otherwise the gate would be untested on a real route and we would only know it
   works in `PolicyEngine`'s own unit tests.
4. **The wiring refuses to install outside dev/test** (R5: synthetic data must not
   be reachable on a production route — `_DevConsentQuery` synthesises consent).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api.dev_wiring import (
    ENV_VAR,
    DevWiringNotPermittedError,
    install_dev_wiring,
    reset_dev_state,
)
from backend.apps.family_api.main import create_app
from backend.domains.service.api import dependencies as service_deps
from backend.intelligence.experience.api import get_multimodal_draft_runtime_resolver
from backend.intelligence.experience.standard_assets import (
    FAMILY_EXPERIENCE_PROMPT_VERSION,
    FAMILY_EXPERIENCE_SCHEMA_VERSION,
    family_experience_output_schema,
)
from backend.platform.identity.context import ActorContext, ActorType

FAMILY = "family-a"
OTHER_FAMILY = "family-zzz"
ACCOUNT = "parent-a"


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # `current_environment()` now fails closed when unset (see
    # test_environment_wiring_acceptance.py); this file must declare its
    # environment explicitly rather than rely on an implicit dev default.
    monkeypatch.setenv(ENV_VAR, "dev")


@pytest.fixture()
def client() -> TestClient:
    reset_dev_state()
    return TestClient(create_app())


@pytest.fixture()
def session(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/account-session",
        json={"external_ref": f"{ACCOUNT}:{FAMILY}"},
        headers={"idempotency-key": "session-1"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _headers(token: str, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "idempotency-key": key}


def test_service_booking_loop_is_callable_end_to_end(
    client: TestClient, session: dict[str, str]
) -> None:
    token = session["token"]
    family_id = session["family_id"]
    supply = f"/families/{family_id}/service"
    loop = f"/families/{family_id}/orchestration/test-loop/services"

    provider = client.post(
        f"{supply}/providers",
        headers=_headers(token, "provider-1"),
        json={
            "provider_ref": "prov-ref-1",
            "display_name": "Teacher Li",
            "provider_kind": "TEACHER",
            "qualification_status": "ACTIVE",
            "admission_status": "ADMITTED",
            "source_ref": "UI-19",
        },
    )
    assert provider.status_code == 200, provider.text

    offering = client.post(
        f"{supply}/offerings",
        headers=_headers(token, "offering-1"),
        json={
            "provider_id": provider.json()["provider_id"],
            "service_offering_ref": "off-ref-1",
            "title": "One communication experiment session",
            "admission_status": "ADMITTED",
            "source_ref": "UI-20",
        },
    )
    assert offering.status_code == 200, offering.text
    offering_id = offering.json()["service_offering_id"]

    slot = client.post(
        f"{supply}/availability-slots",
        headers=_headers(token, "slot-1"),
        json={
            "service_offering_id": offering_id,
            "availability_slot_ref": "slot-ref-1",
            "starts_at": "2026-09-01T10:00:00+00:00",
            "ends_at": "2026-09-01T11:00:00+00:00",
            "channel": "VIDEO",
        },
    )
    assert slot.status_code == 200, slot.text

    booking = client.post(
        f"{loop}/booking-requests",
        headers=_headers(token, "booking-1"),
        json={
            "service_offering_id": offering_id,
            "availability_slot_id": slot.json()["availability_slot_id"],
            "booking_ref": "bk-ref-1",
            "source_page_id": "UI-21",
            "subject_person_id": "child-a",
            "consent_ref": "consent-ref-1",
        },
    )
    assert booking.status_code == 200, booking.text
    booking_id = booking.json()["booking_request_id"]

    confirmed = client.post(
        f"{supply}/booking-requests/{booking_id}/confirm",
        headers=_headers(token, "confirm-1"),
    )
    assert confirmed.status_code == 200, confirmed.text

    # The projection is what UI-24 (my bookings) reads. A green write path that
    # the read path cannot see would still leave the screen empty.
    projection = client.get(f"{loop}/customer-projection", headers=_headers(token, "read-1"))
    assert projection.status_code == 200, projection.text
    booking_ids = [b["booking_request_id"] for b in projection.json()["bookings"]]
    assert booking_id in booking_ids


def test_dev_wiring_does_not_fail_open(client: TestClient, session: dict[str, str]) -> None:
    """The scope must come from the session, never from the URL."""
    token = session["token"]
    loop = f"/families/{session['family_id']}/orchestration/test-loop/services"

    assert client.get(f"{loop}/offerings").status_code == 401

    other = f"/families/{OTHER_FAMILY}/orchestration/test-loop/services/offerings"
    assert client.get(other, headers=_headers(token, "read-x")).status_code == 403

    bad_token = {"Authorization": "Bearer not-a-real-token"}
    assert client.get(f"{loop}/offerings", headers=bad_token).status_code == 401


def test_human_gated_action_still_denies_an_ai_actor(
    client: TestClient, session: dict[str, str]
) -> None:
    """R8: confirming a booking commits a real person's time — AI is denied.

    Constructed rather than incidental: the dev wiring always issues a HUMAN
    actor, so without overriding it this gate would never be exercised on a real
    route.
    """
    token = session["token"]
    family_id = session["family_id"]

    async def _ai_actor() -> ActorContext:
        return ActorContext(
            actor_id="ai:test-agent",
            actor_type=ActorType.AI,
            tenant_id=family_id,
            correlation_id="corr-ai",
        )

    client.app.dependency_overrides[service_deps.get_actor_context] = _ai_actor
    try:
        denied = client.post(
            f"/families/{family_id}/service/booking-requests/any-id/confirm",
            headers=_headers(token, "confirm-ai"),
        )
    finally:
        client.app.dependency_overrides[service_deps.get_actor_context] = None
        del client.app.dependency_overrides[service_deps.get_actor_context]

    # 403 from the policy engine, not 404 from the repository: the gate must
    # reject before the booking is ever looked up.
    assert denied.status_code == 403, denied.text


def test_dev_wiring_refuses_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """R5 — the synthetic consent path must be unreachable in production."""
    monkeypatch.setenv(ENV_VAR, "production")
    with pytest.raises(DevWiringNotPermittedError):
        install_dev_wiring(FastAPI())


def test_production_app_keeps_service_endpoints_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside dev, the four dependencies still raise — availability is not
    silently granted by the app factory."""
    monkeypatch.setenv(ENV_VAR, "production")
    app = create_app()
    assert service_deps.get_repository not in app.dependency_overrides
    assert service_deps.get_consent_query not in app.dependency_overrides
    assert service_deps.get_action_context not in app.dependency_overrides
    assert service_deps.get_actor_context not in app.dependency_overrides
    assert get_multimodal_draft_runtime_resolver not in app.dependency_overrides


def test_dev_wiring_installs_experience_resolver_from_authenticated_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic AI runtime uses the bearer identity, never a client scope."""

    monkeypatch.setenv(ENV_VAR, "test")
    reset_dev_state()
    app = create_app()
    assert get_multimodal_draft_runtime_resolver in app.dependency_overrides

    payload = {
        "run_id": "run-dev-wiring-001",
        "prompt_version": FAMILY_EXPERIENCE_PROMPT_VERSION,
        "schema_version": FAMILY_EXPERIENCE_SCHEMA_VERSION,
        "payload": {"media_ref": "fixture:image-001"},
        "output_schema": family_experience_output_schema(),
        "modalities": ["TEXT", "IMAGE"],
        "estimated_input_tokens": 128,
        "media_inputs": [
            {
                "media_type": "IMAGE",
                "uri": "media:fixture:dev-wiring-001",
                "mime_type": "image/jpeg",
                "sha256": "a" * 64,
            }
        ],
    }

    with TestClient(app) as client:
        session = client.post(
            "/auth/account-session",
            json={"external_ref": "guardian-dev:family-dev"},
            headers={"idempotency-key": "experience-session-1"},
        )
        assert session.status_code == 200, session.text
        token = session.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        draft = client.post(
            "/families/family-dev/experience/multimodal/drafts",
            headers=headers,
            json=payload,
        )
        assert draft.status_code == 200, draft.text
        result = draft.json()
        assert result["scope"]["tenant_id"] == "family-dev"
        assert result["scope"]["family_id"] == "family-dev"
        assert result["scope"]["subject_ids"] == [
            "guardian-dev",
            "dev-child:family-dev",
        ]
        assert result["status"] == "DRAFT"
        assert result["requires_human_confirmation"] is True

        cross_family = client.post(
            "/families/family-other/experience/multimodal/drafts",
            headers=headers,
            json=payload | {"run_id": "run-dev-wiring-cross-family"},
        )
        assert cross_family.status_code == 403, cross_family.text


def test_dev_experience_run_ledger_survives_create_decision_and_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The test runtime preserves a run across separately resolved requests."""

    monkeypatch.setenv(ENV_VAR, "test")
    reset_dev_state()
    app = create_app()
    payload = {
        "run_id": "run-dev-wiring-persistent-001",
        "prompt_version": FAMILY_EXPERIENCE_PROMPT_VERSION,
        "schema_version": FAMILY_EXPERIENCE_SCHEMA_VERSION,
        "payload": {"message": "请生成家庭成长草案"},
        "output_schema": family_experience_output_schema(),
        "modalities": ["TEXT"],
        "estimated_input_tokens": 64,
    }

    with TestClient(app) as client:
        session = client.post(
            "/auth/account-session",
            json={"external_ref": "guardian-persist:family-persist"},
            headers={"idempotency-key": "experience-session-persist"},
        )
        assert session.status_code == 200, session.text
        token = session.json()["token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        created = client.post(
            "/families/family-persist/experience/multimodal/drafts",
            headers=auth_headers | {"Idempotency-Key": "draft-persist-1"},
            json=payload,
        )
        assert created.status_code == 200, created.text

        decision = client.post(
            "/families/family-persist/experience/multimodal/runs/"
            "run-dev-wiring-persistent-001/decisions",
            headers=auth_headers | {"Idempotency-Key": "decision-persist-1"},
            json={"decision": "confirm"},
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["status"] == "recorded"

        replay = client.get(
            "/families/family-persist/experience/multimodal/runs/"
            "run-dev-wiring-persistent-001/replay",
            headers=auth_headers,
        )
        assert replay.status_code == 200, replay.text
        projection = replay.json()
        assert projection["run_id"] == "run-dev-wiring-persistent-001"
        assert projection["status"] == "DRAFT"
        assert projection["deletion_state"] == "active"
        assert projection["draft_payload"]["understanding"] == (
            "这是由生产同构测试链路生成的合成草案"
        )
        assert projection["entries"][-1]["interaction_type"] == "decision"
        assert projection["entries"][-1]["payload"]["decision"] == "accepted"

        replayed_decision = client.post(
            "/families/family-persist/experience/multimodal/runs/"
            "run-dev-wiring-persistent-001/decisions",
            headers=auth_headers | {"Idempotency-Key": "decision-persist-1"},
            json={"decision": "confirm"},
        )
        assert replayed_decision.status_code == 200, replayed_decision.text
        assert replayed_decision.json()["status"] == "replayed"
        assert replayed_decision.json()["idempotency_replayed"] is True
