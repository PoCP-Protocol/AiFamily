"""Exclusive H-LIVE-01 tests: approved detail read and fail-closed negatives."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.domains.service.api import dependencies as service_dependencies
from backend.domains.service.api import live_routes
from backend.domains.service.application.context import ActionContext
from backend.domains.service.application.live_ports import (
    LiveProjectionConflictError,
)
from backend.domains.service.application.live_read_models import LiveSessionProjection
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.identity.context import ActorContext, ActorType, TenantStatus
from backend.platform.identity.directory import InMemoryTenantDirectory

FAMILY = "family-a"
OTHER_FAMILY = "family-b"
TENANT = "tenant-a"
NOW = datetime.now(UTC).replace(microsecond=0)


class Projection:
    def __init__(self, value: LiveSessionProjection | None = None, error: Exception | None = None):
        self.value = value
        self.error = error
        self.calls: list[dict[str, str]] = []

    async def get_session_projection(
        self, *, tenant_id: str, family_id: str, session_ref: str
    ) -> LiveSessionProjection | None:
        self.calls.append(
            {"tenant_id": tenant_id, "family_id": family_id, "session_ref": session_ref}
        )
        if self.error:
            raise self.error
        return self.value


class MalformedProjection:
    async def get_session_projection(
        self, *, tenant_id: str, family_id: str, session_ref: str
    ) -> dict[str, str]:
        return {"session_ref": session_ref}


def _context(*, family_id: str = FAMILY, tenant_id: str = TENANT) -> ActionContext:
    return ActionContext(
        tenant_id=tenant_id,
        family_id=family_id,
        actor_person_id="guardian-1",
        actor="guardian:1",
        correlation_id="corr-live-1",
        environment="TEST",
    )


def _actor(*, tenant_id: str = TENANT, actor_type: ActorType = ActorType.HUMAN) -> ActorContext:
    return ActorContext(
        actor_id="guardian-1",
        actor_type=actor_type,
        tenant_id=tenant_id,
        correlation_id="corr-live-1",
    )


def _projection(**overrides: object) -> LiveSessionProjection:
    values: dict[str, object] = {
        "tenant_id": TENANT,
        "family_id": FAMILY,
        "session_ref": "live-001",
        "title": "亲子沟通小课",
        "presenter_name": "咪莉老师",
        "audience_scope": ("ADULT_GUARDIAN",),
        "starts_at": NOW + timedelta(hours=1),
        "ends_at": NOW + timedelta(hours=2),
        "review_ref": "review-001",
        "review_version": "v3",
        "review_status": "APPROVED",
        "status": "SCHEDULED",
        "family_visibility": "FAMILY_SCOPED",
        "as_of": NOW,
        "source": "CANONICAL_LIVE_PROJECTION",
        "fixture_only": False,
    }
    values.update(overrides)
    return LiveSessionProjection.model_validate(values)


@pytest.fixture
def wiring() -> dict[str, object]:
    projection = Projection(_projection())
    recorder = AuditRecorder()
    return {"projection": projection, "recorder": recorder}


@pytest.fixture
def client(wiring: dict[str, object]) -> TestClient:
    app = FastAPI()
    app.include_router(live_routes.router)
    projection = wiring["projection"]
    recorder = wiring["recorder"]
    assert isinstance(projection, Projection)
    assert isinstance(recorder, AuditRecorder)
    app.dependency_overrides[service_dependencies.get_live_projection] = lambda: projection
    app.dependency_overrides[service_dependencies.get_action_context] = lambda: _context()
    app.dependency_overrides[service_dependencies.get_actor_context] = lambda: _actor()
    app.dependency_overrides[service_dependencies.get_tenant_directory] = lambda: (
        InMemoryTenantDirectory({TENANT: TenantStatus.ACTIVE})
    )
    app.dependency_overrides[service_dependencies.get_audit_recorder] = lambda: recorder
    return TestClient(app)


def test_approved_unexpired_family_scoped_detail_is_readable_and_audited(
    client: TestClient, wiring: dict[str, object]
) -> None:
    response = client.get(f"/families/{FAMILY}/live-sessions/live-001")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["presenter_name"] == "咪莉老师"
    assert body["family_visibility"] == "FAMILY_SCOPED"
    assert body["review_version"] == "v3"
    assert "room_url" not in body
    assert "playback_token" not in body
    assert "ranking_score" not in body
    assert "purchase_cta" not in body
    assert "ai_conclusion" not in body
    recorder = wiring["recorder"]
    assert isinstance(recorder, AuditRecorder)
    events = recorder.all_events()
    assert len(events) == 1
    assert events[0].is_read
    assert events[0].access_purpose == "LIVE_DISCOVERY"


@pytest.mark.parametrize(
    ("override", "detail"),
    [
        ({"review_status": "WITHDRAWN"}, "live_session_not_approved"),
        ({"ends_at": NOW - timedelta(minutes=1)}, "live_session_expired"),
        ({"audience_scope": ()}, "live_session_audience_scope_missing"),
        ({"family_visibility": "FAMILY_SCOPED"}, "live_session_not_found"),
    ],
)
def test_ineligible_projection_is_not_exposed(
    client: TestClient,
    wiring: dict[str, object],
    override: dict[str, object],
    detail: str,
) -> None:
    projection = wiring["projection"]
    assert isinstance(projection, Projection)
    if detail == "live_session_not_found":
        projection.value = None
    else:
        values = {**_projection().model_dump(), **override}
        if detail == "live_session_expired":
            values["starts_at"] = NOW - timedelta(hours=2)
        projection.value = LiveSessionProjection.model_validate(values)

    response = client.get(f"/families/{FAMILY}/live-sessions/live-001")

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == detail


def test_cross_family_url_is_forbidden(client: TestClient) -> None:
    response = client.get(f"/families/{OTHER_FAMILY}/live-sessions/live-001")
    assert response.status_code == 403


def test_cross_tenant_actor_is_forbidden(client: TestClient) -> None:
    app = client.app
    app.dependency_overrides[service_dependencies.get_actor_context] = lambda: _actor(
        tenant_id="tenant-b"
    )
    response = client.get(f"/families/{FAMILY}/live-sessions/live-001")
    assert response.status_code == 403


def test_missing_authentication_is_401_when_auth_resolver_rejects(client: TestClient) -> None:
    async def reject_auth() -> ActionContext:
        raise HTTPException(status_code=401, detail="authentication_required")

    client.app.dependency_overrides[service_dependencies.get_action_context] = reject_auth
    response = client.get(f"/families/{FAMILY}/live-sessions/live-001")
    assert response.status_code == 401


def test_unconfigured_provider_is_503_fail_closed() -> None:
    app = FastAPI()
    app.include_router(live_routes.router)
    app.dependency_overrides[service_dependencies.get_action_context] = lambda: _context()
    app.dependency_overrides[service_dependencies.get_actor_context] = lambda: _actor()
    app.dependency_overrides[service_dependencies.get_audit_recorder] = AuditRecorder
    response = TestClient(app).get(f"/families/{FAMILY}/live-sessions/live-001")
    assert response.status_code == 503
    assert response.json()["detail"] == "live_projection_not_configured"


def test_provider_conflict_is_409(client: TestClient, wiring: dict[str, object]) -> None:
    projection = wiring["projection"]
    assert isinstance(projection, Projection)
    projection.error = LiveProjectionConflictError("live_projection_conflict")
    response = client.get(f"/families/{FAMILY}/live-sessions/live-001")
    assert response.status_code == 409
    assert response.json()["detail"] == "live_projection_conflict"


def test_provider_shape_failure_is_503_fail_closed(client: TestClient) -> None:
    client.app.dependency_overrides[service_dependencies.get_live_projection] = MalformedProjection
    response = client.get(f"/families/{FAMILY}/live-sessions/live-001")
    assert response.status_code == 503
    assert response.json()["detail"] == "live_projection_shape_invalid"


def test_fixture_must_be_explicitly_marked() -> None:
    with pytest.raises(ValueError, match="test_fixture_must_be_explicitly_marked"):
        _projection(source="TEST_FIXTURE", fixture_only=False)


def test_baseline_content_is_rejected() -> None:
    with pytest.raises(ValueError, match="baseline_content_is_not_a_live_source"):
        _projection(source="BASELINE_CONTENT")
