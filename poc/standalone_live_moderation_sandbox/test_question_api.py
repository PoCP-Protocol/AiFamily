from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from poc.standalone_live_moderation_sandbox.question_api import create_app


def headers(
    *, role: str = "ADULT_VIEWER", family: str = "family.synthetic.alpha"
) -> dict[str, str]:
    return {
        "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
        "X-Fixture-Only": "true",
        "X-Tenant-Id": "tenant.synthetic.alpha",
        "X-Family-Id": family,
        "X-Actor-Id": "actor.synthetic.adult"
        if role == "ADULT_VIEWER"
        else "actor.synthetic.moderator",
        "X-Actor-Role": role,
    }


def test_question_requires_human_review_and_survives_app_restart(tmp_path: Path) -> None:
    database = tmp_path / "questions.sqlite3"
    client = TestClient(create_app(database))
    submitted = client.post(
        "/sandbox/live/sessions/live.synthetic.1/questions",
        headers=headers(),
        json={
            "question_ref": "question.1",
            "idempotency_key": "submit.1",
            "text": "怎样先听懂再回应？",
        },
    )
    assert submitted.status_code == 202
    assert submitted.json()["status"] == "PENDING"

    moderator_queue = client.get(
        "/sandbox/live/sessions/live.synthetic.1/questions",
        headers=headers(role="HUMAN_MODERATOR"),
    )
    assert moderator_queue.status_code == 200
    assert moderator_queue.json()[0]["status"] == "PENDING"

    another_family = client.get(
        "/sandbox/live/sessions/live.synthetic.1/questions",
        headers=headers(family="family.synthetic.other"),
    )
    assert another_family.json() == []

    reviewed = client.post(
        "/sandbox/moderation/questions/question.1/decision",
        headers=headers(role="HUMAN_MODERATOR"),
        json={"decision_key": "decision.1", "action": "APPROVE", "reason": "人工确认可展示"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "APPROVED"

    restarted = TestClient(create_app(database))
    visible = restarted.get(
        "/sandbox/live/sessions/live.synthetic.1/questions",
        headers=headers(),
    )
    assert visible.status_code == 200
    assert visible.json()[0]["text"] == "怎样先听懂再回应？"
    assert visible.json()[0]["source"] == "SANDBOX_SYNTHETIC"
    assert visible.json()[0]["fixture_only"] is True


def test_child_cross_scope_and_unauthenticated_requests_fail_closed(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "questions.sqlite3"))
    payload = {"question_ref": "question.2", "idempotency_key": "submit.2", "text": "测试问题"}
    assert (
        client.post("/sandbox/live/sessions/live.synthetic.1/questions", json=payload).status_code
        == 401
    )
    assert (
        client.post(
            "/sandbox/live/sessions/live.synthetic.1/questions",
            headers=headers(role="CHILD"),
            json=payload,
        ).status_code
        == 403
    )


def test_idempotency_conflicts_fail_closed(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "questions.sqlite3"))
    url = "/sandbox/live/sessions/live.synthetic.1/questions"
    first = {"question_ref": "question.3", "idempotency_key": "submit.3", "text": "第一个问题"}
    assert client.post(url, headers=headers(), json=first).status_code == 202
    assert client.post(url, headers=headers(), json=first).status_code == 202
    conflict = {**first, "question_ref": "question.4", "text": "冲突问题"}
    assert client.post(url, headers=headers(), json=conflict).status_code == 409


def test_only_human_moderator_can_decide_and_rejection_stays_hidden(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "questions.sqlite3"))
    client.post(
        "/sandbox/live/sessions/live.synthetic.1/questions",
        headers=headers(),
        json={"question_ref": "question.5", "idempotency_key": "submit.5", "text": "等待审核"},
    )
    decision = {"decision_key": "decision.5", "action": "REJECT", "reason": "人工判断不展示"}
    assert (
        client.post(
            "/sandbox/moderation/questions/question.5/decision",
            headers=headers(),
            json=decision,
        ).status_code
        == 403
    )
    rejected = client.post(
        "/sandbox/moderation/questions/question.5/decision",
        headers=headers(role="HUMAN_MODERATOR"),
        json=decision,
    )
    assert rejected.json()["status"] == "REJECTED"
    other_adult = headers()
    other_adult["X-Actor-Id"] = "actor.synthetic.other"
    assert (
        client.get(
            "/sandbox/live/sessions/live.synthetic.1/questions",
            headers=other_adult,
        ).json()
        == []
    )


def test_websocket_broadcasts_pending_then_human_reviewed_event(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "realtime.sqlite3"))
    query = (
        "source=SANDBOX_SYNTHETIC&fixture_only=true&tenant_id=tenant.synthetic.alpha&"
        "family_id=family.synthetic.alpha&actor_id=actor.synthetic.adult&role=ADULT_VIEWER"
    )
    with client.websocket_connect(
        f"/ws/sandbox/live/sessions/live.synthetic.1/questions?{query}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "CONNECTED"
        submitted = client.post(
            "/sandbox/live/sessions/live.synthetic.1/questions",
            headers=headers(),
            json={
                "question_ref": "question.realtime",
                "idempotency_key": "submit.realtime",
                "text": "这个方法可以如何练习？",
            },
        )
        assert submitted.status_code == 202
        pending_event = websocket.receive_json()
        assert pending_event["type"] == "QUESTION_SUBMITTED"
        assert pending_event["question"]["status"] == "PENDING"

        reviewed = client.post(
            "/sandbox/moderation/questions/question.realtime/decision",
            headers=headers(role="HUMAN_MODERATOR"),
            json={
                "decision_key": "decision.realtime",
                "action": "APPROVE",
                "reason": "人工确认可展示",
            },
        )
        assert reviewed.status_code == 200
        approved_event = websocket.receive_json()
        assert approved_event["type"] == "QUESTION_REVIEWED"
        assert approved_event["question"]["status"] == "APPROVED"
        assert approved_event["external_effect"] is False


def test_websocket_rejects_child_and_non_synthetic_scope(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "realtime-denied.sqlite3"))
    for query in (
        "source=SANDBOX_SYNTHETIC&fixture_only=true&tenant_id=tenant.synthetic.alpha&"
        "family_id=family.synthetic.alpha&actor_id=actor.synthetic.child&role=CHILD",
        "source=REAL&fixture_only=false&tenant_id=tenant.real&family_id=family.real&"
        "actor_id=actor.real&role=ADULT_VIEWER",
    ):
        with (
            pytest.raises(WebSocketDisconnect) as stopped,
            client.websocket_connect(
                f"/ws/sandbox/live/sessions/live.synthetic.1/questions?{query}"
            ) as websocket,
        ):
            websocket.receive_json()
        assert stopped.value.code == 4403


def test_pending_question_is_private_but_approved_event_reaches_family(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "realtime-privacy.sqlite3"))
    query = (
        "source=SANDBOX_SYNTHETIC&fixture_only=true&tenant_id=tenant.synthetic.alpha&"
        "family_id=family.synthetic.alpha&actor_id=actor.synthetic.other&role=ADULT_VIEWER"
    )
    with client.websocket_connect(
        f"/ws/sandbox/live/sessions/live.synthetic.1/questions?{query}"
    ) as websocket:
        assert websocket.receive_json()["type"] == "CONNECTED"
        assert (
            client.post(
                "/sandbox/live/sessions/live.synthetic.1/questions",
                headers=headers(),
                json={
                    "question_ref": "question.private",
                    "idempotency_key": "submit.private",
                    "text": "等待人工审核的问题",
                },
            ).status_code
            == 202
        )
        assert (
            client.post(
                "/sandbox/moderation/questions/question.private/decision",
                headers=headers(role="HUMAN_MODERATOR"),
                json={
                    "decision_key": "decision.private",
                    "action": "APPROVE",
                    "reason": "人工确认可展示",
                },
            ).status_code
            == 200
        )
        event = websocket.receive_json()
        assert event["type"] == "QUESTION_REVIEWED"
        assert event["question"]["status"] == "APPROVED"


def test_cors_allows_ephemeral_local_preview_ports_only(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "cors.sqlite3"))

    local = client.options(
        "/sandbox/live/sessions/live.synthetic.1/questions",
        headers={
            "Origin": "http://127.0.0.1:4205",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert local.status_code == 200
    assert local.headers["access-control-allow-origin"] == "http://127.0.0.1:4205"

    external = client.options(
        "/sandbox/live/sessions/live.synthetic.1/questions",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert external.status_code == 400
    assert "access-control-allow-origin" not in external.headers
