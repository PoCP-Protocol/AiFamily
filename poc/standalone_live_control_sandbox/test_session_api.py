from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from poc.standalone_live_control_sandbox import session_api
from poc.standalone_live_control_sandbox.session_api import create_app

NOW = datetime(2026, 9, 3, 12, tzinfo=UTC)


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
        "external_effect": False,
    }


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
    assert second.get(
        "/sandbox/live-control/operator/sessions",
        headers=headers(role="ADULT_VIEWER"),
    ).status_code == 403
    other_family = second.get(
        "/sandbox/live-control/operator/sessions",
        headers=headers(role="CREATOR", family="family.synthetic.other"),
    )
    assert other_family.status_code == 200
    assert other_family.json() == []
