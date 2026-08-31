from pathlib import Path

from fastapi.testclient import TestClient

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
