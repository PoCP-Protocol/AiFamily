from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from poc.standalone_live_moderation_sandbox.incident_api import (
    IncidentContext,
    create_app,
)


def headers(
    *,
    role: str = "ADULT_VIEWER",
    tenant: str = "tenant.synthetic.alpha",
    family: str = "family.synthetic.alpha",
    actor: str | None = None,
) -> dict[str, str]:
    default_actor = {
        "ADULT_VIEWER": "actor.synthetic.adult",
        "HUMAN_MODERATOR": "actor.synthetic.moderator",
        "CREATOR": "actor.synthetic.creator",
        "AI_AGENT": "actor.synthetic.ai",
        "CHILD": "actor.synthetic.child",
    }.get(role, "actor.synthetic.unsafe")
    return {
        "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
        "X-Fixture-Only": "true",
        "X-Tenant-Id": tenant,
        "X-Family-Id": family,
        "X-Actor-Id": actor or default_actor,
        "X-Actor-Role": role,
    }


def report_payload(suffix: str = "1") -> dict[str, str]:
    return {
        "report_ref": f"incident.synthetic.{suffix}",
        "idempotency_key": f"report-key.{suffix}",
        "reason": "直播内容可能不适合当前家庭场景",
    }


def submit(client: TestClient, suffix: str = "1"):
    return client.post(
        "/sandbox/live-incidents/sessions/session.synthetic.1/reports",
        headers=headers(),
        json=report_payload(suffix),
    )


class RecordingPort:
    def __init__(self, name: str, fail_at: str | None = None) -> None:
        self.name = name
        self.fail_at = fail_at
        self.calls: list[str] = []

    def prepare(self, context: IncidentContext) -> object:
        self.calls.append(f"prepare:{context.action}")
        if self.fail_at == "prepare":
            raise RuntimeError(f"{self.name} prepare failed")
        return context

    def commit(self, prepared: object) -> None:
        context = prepared
        assert isinstance(context, IncidentContext)
        self.calls.append(f"commit:{context.action}")
        if self.fail_at == "commit":
            raise RuntimeError(f"{self.name} commit failed")

    def rollback(self, prepared: object) -> None:
        context = prepared
        assert isinstance(context, IncidentContext)
        self.calls.append(f"rollback:{context.action}")


def decision(action: str, suffix: str = "1") -> dict[str, str]:
    return {
        "decision_key": f"decision-key.{suffix}",
        "action": action,
        "reason": "人工复核并执行最小必要处置",
    }


@pytest.mark.parametrize(
    ("action", "state", "components"),
    [
        ("CONTINUE", "CONTINUED", []),
        ("HIDE", "HIDDEN", ["control", "interaction"]),
        ("STOP", "STOPPED", ["control", "interaction", "media"]),
    ],
)
def test_adult_reports_and_only_human_moderator_decides(
    tmp_path: Path, action: str, state: str, components: list[str]
) -> None:
    ports = [RecordingPort(name) for name in ("control", "interaction", "media")]
    client = TestClient(
        create_app(
            tmp_path / f"{action}.sqlite3",
            control_port=ports[0],
            interaction_port=ports[1],
            media_port=ports[2],
        )
    )
    created = submit(client)
    assert created.status_code == 202
    assert created.json()["state"] == "PENDING"
    assert created.json()["external_effect"] is False

    decided = client.post(
        "/sandbox/live-incidents/reports/incident.synthetic.1/decisions",
        headers=headers(role="HUMAN_MODERATOR"),
        json=decision(action),
    )
    assert decided.status_code == 200
    body = decided.json()
    assert body["state"] == state
    assert body["receipt"] == {
        "receipt_ref": "sandbox-receipt:decision-key.1",
        "action": action,
        "completed_components": components,
        "audit_mode": "SANDBOX_RECEIPT_ONLY",
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
        "external_effect": False,
    }


def test_report_and_decision_idempotency_conflicts(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "incidents.sqlite3"))
    first = submit(client)
    assert first.status_code == 202
    assert submit(client).json() == first.json()

    changed_report = report_payload()
    changed_report["reason"] = "相同键但不同举报内容"
    assert (
        client.post(
            "/sandbox/live-incidents/sessions/session.synthetic.1/reports",
            headers=headers(),
            json=changed_report,
        ).status_code
        == 409
    )

    url = "/sandbox/live-incidents/reports/incident.synthetic.1/decisions"
    payload = decision("STOP")
    first_decision = client.post(url, headers=headers(role="HUMAN_MODERATOR"), json=payload)
    assert first_decision.status_code == 200
    assert client.post(url, headers=headers(role="HUMAN_MODERATOR"), json=payload).json() == (
        first_decision.json()
    )
    changed_decision = {**payload, "action": "HIDE"}
    assert (
        client.post(
            url,
            headers=headers(role="HUMAN_MODERATOR"),
            json=changed_decision,
        ).status_code
        == 409
    )


@pytest.mark.parametrize("role", ["AI_AGENT", "CREATOR", "CHILD", "ADULT_VIEWER"])
def test_non_human_roles_cannot_decide(tmp_path: Path, role: str) -> None:
    client = TestClient(create_app(tmp_path / f"{role}.sqlite3"))
    assert submit(client).status_code == 202
    result = client.post(
        "/sandbox/live-incidents/reports/incident.synthetic.1/decisions",
        headers=headers(role=role),
        json=decision("STOP"),
    )
    assert result.status_code == 403


def test_auth_scope_and_listing_fail_closed(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "scope.sqlite3"))
    payload = report_payload()
    url = "/sandbox/live-incidents/sessions/session.synthetic.1/reports"
    assert client.post(url, json=payload).status_code == 401
    assert client.post(url, headers=headers(role="CHILD"), json=payload).status_code == 403
    unsafe = headers()
    unsafe["X-Actor-Id"] = "real-user"
    assert client.post(url, headers=unsafe, json=payload).status_code == 403
    assert submit(client).status_code == 202

    other_scope = headers(role="HUMAN_MODERATOR", family="family.synthetic.other")
    assert client.get("/sandbox/live-incidents/reports", headers=other_scope).json() == []
    denied = client.post(
        "/sandbox/live-incidents/reports/incident.synthetic.1/decisions",
        headers=other_scope,
        json=decision("STOP"),
    )
    assert denied.status_code == 403


@pytest.mark.parametrize(
    ("failed_component", "fail_at"),
    [
        ("control", "prepare"),
        ("interaction", "commit"),
        ("media", "commit"),
    ],
)
def test_stop_port_failure_rolls_back_and_keeps_pending(
    tmp_path: Path, failed_component: str, fail_at: str
) -> None:
    ports = {
        name: RecordingPort(name, fail_at if name == failed_component else None)
        for name in ("control", "interaction", "media")
    }
    database = tmp_path / f"failure-{failed_component}.sqlite3"
    client = TestClient(
        create_app(
            database,
            control_port=ports["control"],
            interaction_port=ports["interaction"],
            media_port=ports["media"],
        )
    )
    assert submit(client).status_code == 202
    failed = client.post(
        "/sandbox/live-incidents/reports/incident.synthetic.1/decisions",
        headers=headers(role="HUMAN_MODERATOR"),
        json=decision("STOP"),
    )
    assert failed.status_code == 503
    queue = client.get("/sandbox/live-incidents/reports", headers=headers(role="HUMAN_MODERATOR"))
    assert queue.json()[0]["state"] == "PENDING"
    assert queue.json()[0]["receipt"] is None
    committed = [port for port in ports.values() if any("commit:" in call for call in port.calls)]
    assert all(any("rollback:" in call for call in port.calls) for port in committed)


def test_sqlite_restart_restores_pending_terminal_and_idempotency(tmp_path: Path) -> None:
    database = tmp_path / "restart.sqlite3"
    first = TestClient(create_app(database))
    assert submit(first, "pending").status_code == 202
    assert submit(first, "terminal").status_code == 202
    terminal_url = "/sandbox/live-incidents/reports/incident.synthetic.terminal/decisions"
    payload = decision("STOP", "restart")
    decided = first.post(terminal_url, headers=headers(role="HUMAN_MODERATOR"), json=payload)
    assert decided.status_code == 200

    restarted = TestClient(create_app(database))
    queue = restarted.get(
        "/sandbox/live-incidents/reports", headers=headers(role="HUMAN_MODERATOR")
    ).json()
    assert {item["report_ref"]: item["state"] for item in queue} == {
        "incident.synthetic.pending": "PENDING",
        "incident.synthetic.terminal": "STOPPED",
    }
    replay = restarted.post(terminal_url, headers=headers(role="HUMAN_MODERATOR"), json=payload)
    assert replay.json() == decided.json()


def test_missing_incident_and_blank_reasons_are_rejected(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "validation.sqlite3"))
    blank_report = report_payload()
    blank_report["reason"] = "  "
    assert (
        client.post(
            "/sandbox/live-incidents/sessions/session.synthetic.1/reports",
            headers=headers(),
            json=blank_report,
        ).status_code
        == 422
    )
    missing = client.post(
        "/sandbox/live-incidents/reports/incident.synthetic.missing/decisions",
        headers=headers(role="HUMAN_MODERATOR"),
        json=decision("STOP"),
    )
    assert missing.status_code == 404
    assert submit(client).status_code == 202
    blank_decision = decision("STOP")
    blank_decision["reason"] = " "
    assert (
        client.post(
            "/sandbox/live-incidents/reports/incident.synthetic.1/decisions",
            headers=headers(role="HUMAN_MODERATOR"),
            json=blank_decision,
        ).status_code
        == 422
    )
