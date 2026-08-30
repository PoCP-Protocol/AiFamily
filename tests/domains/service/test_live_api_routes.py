"""H-LIVE-01 read-files contract tests.

The source adapter is a test double here; it is not production evidence.  The
tests prove the same HTTP shape, scope gates, approval/expiry gates and read-audit
semantics that a real adapter must satisfy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.service.api import dependencies as deps
from backend.domains.service.api.live_routes import router
from backend.domains.service.application.context import ActionContext
from backend.domains.service.application.live_read_models import LiveSessionCandidate
from backend.platform.audit.models import AuditActionKind
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.identity.context import ActorContext, ActorType, TenantStatus
from backend.platform.identity.directory import InMemoryTenantDirectory

TENANT = "tenant-h01"
FAMILY = "family-h01"
GUARDIAN = "person-guardian-h01"
SESSION = "session-h01-001"


def _ctx(*, family_id: str = FAMILY, actor_person_id: str = GUARDIAN) -> ActionContext:
    return ActionContext(
        tenant_id=TENANT,
        family_id=family_id,
        actor_person_id=actor_person_id,
        actor="guardian:h01",
        correlation_id="corr-h01-001",
        environment="TEST",
    )


def _actor(*, tenant_id: str = TENANT, actor_type: ActorType = ActorType.HUMAN) -> ActorContext:
    return ActorContext(
        actor_id="account-h01",
        actor_type=actor_type,
        tenant_id=tenant_id,
        correlation_id="corr-h01-001",
    )


def _candidate(**overrides: object) -> LiveSessionCandidate:
    now = datetime.now(UTC)
    values: dict[str, object] = {
        "session_ref": SESSION,
        "tenant_id": TENANT,
        "family_id": FAMILY,
        "title": "21天晚间学习启动说明",
        "starts_at": now + timedelta(hours=1),
        "ends_at": now + timedelta(hours=2),
        "status": "SCHEDULED",
        "audience_scope": "FAMILY_GUARDIANS",
        "guardian_person_ids": (GUARDIAN,),
        "approved": True,
        "effective_from": now - timedelta(minutes=1),
        "effective_to": now + timedelta(days=1),
        "source_system": "TEST_FIXTURE",
        "environment": "TEST",
        "fixture_only": True,
        "external_effect": False,
    }
    values.update(overrides)
    return LiveSessionCandidate(**values)


class FakeLiveReader:
    def __init__(self, candidate: LiveSessionCandidate | None) -> None:
        self.candidate = candidate
        self.calls: list[tuple[str, str, str]] = []

    async def get_session(
        self, *, tenant_id: str, family_id: str, session_ref: str
    ) -> LiveSessionCandidate | None:
        self.calls.append((tenant_id, family_id, session_ref))
        return self.candidate


@pytest.fixture
def wiring() -> tuple[TestClient, FakeLiveReader, AuditRecorder]:
    reader = FakeLiveReader(_candidate())
    recorder = AuditRecorder()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[deps.get_live_session_read_port] = lambda: reader
    # Keep the context server-derived and independent of the URL path.  If the
    # helper itself is registered, FastAPI sees its ``family_id`` parameter and
    # injects the path value, which would erase the cross-family negative case.
    app.dependency_overrides[deps.get_action_context] = lambda: _ctx()
    app.dependency_overrides[deps.get_actor_context] = _actor
    app.dependency_overrides[deps.get_audit_recorder] = lambda: recorder
    app.dependency_overrides[deps.get_policy_engine] = lambda: deps.build_policy_engine(
        InMemoryTenantDirectory({TENANT: TenantStatus.ACTIVE})
    )
    with TestClient(app) as client:
        yield client, reader, recorder


def test_import_openapi_and_success_shape(
    wiring: tuple[TestClient, FakeLiveReader, AuditRecorder],
) -> None:
    client, reader, recorder = wiring
    response = client.get(f"/families/{FAMILY}/live-sessions/{SESSION}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "h-live-01.v1"
    assert body["audience_scope"] == "FAMILY_GUARDIANS"
    assert body["source_system"] == "TEST_FIXTURE"
    assert body["fixture_only"] is True
    assert body["external_effect"] is False
    assert "guardian_person_ids" not in body
    assert "booking_request_id" not in body
    assert "playback_url" not in body
    assert reader.calls == [(TENANT, FAMILY, SESSION)]

    reads = recorder.all_events()
    assert len(reads) == 1
    assert reads[0].action_kind is AuditActionKind.READ
    assert reads[0].action == "read_live_session_detail"
    assert reads[0].access_purpose == "service_live_session_detail"
    assert reads[0].subject_person_id == GUARDIAN
    assert "session_ref" in reads[0].accessed_fields


def test_openapi_exposes_only_get_detail() -> None:
    app = FastAPI()
    app.include_router(router)
    operations = app.openapi()["paths"]["/families/{family_id}/live-sessions/{session_ref}"]
    assert set(operations) == {"get"}


def test_cross_family_path_is_forbidden(
    wiring: tuple[TestClient, FakeLiveReader, AuditRecorder],
) -> None:
    client, reader, _recorder = wiring
    response = client.get(f"/families/family-other/live-sessions/{SESSION}")
    assert response.status_code == 403
    assert response.json()["detail"] == "family_scope_violation"
    assert reader.calls == []


def test_actor_tenant_scope_is_forbidden(
    wiring: tuple[TestClient, FakeLiveReader, AuditRecorder],
) -> None:
    client, reader, _recorder = wiring
    client.app.dependency_overrides[deps.get_actor_context] = lambda: _actor(
        tenant_id="tenant-other"
    )
    response = client.get(f"/families/{FAMILY}/live-sessions/{SESSION}")
    assert response.status_code == 403
    assert response.json()["detail"] == "tenant_scope_violation"
    assert reader.calls == []


def test_non_guardian_and_ai_are_forbidden(
    wiring: tuple[TestClient, FakeLiveReader, AuditRecorder],
) -> None:
    client, reader, _recorder = wiring
    reader.candidate = _candidate(guardian_person_ids=("person-other",))
    response = client.get(f"/families/{FAMILY}/live-sessions/{SESSION}")
    assert response.status_code == 403
    assert response.json()["detail"] == "live_session_guardian_scope_violation"

    # The dependency override is replaced with an AI actor for the same request.
    client.app.dependency_overrides[deps.get_actor_context] = lambda: _actor(
        actor_type=ActorType.AI
    )
    response = client.get(f"/families/{FAMILY}/live-sessions/{SESSION}")
    assert response.status_code == 403
    assert response.json()["detail"] == "guardian_human_required"


@pytest.mark.parametrize(
    "overrides",
    [
        {"approved": False},
        {"effective_to": datetime.now(UTC) - timedelta(seconds=1)},
        {"tenant_id": "tenant-other"},
        {"family_id": "family-other"},
    ],
)
def test_unapproved_expired_or_mismatched_candidate_fails_closed(
    wiring: tuple[TestClient, FakeLiveReader, AuditRecorder], overrides: dict[str, object]
) -> None:
    client, reader, _recorder = wiring
    reader.candidate = _candidate(**overrides)
    response = client.get(f"/families/{FAMILY}/live-sessions/{SESSION}")
    if "tenant_id" in overrides or "family_id" in overrides:
        assert response.status_code == 403
        assert response.json()["detail"] == "live_session_scope_violation"
    else:
        assert response.status_code == 404
        assert response.json()["detail"] == "live_session_not_found"


def test_fixture_source_contradiction_is_rejected() -> None:
    with pytest.raises(ValueError, match="live_session_fixture_boundary_invalid"):
        _candidate(environment="PRODUCTION")

    with pytest.raises(ValueError, match="live_session_canonical_source_cannot_be_fixture"):
        _candidate(source_system="CANONICAL_LIVE", fixture_only=True)

    with pytest.raises(ValueError, match="live_session_external_effect_not_allowed"):
        _candidate(external_effect=True)

    with pytest.raises(ValueError, match="literal_error"):
        _candidate(audience_scope="PUBLIC")


def test_default_read_adapter_is_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="live-session read port not configured"):
        import asyncio

        asyncio.run(deps.get_live_session_read_port())
