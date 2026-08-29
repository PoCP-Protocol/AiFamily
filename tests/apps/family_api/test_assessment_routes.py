"""HTTP acceptance tests for UI-02 -> UI-03."""

from fastapi.testclient import TestClient

from backend.apps.family_api.main import create_app


def _session(client: TestClient, family: str = "family-a") -> tuple[str, dict]:
    response = client.post(
        "/auth/account-session",
        json={"external_ref": f"account-a:{family}"},
        headers={"idempotency-key": "auth-1"},
    )
    return response.json()["token"], {"Authorization": f"Bearer {response.json()['token']}"}


def test_http_chain_idempotency_auth_and_audit() -> None:
    client = TestClient(create_app())
    token, auth = _session(client)
    family = "family-a"

    start = client.post("/families/family-a/assessments/sessions", json={"subject_person_id": "child-a"}, headers={**auth, "idempotency-key": "start-1"})
    replay = client.post("/families/family-a/assessments/sessions", json={"subject_person_id": "child-a"}, headers={**auth, "idempotency-key": "start-1"})
    assert start.status_code == replay.status_code == 200
    assert start.json() == replay.json()
    session_id = start.json()["session_id"]

    assert client.post(f"/families/{family}/assessments/sessions/{session_id}/responses", json={"item_ref": "item-1", "response_type": "TEXT", "response_value": "沟通"}, headers={**auth, "idempotency-key": "response-1"}).status_code == 200
    assert client.post(f"/families/{family}/assessments/sessions/{session_id}/submit", json={}, headers={**auth, "idempotency-key": "submit-1"}).status_code == 200
    hypothesis = client.post(f"/families/{family}/assessments/{session_id}/growth-hypothesis", json={}, headers={**auth, "idempotency-key": "hypothesis-1"}).json()
    decision = client.post(f"/families/{family}/growth-hypotheses/decisions", json={"assessment_session_id": session_id, "hypothesis_ref": hypothesis["hypothesis_ref"], "decision_type": "CONFIRM"}, headers={**auth, "idempotency-key": "decision-1"})

    assert decision.status_code == 200
    assert decision.json()["hypothesis"]["canonical_fact"] is False
    assert decision.json()["growth_intent"]["kind"] == "GrowthIntent"
    assert len(client.app.state.assessment.service.audit.all_events()) >= 5


def test_unauthorized_and_cross_family_requests_are_rejected() -> None:
    client = TestClient(create_app())
    token, auth = _session(client)
    assert token
    assert client.get("/families/family-a/ui/02/assessment").status_code == 401
    assert client.get("/families/family-b/ui/02/assessment", headers=auth).status_code == 403
    assert client.post("/families/family-a/assessments/sessions", json={"subject_person_id": "child-a"}, headers=auth).status_code == 400