"""H-LIVE-01 read-only route acceptance and refusal tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.service.api import dependencies as deps
from backend.domains.service.api.live_routes import router as live_router
from backend.domains.service.application.context import ActionContext
from backend.domains.service.application.live_read_models import LiveSessionCandidate
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.identity.context import ActorContext, ActorType

from .helpers import FAMILY, GUARDIAN, TENANT

CORRELATION = "corr-live-001"
SESSION_REF = "expert-live-001"


class _Reader:
    def __init__(self, candidate: LiveSessionCandidate | None) -> None:
        self.candidate = candidate
        self.calls: list[tuple[str, str, str]] = []

    async def find_session(self, *, tenant_id, family_id, session_ref, as_of):
        self.calls.append((tenant_id, family_id, session_ref))
        if self.candidate is None:
            return None
        if (
            self.candidate.tenant_id != tenant_id
            or self.candidate.family_id != family_id
            or self.candidate.session_ref != session_ref
        ):
            return None
        return self.candidate


class _UnscopedReader(_Reader):
    async def find_session(self, *, tenant_id, family_id, session_ref, as_of):
        self.calls.append((tenant_id, family_id, session_ref))
        return self.candidate


def _candidate(**overrides: object) -> LiveSessionCandidate:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "tenant_id": TENANT,
        "family_id": FAMILY,
        "session_ref": SESSION_REF,
        "title": "家庭沟通中的倾听练习",
        "host_display_name": "李老师",
        "audience_scope": "适合 6–12 岁孩子家庭的家长",
        "starts_at": now + timedelta(hours=2),
        "ends_at": now + timedelta(hours=3),
        "approval_ref": "admission-001",
        "approval_version": "v1",
        "status": "SCHEDULED",
        "family_visibility": "FAMILY",
        "approved": True,
        "source": "TEST_FIXTURE",
        "fixture_only": True,
    }
    values.update(overrides)
    return LiveSessionCandidate(**values)


class _Wiring:
    def __init__(self, reader: _Reader) -> None:
        self.reader = reader
        self.recorder = AuditRecorder()
        self.actor_type = ActorType.HUMAN

    def context(self) -> ActionContext:
        return ActionContext(
            tenant_id=TENANT,
            family_id=FAMILY,
            actor_person_id=GUARDIAN,
            actor="guardian:live-test",
            correlation_id=CORRELATION,
            environment="TEST",
        )

    def actor(self) -> ActorContext:
        return ActorContext(
            actor_id=GUARDIAN if self.actor_type is ActorType.HUMAN else "ai:live-test",
            actor_type=self.actor_type,
            tenant_id=TENANT,
            correlation_id=CORRELATION,
        )


@contextmanager
def _client(wiring: _Wiring) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(live_router)

    async def reader():
        return wiring.reader

    async def context():
        return wiring.context()

    async def actor():
        return wiring.actor()

    app.dependency_overrides[deps.get_live_session_reader] = reader
    app.dependency_overrides[deps.get_action_context] = context
    app.dependency_overrides[deps.get_actor_context] = actor
    app.dependency_overrides[deps.get_audit_recorder] = lambda: wiring.recorder
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[tuple[TestClient, _Wiring]]:
    wiring = _Wiring(_Reader(_candidate()))
    with _client(wiring) as test_client:
        yield test_client, wiring


def test_approved_current_family_detail_is_read_only_and_audited(
    client: tuple[TestClient, _Wiring],
) -> None:
    test_client, wiring = client
    response = test_client.get(f"/families/{FAMILY}/live-sessions/{SESSION_REF}")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {
        "session_ref",
        "title",
        "host_display_name",
        "audience_scope",
        "starts_at",
        "ends_at",
        "approval_ref",
        "approval_version",
        "status",
        "family_visibility",
        "as_of",
        "source",
        "fixture_only",
    }
    assert payload["fixture_only"] is True
    assert payload["family_visibility"] == "FAMILY"
    assert payload["source"] == "TEST_FIXTURE"
    forbidden_fields = {
        "room_url",
        "playback_token",
        "child_profile",
        "ranking_score",
        "purchase_cta",
        "ai_conclusion",
    }
    assert not forbidden_fields & set(payload)

    events = wiring.recorder.all_events()
    assert len(events) == 1
    assert events[0].is_read
    assert events[0].action == "read_live_session"
    assert events[0].resource_id == SESSION_REF
    assert events[0].access_purpose == "LIVE_SESSION_DISCOVERY"
    assert set(events[0].accessed_fields) == set(payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {"approved": False},
        {"ends_at": datetime.now(UTC) - timedelta(minutes=1)},
        {"family_visibility": "TENANT"},
        {"status": "ENDED"},
        {"audience_scope": "   "},
        {"source": "BASELINE_CONTENT"},
        {"source": "TEST_FIXTURE", "fixture_only": False},
    ],
)
def test_non_admitted_detail_is_not_disclosed(
    overrides: dict[str, object],
) -> None:
    if overrides.get("audience_scope") == "   ":
        candidate = _candidate().model_copy(update=overrides)
    else:
        candidate = _candidate(**overrides)
    wiring = _Wiring(_Reader(candidate))
    with _client(wiring) as test_client:
        response = test_client.get(f"/families/{FAMILY}/live-sessions/{SESSION_REF}")
    assert response.status_code == 404, response.text


def test_cross_family_is_forbidden_before_reader_call() -> None:
    reader = _Reader(_candidate())
    wiring = _Wiring(reader)
    with _client(wiring) as test_client:
        response = test_client.get("/families/family-other/live-sessions/expert-live-001")
    assert response.status_code == 403
    assert reader.calls == []


def test_cross_tenant_candidate_is_not_disclosed() -> None:
    candidate = _candidate(tenant_id="tenant-other")
    reader = _UnscopedReader(candidate)
    wiring = _Wiring(reader)
    with _client(wiring) as test_client:
        response = test_client.get(f"/families/{FAMILY}/live-sessions/{SESSION_REF}")
    assert response.status_code == 404


def test_ai_actor_is_forbidden() -> None:
    wiring = _Wiring(_Reader(_candidate()))
    wiring.actor_type = ActorType.AI
    with _client(wiring) as test_client:
        response = test_client.get(f"/families/{FAMILY}/live-sessions/{SESSION_REF}")
    assert response.status_code == 403


def test_missing_provider_fails_closed() -> None:
    wiring = _Wiring(_Reader(_candidate()))
    app = FastAPI()
    app.include_router(live_router)

    async def context():
        return wiring.context()

    async def actor():
        return wiring.actor()

    app.dependency_overrides[deps.get_action_context] = context
    app.dependency_overrides[deps.get_actor_context] = actor
    app.dependency_overrides[deps.get_audit_recorder] = lambda: wiring.recorder
    with TestClient(app) as test_client:
        response = test_client.get(f"/families/{FAMILY}/live-sessions/{SESSION_REF}")
    assert response.status_code == 503
    assert wiring.recorder.all_events() == ()


def test_missing_auth_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "development")
    from backend.apps.family_api.dev_wiring import reset_dev_state
    from backend.apps.family_api.main import create_app

    reset_dev_state()
    with TestClient(create_app()) as test_client:
        response = test_client.get(f"/families/{FAMILY}/live-sessions/{SESSION_REF}")
    assert response.status_code == 401


def test_route_is_get_only_and_has_stable_openapi_shape() -> None:
    app = FastAPI()
    app.include_router(live_router)
    path = "/families/{family_id}/live-sessions/{session_ref}"
    operations = app.openapi()["paths"][path]
    assert set(operations) == {"get"}
    response_schema = operations["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("#/components/schemas/ApprovedLiveSessionDetail")
