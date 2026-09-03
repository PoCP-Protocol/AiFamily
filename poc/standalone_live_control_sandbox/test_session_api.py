from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from poc.standalone_live_control_sandbox import session_api
from poc.standalone_live_control_sandbox.control_plane import CanonicalConsentDecision
from poc.standalone_live_control_sandbox.session_api import (
    SyntheticConsentProjection,
    create_app,
)

NOW = datetime(2026, 9, 3, 12, tzinfo=UTC)


class ConsentProjection:
    def __init__(self, decision: CanonicalConsentDecision | None = None) -> None:
        self.decision = decision
        self.calls: list[dict[str, object]] = []

    def require_grant(self, **query: object) -> CanonicalConsentDecision:
        self.calls.append(query)
        if self.decision is not None:
            return self.decision
        return consent_decision(
            tenant_id=str(query["tenant_id"]),
            family_id=str(query["family_id"]),
            guardian_id=str(query["guardian_id"]),
        )


def consent_decision(**overrides: object) -> CanonicalConsentDecision:
    values: dict[str, object] = {
        "consent_ref": "consent.canonical.synthetic.1",
        "tenant_id": "tenant.synthetic.alpha",
        "family_id": "family.synthetic.alpha",
        "guardian_id": "actor.synthetic.adult_viewer",
        "purpose": "live_attendance",
        "granted": True,
        "expires_at": NOW + timedelta(hours=2),
    }
    values.update(overrides)
    return CanonicalConsentDecision(**values)  # type: ignore[arg-type]


def headers(
    *,
    role: str,
    tenant: str = "tenant.synthetic.alpha",
    family: str = "family.synthetic.alpha",
    actor: str | None = None,
) -> dict[str, str]:
    return {
        "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
        "X-Fixture-Only": "true",
        "X-Tenant-Id": tenant,
        "X-Family-Id": family,
        "X-Actor-Id": actor or f"actor.synthetic.{role.lower()}",
        "X-Actor-Role": role,
    }


def create_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "session_ref": "live.synthetic.control.1",
        "idempotency_key": "create-live-1",
        "title": "如何在冲突后重新开始沟通",
        "speaker": "合成专家",
        "expert_summary": "从一个可练习的小动作开始修复家庭沟通。",
        "applicable_scope": "成年家长与照护者",
        "problem_tags": ["家庭沟通", "冲突复盘"],
        "starts_at": (NOW - timedelta(minutes=5)).isoformat(),
        "ends_at": (NOW + timedelta(hours=1)).isoformat(),
        "audience_scope": "FAMILY",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(session_api, "now_utc", lambda: NOW)
    return TestClient(create_app(tmp_path / "control.sqlite3"))


def create_and_approve(client: TestClient) -> dict[str, object]:
    created = client.post(
        "/sandbox/live-control/sessions",
        headers=headers(role="CREATOR"),
        json=create_payload(),
    )
    assert created.status_code == 201
    approved = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/review",
        headers=headers(role="CONTENT_REVIEWER"),
        json={
            "decision_key": "review-live-1",
            "action": "APPROVE",
            "reason": "人工确认内容适合成年家庭成员",
            "review_ref": "review.synthetic.1",
        },
    )
    assert approved.status_code == 200
    return approved.json()


def registration_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "idempotency_key": "register-live-1",
        "correlation_id": "correlation-register-1",
    }
    payload.update(overrides)
    return payload


def registration_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    consent: ConsentProjection | None,
) -> TestClient:
    monkeypatch.setattr(session_api, "now_utc", lambda: NOW)
    return TestClient(create_app(tmp_path / "registration.sqlite3", consent=consent))


def test_creator_review_discovery_and_detail_happy_path(client: TestClient) -> None:
    body = create_and_approve(client)
    assert body["approval_status"] == "APPROVED"
    assert body["external_effect"] is False
    assert body["audit_mode"] == "SANDBOX_RECEIPT_ONLY"

    family_headers = headers(role="ADULT_VIEWER")
    discovery = client.get(
        "/sandbox/live-control/families/family.synthetic.alpha/sessions",
        headers=family_headers,
    )
    assert discovery.status_code == 200
    assert discovery.headers["cache-control"] == "no-store"
    assert [item["session_ref"] for item in discovery.json()] == ["live.synthetic.control.1"]
    detail = client.get(
        "/sandbox/live-control/families/family.synthetic.alpha/sessions/live.synthetic.control.1",
        headers=family_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["audience_scope"] == "FAMILY"
    assert "room" not in detail.text.lower()
    assert "token" not in detail.text.lower()


def test_unreviewed_rejected_withdrawn_and_expired_sessions_never_discover(
    client: TestClient,
) -> None:
    client.post(
        "/sandbox/live-control/sessions",
        headers=headers(role="CREATOR"),
        json=create_payload(),
    )
    discover_url = "/sandbox/live-control/families/family.synthetic.alpha/sessions"
    adult = headers(role="ADULT_VIEWER")
    assert client.get(discover_url, headers=adult).json() == []

    client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/review",
        headers=headers(role="CONTENT_REVIEWER"),
        json={
            "decision_key": "reject-live-1",
            "action": "REJECT",
            "reason": "内容不满足展示要求",
            "review_ref": "review.synthetic.reject",
        },
    )
    assert client.get(discover_url, headers=adult).json() == []

    second = create_payload(
        session_ref="live.synthetic.control.2",
        idempotency_key="create-live-2",
        ends_at=(NOW - timedelta(seconds=1)).isoformat(),
        starts_at=(NOW - timedelta(hours=1)).isoformat(),
    )
    client.post(
        "/sandbox/live-control/sessions",
        headers=headers(role="CREATOR"),
        json=second,
    )
    client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.2/review",
        headers=headers(role="CONTENT_REVIEWER"),
        json={
            "decision_key": "approve-expired",
            "action": "APPROVE",
            "reason": "合成过期反例",
            "review_ref": "review.synthetic.expired",
        },
    )
    assert client.get(discover_url, headers=adult).json() == []


def test_approved_session_can_go_live_then_withdraw_and_disappear(client: TestClient) -> None:
    create_and_approve(client)
    go_live = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/lifecycle",
        headers=headers(role="LIVE_OPERATOR"),
        json={
            "action_key": "go-live-1",
            "action": "GO_LIVE",
            "reason": "人工确认合成媒体已准备",
        },
    )
    assert go_live.status_code == 200
    assert go_live.json()["status"] == "LIVE"
    assert go_live.json()["section"] == "live-now"

    withdrawn = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/lifecycle",
        headers=headers(role="LIVE_OPERATOR"),
        json={
            "action_key": "withdraw-live-1",
            "action": "WITHDRAW",
            "reason": "人工停止演练",
        },
    )
    assert withdrawn.status_code == 200
    discovery = client.get(
        "/sandbox/live-control/families/family.synthetic.alpha/sessions",
        headers=headers(role="ADULT_VIEWER"),
    )
    assert discovery.json() == []
    detail = client.get(
        "/sandbox/live-control/families/family.synthetic.alpha/sessions/live.synthetic.control.1",
        headers=headers(role="ADULT_VIEWER"),
    )
    assert detail.status_code == 404


def test_create_and_review_idempotency_conflicts_fail_closed(client: TestClient) -> None:
    first = client.post(
        "/sandbox/live-control/sessions",
        headers=headers(role="CREATOR"),
        json=create_payload(),
    )
    replay = client.post(
        "/sandbox/live-control/sessions",
        headers=headers(role="CREATOR"),
        json=create_payload(),
    )
    assert first.status_code == replay.status_code == 201
    conflict = client.post(
        "/sandbox/live-control/sessions",
        headers=headers(role="CREATOR"),
        json=create_payload(title="不同内容"),
    )
    assert conflict.status_code == 409
    summary_conflict = client.post(
        "/sandbox/live-control/sessions",
        headers=headers(role="CREATOR"),
        json=create_payload(expert_summary="同一幂等键下的不同摘要"),
    )
    assert summary_conflict.status_code == 409

    create_and_approve(client)
    review_replay = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/review",
        headers=headers(role="CONTENT_REVIEWER"),
        json={
            "decision_key": "review-live-1",
            "action": "APPROVE",
            "reason": "人工确认内容适合成年家庭成员",
            "review_ref": "review.synthetic.1",
        },
    )
    assert review_replay.status_code == 200
    review_conflict = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/review",
        headers=headers(role="CONTENT_REVIEWER"),
        json={
            "decision_key": "review-live-1",
            "action": "WITHDRAW",
            "reason": "冲突",
            "review_ref": "review.synthetic.1",
        },
    )
    assert review_conflict.status_code == 409


def test_go_live_rejects_future_session_and_naive_timestamps(client: TestClient) -> None:
    future = create_payload(
        starts_at=(NOW + timedelta(minutes=10)).isoformat(),
        ends_at=(NOW + timedelta(hours=1)).isoformat(),
    )
    assert (
        client.post(
            "/sandbox/live-control/sessions",
            headers=headers(role="CREATOR"),
            json=future,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/sandbox/live-control/sessions/live.synthetic.control.1/review",
            headers=headers(role="CONTENT_REVIEWER"),
            json={
                "decision_key": "approve-future",
                "action": "APPROVE",
                "reason": "人工审核通过",
                "review_ref": "review.synthetic.future",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/sandbox/live-control/sessions/live.synthetic.control.1/lifecycle",
            headers=headers(role="LIVE_OPERATOR"),
            json={
                "action_key": "start-too-early",
                "action": "GO_LIVE",
                "reason": "提前开播反例",
            },
        ).status_code
        == 409
    )

    naive = create_payload(
        session_ref="live.synthetic.naive",
        idempotency_key="create-naive",
        starts_at="2026-09-03T12:00:00",
        ends_at="2026-09-03T13:00:00",
    )
    assert (
        client.post(
            "/sandbox/live-control/sessions",
            headers=headers(role="CREATOR"),
            json=naive,
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "request_headers, expected",
    [
        ({}, 401),
        (headers(role="CHILD"), 403),
        (headers(role="ADULT_VIEWER", tenant="tenant.real"), 403),
        (headers(role="ADULT_VIEWER", family="family.synthetic.other"), 403),
    ],
)
def test_discovery_requires_synthetic_adult_exact_scope(
    client: TestClient, request_headers: dict[str, str], expected: int
) -> None:
    response = client.get(
        "/sandbox/live-control/families/family.synthetic.alpha/sessions",
        headers=request_headers,
    )
    assert response.status_code == expected


def test_wrong_roles_cannot_create_review_or_operate(client: TestClient) -> None:
    assert (
        client.post(
            "/sandbox/live-control/sessions",
            headers=headers(role="ADULT_VIEWER"),
            json=create_payload(),
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/sandbox/live-control/sessions/missing/review",
            headers=headers(role="CREATOR"),
            json={
                "decision_key": "review-denied",
                "action": "APPROVE",
                "reason": "不允许",
                "review_ref": "review.denied",
            },
        ).status_code
        == 403
    )


def test_receipts_survive_app_restart_without_claiming_canonical_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session_api, "now_utc", lambda: NOW)
    database = tmp_path / "restart.sqlite3"
    first = TestClient(create_app(database))
    create_and_approve(first)
    second = TestClient(create_app(database))
    receipts = second.get(
        "/sandbox/live-control/sessions/live.synthetic.control.1/receipts",
        headers=headers(role="LIVE_OPERATOR"),
    )
    assert receipts.status_code == 200
    body = receipts.json()
    assert [item["action"] for item in body["receipts"]] == [
        "SESSION_CREATED",
        "SESSION_APPROVE",
    ]
    assert body["audit_mode"] == "SANDBOX_RECEIPT_ONLY"
    assert body["external_effect"] is False


def test_health_and_response_shape_are_explicit(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
        "synthetic_consent_enabled": False,
        "consent_persistence": False,
        "external_effect": False,
    }


def test_explicit_synthetic_consent_adapter_enables_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session_api, "now_utc", lambda: NOW)
    client = TestClient(
        create_app(
            tmp_path / "synthetic-consent.sqlite3",
            consent=SyntheticConsentProjection(),
        )
    )
    create_and_approve(client)

    health = client.get("/health").json()
    assert health["synthetic_consent_enabled"] is True
    assert health["fixture_only"] is True
    assert health["consent_persistence"] is False
    response = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/registrations",
        headers=headers(role="ADULT_VIEWER"),
        json=registration_payload(),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "CONFIRMED"
    assert response.json()["consent_ref"].startswith("consent.synthetic.ephemeral.")
    assert response.json()["external_effect"] is False


def test_synthetic_consent_projection_is_short_lived_and_not_persistent() -> None:
    projection = SyntheticConsentProjection(ttl=timedelta(minutes=7))

    decision = projection.require_grant(
        tenant_id="tenant.synthetic.alpha",
        family_id="family.synthetic.alpha",
        guardian_id="actor.synthetic.adult_viewer",
        purpose="live_attendance",
        session_ref="live.synthetic.control.1",
        now=NOW,
    )

    assert decision.granted is True
    assert decision.expires_at == NOW + timedelta(minutes=7)
    assert not hasattr(projection, "database")
    with pytest.raises(ValueError, match="within 15 minutes"):
        SyntheticConsentProjection(ttl=timedelta(minutes=16))


def test_synthetic_consent_does_not_bypass_session_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session_api, "now_utc", lambda: NOW)
    client = TestClient(
        create_app(
            tmp_path / "synthetic-consent-scope.sqlite3",
            consent=SyntheticConsentProjection(),
        )
    )
    create_and_approve(client)

    response = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/registrations",
        headers=headers(role="ADULT_VIEWER", family="family.synthetic.other"),
        json=registration_payload(),
    )

    assert response.status_code == 403


def test_cli_wires_synthetic_consent_only_when_explicitly_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run(app, *, host: str, port: int) -> None:
        captured.update(app=app, host=host, port=port)

    monkeypatch.setattr(session_api.uvicorn, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "session_api.py",
            "--serve",
            "--database",
            str(tmp_path / "cli.sqlite3"),
            "--port",
            "55301",
        ],
    )

    session_api.main()

    disabled_health = TestClient(captured["app"]).get("/health").json()
    assert disabled_health["synthetic_consent_enabled"] is False
    captured.clear()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "session_api.py",
            "--serve",
            "--database",
            str(tmp_path / "cli.sqlite3"),
            "--port",
            "55301",
            "--enable-synthetic-consent",
        ],
    )

    session_api.main()

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 55301
    health = TestClient(captured["app"]).get("/health").json()
    assert health["synthetic_consent_enabled"] is True
    assert health["source"] == "SANDBOX_SYNTHETIC"
    assert health["fixture_only"] is True
    assert health["consent_persistence"] is False


def test_adult_registers_and_cancels_with_canonical_consent_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consent = ConsentProjection()
    client = registration_client(tmp_path, monkeypatch, consent)
    create_and_approve(client)

    registered = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/registrations",
        headers=headers(role="ADULT_VIEWER"),
        json=registration_payload(),
    )

    assert registered.status_code == 201
    body = registered.json()
    assert body["status"] == "CONFIRMED"
    assert body["replayed"] is False
    assert body["consent_ref"] == "consent.canonical.synthetic.1"
    assert body["purpose"] == "live_attendance"
    assert body["fixture_only"] is True
    assert body["external_effect"] is False
    assert consent.calls == [
        {
            "tenant_id": "tenant.synthetic.alpha",
            "family_id": "family.synthetic.alpha",
            "guardian_id": "actor.synthetic.adult_viewer",
            "purpose": "live_attendance",
            "session_ref": "live.synthetic.control.1",
            "now": NOW,
        }
    ]

    cancelled = client.post(
        f"/sandbox/live-control/registrations/{body['registration_ref']}/cancel",
        headers=headers(role="ADULT_VIEWER"),
        json=registration_payload(
            idempotency_key="cancel-live-1",
            correlation_id="correlation-cancel-1",
        ),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["external_effect"] is False
    receipts = client.get(
        "/sandbox/live-control/sessions/live.synthetic.control.1/receipts",
        headers=headers(role="LIVE_OPERATOR"),
    ).json()["receipts"]
    assert [receipt["action"] for receipt in receipts[-2:]] == [
        "REGISTRATION_CONFIRMED",
        "REGISTRATION_CANCELLED",
    ]


def test_registration_and_cancel_are_persistent_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consent = ConsentProjection()
    database = tmp_path / "persistent-registration.sqlite3"
    monkeypatch.setattr(session_api, "now_utc", lambda: NOW)
    first = TestClient(create_app(database, consent=consent))
    create_and_approve(first)
    initial = first.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/registrations",
        headers=headers(role="ADULT_VIEWER"),
        json=registration_payload(),
    )
    registration_ref = initial.json()["registration_ref"]

    second = TestClient(create_app(database, consent=consent))
    replay = second.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/registrations",
        headers=headers(role="ADULT_VIEWER"),
        json=registration_payload(),
    )
    assert replay.status_code == 201
    assert replay.json()["registration_ref"] == registration_ref
    assert replay.json()["replayed"] is True
    assert len(consent.calls) == 1

    cancel_payload = registration_payload(
        idempotency_key="cancel-live-1",
        correlation_id="correlation-cancel-1",
    )
    cancelled = second.post(
        f"/sandbox/live-control/registrations/{registration_ref}/cancel",
        headers=headers(role="ADULT_VIEWER"),
        json=cancel_payload,
    )
    third = TestClient(create_app(database, consent=consent))
    cancel_replay = third.post(
        f"/sandbox/live-control/registrations/{registration_ref}/cancel",
        headers=headers(role="ADULT_VIEWER"),
        json=cancel_payload,
    )
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancel_replay.status_code == 200
    assert cancel_replay.json()["status"] == "CANCELLED"
    assert cancel_replay.json()["replayed"] is True


def test_missing_consent_provider_returns_503_without_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = registration_client(tmp_path, monkeypatch, None)
    create_and_approve(client)

    response = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/registrations",
        headers=headers(role="ADULT_VIEWER"),
        json=registration_payload(),
    )

    assert response.status_code == 503
    with session_api.connect(tmp_path / "registration.sqlite3") as database:
        count = database.execute("SELECT COUNT(*) FROM live_registrations").fetchone()[0]
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert count == 0
    assert not any("consent" in table.lower() for table in tables)


def test_consent_projection_failure_returns_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingConsentProjection:
        def require_grant(self, **query: object) -> CanonicalConsentDecision:
            del query
            raise RuntimeError("synthetic canonical adapter failure")

    monkeypatch.setattr(session_api, "now_utc", lambda: NOW)
    client = TestClient(
        create_app(tmp_path / "failed-consent.sqlite3", consent=FailingConsentProjection())
    )
    create_and_approve(client)

    response = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/registrations",
        headers=headers(role="ADULT_VIEWER"),
        json=registration_payload(),
    )

    assert response.status_code == 503
    assert "adapter failure" not in response.text


@pytest.mark.parametrize(
    "decision",
    [
        consent_decision(granted=False),
        consent_decision(expires_at=NOW - timedelta(seconds=1)),
        consent_decision(purpose="other"),
        consent_decision(tenant_id="tenant.synthetic.other"),
        consent_decision(family_id="family.synthetic.other"),
        consent_decision(guardian_id="actor.synthetic.other"),
    ],
)
def test_withdrawn_expired_or_cross_scope_consent_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: CanonicalConsentDecision,
) -> None:
    client = registration_client(tmp_path, monkeypatch, ConsentProjection(decision))
    create_and_approve(client)

    response = client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/registrations",
        headers=headers(role="ADULT_VIEWER"),
        json=registration_payload(),
    )

    assert response.status_code == 403


def test_registration_requires_approved_unexpired_scheduled_family_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consent = ConsentProjection()
    client = registration_client(tmp_path, monkeypatch, consent)
    endpoint = "/sandbox/live-control/sessions/live.synthetic.control.1/registrations"

    client.post(
        "/sandbox/live-control/sessions",
        headers=headers(role="CREATOR"),
        json=create_payload(),
    )
    assert (
        client.post(
            endpoint,
            headers=headers(role="ADULT_VIEWER"),
            json=registration_payload(),
        ).status_code
        == 409
    )
    client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/review",
        headers=headers(role="CONTENT_REVIEWER"),
        json={
            "decision_key": "review-live-before-registration",
            "action": "APPROVE",
            "reason": "人工审核通过",
            "review_ref": "review.synthetic.before-registration",
        },
    )
    client.post(
        "/sandbox/live-control/sessions/live.synthetic.control.1/lifecycle",
        headers=headers(role="LIVE_OPERATOR"),
        json={
            "action_key": "go-live-before-registration",
            "action": "GO_LIVE",
            "reason": "合成开播反例",
        },
    )
    assert (
        client.post(
            endpoint,
            headers=headers(role="ADULT_VIEWER"),
            json=registration_payload(
                idempotency_key="register-live-session",
                correlation_id="correlation-live-session",
            ),
        ).status_code
        == 409
    )

    expired = create_payload(
        session_ref="live.synthetic.expired",
        idempotency_key="create-expired",
        starts_at=(NOW - timedelta(hours=2)).isoformat(),
        ends_at=(NOW - timedelta(hours=1)).isoformat(),
    )
    client.post(
        "/sandbox/live-control/sessions",
        headers=headers(role="CREATOR"),
        json=expired,
    )
    client.post(
        "/sandbox/live-control/sessions/live.synthetic.expired/review",
        headers=headers(role="CONTENT_REVIEWER"),
        json={
            "decision_key": "review-expired-registration",
            "action": "APPROVE",
            "reason": "合成过期反例",
            "review_ref": "review.synthetic.expired-registration",
        },
    )
    assert (
        client.post(
            "/sandbox/live-control/sessions/live.synthetic.expired/registrations",
            headers=headers(role="ADULT_VIEWER"),
            json=registration_payload(
                idempotency_key="register-expired",
                correlation_id="correlation-expired",
            ),
        ).status_code
        == 409
    )


def test_registration_scope_role_and_idempotency_conflicts_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    consent = ConsentProjection()
    client = registration_client(tmp_path, monkeypatch, consent)
    create_and_approve(client)
    endpoint = "/sandbox/live-control/sessions/live.synthetic.control.1/registrations"

    assert client.post(endpoint, json=registration_payload()).status_code == 401
    assert (
        client.post(
            endpoint,
            headers=headers(role="CHILD"),
            json=registration_payload(),
        ).status_code
        == 403
    )
    assert (
        client.post(
            endpoint,
            headers=headers(role="ADULT_VIEWER", family="family.synthetic.other"),
            json=registration_payload(),
        ).status_code
        == 403
    )

    created = client.post(
        endpoint,
        headers=headers(role="ADULT_VIEWER"),
        json=registration_payload(),
    )
    assert created.status_code == 201
    assert (
        client.post(
            endpoint,
            headers=headers(role="ADULT_VIEWER"),
            json=registration_payload(correlation_id="different-correlation"),
        ).status_code
        == 409
    )
    assert (
        client.post(
            endpoint,
            headers=headers(role="ADULT_VIEWER"),
            json=registration_payload(
                idempotency_key="different-register-key",
                correlation_id="different-register-correlation",
            ),
        ).status_code
        == 409
    )

    registration_ref = created.json()["registration_ref"]
    cancel_payload = registration_payload(
        idempotency_key="cancel-live-1",
        correlation_id="correlation-cancel-1",
    )
    assert (
        client.post(
            f"/sandbox/live-control/registrations/{registration_ref}/cancel",
            headers=headers(role="ADULT_VIEWER", actor="actor.synthetic.other-adult"),
            json=cancel_payload,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/sandbox/live-control/registrations/{registration_ref}/cancel",
            headers=headers(role="ADULT_VIEWER"),
            json=cancel_payload,
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/sandbox/live-control/registrations/{registration_ref}/cancel",
            headers=headers(role="ADULT_VIEWER"),
            json=registration_payload(
                idempotency_key="cancel-live-2",
                correlation_id="correlation-cancel-2",
            ),
        ).status_code
        == 409
    )


def test_operator_listing_is_scoped_role_gated_and_restart_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(session_api, "now_utc", lambda: NOW)
    database = tmp_path / "operator-list.sqlite3"
    first = TestClient(create_app(database))
    create_and_approve(first)
    second = TestClient(create_app(database))
    listing = second.get(
        "/sandbox/live-control/operator/sessions",
        headers=headers(role="CREATOR"),
    )
    assert listing.status_code == 200
    assert listing.headers["cache-control"] == "no-store"
    assert listing.json()[0]["session_ref"] == "live.synthetic.control.1"
    assert (
        second.get(
            "/sandbox/live-control/operator/sessions",
            headers=headers(role="ADULT_VIEWER"),
        ).status_code
        == 403
    )
    other_family = second.get(
        "/sandbox/live-control/operator/sessions",
        headers=headers(role="CREATOR", family="family.synthetic.other"),
    )
    assert other_family.status_code == 200
    assert other_family.json() == []
