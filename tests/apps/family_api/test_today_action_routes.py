from fastapi.testclient import TestClient

from backend.apps.family_api.dev_wiring import reset_dev_state
from backend.apps.family_api.main import create_app


def _session(client: TestClient, ref: str) -> dict[str, str]:
    response = client.post(
        "/auth/account-session",
        headers={"Idempotency-Key": ref},
        json={"external_ref": ref},
    )
    return response.json()


def test_today_start_check_in_and_replay() -> None:
    reset_dev_state()
    client = TestClient(create_app())
    session = _session(client, "parent:family-today")
    headers = {"Authorization": f"Bearer {session['token']}"}
    assert (
        client.get("/families/family-today/today", headers=headers).json()["tasks"][0]["state"]
        == "AVAILABLE"
    )
    start = client.post(
        "/families/family-today/tasks/task:today:first-step/state",
        headers={**headers, "Idempotency-Key": "start-1"},
        json={"state": "STARTED"},
    )
    assert start.status_code == 200
    check = client.post(
        "/families/family-today/tasks/task:today:first-step/check-in",
        headers={**headers, "Idempotency-Key": "check-1"},
        json={"note": "done"},
    )
    replay = client.post(
        "/families/family-today/tasks/task:today:first-step/check-in",
        headers={**headers, "Idempotency-Key": "check-1"},
        json={"note": "done"},
    )
    assert check.status_code == 200
    assert replay.json()["action_id"] == check.json()["action_id"]
    assert replay.json()["replayed"] is True


def test_today_fail_closed_and_idempotency() -> None:
    reset_dev_state()
    client = TestClient(create_app())
    session = _session(client, "parent:family-a")
    headers = {"Authorization": f"Bearer {session['token']}"}
    assert client.get("/families/family-a/today").status_code == 401
    assert client.get("/families/family-b/today", headers=headers).status_code == 403
    response = client.post(
        "/families/family-a/tasks/task:today:first-step/state",
        headers=headers,
        json={"state": "STARTED"},
    )
    assert response.status_code == 400
    invalid = client.post(
        "/families/family-a/tasks/task:today:first-step/state",
        headers={**headers, "Idempotency-Key": "bad-state"},
        json={"state": "DONE"},
    )
    assert invalid.status_code == 400
