"""HTTP acceptance tests for the UI-02 -> UI-03 chain.

Rewritten for the four-layer refactor. Three things changed and each broke the
previous version of this file:

1. Handler construction moved out of `api.py` into dependencies that raise by
   design, so the app is only callable with `dev_wiring` installed
   (`AIFAMILY_ENV=dev`). Without it every route returns 500.
2. `app.state.assessment.service.audit` no longer exists — audit is reached
   through `backend.platform.audit`, not through per-app state.
3. `subject_person_id` must be a UUID (`commands._is_uuid`). The old fixture
   passed `"child-a"`, which is why the "missing idempotency-key returns 400"
   assertion below used to pass for the wrong reason: the request was rejected
   for a malformed person id before the idempotency check was ever reached. Each
   assertion here now fails only for the reason it names.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.dev_wiring import reset_dev_state
from backend.apps.family_api.main import create_app

FAMILY = "family-a"
OTHER_FAMILY = "family-b"


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`create_app` only installs dev wiring when the environment says dev.

    Set before `create_app` is called, not after: the decision is made once at
    construction time.
    """
    monkeypatch.setenv("AIFAMILY_ENV", "dev")
    reset_dev_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _auth(client: TestClient, family: str = FAMILY, key: str = "auth-1") -> dict[str, str]:
    """Exchange a dev external_ref for a bearer token.

    The `<account>:<family>` convention is what binds the session to a family —
    the family is the segment after the colon.
    """
    response = client.post(
        "/auth/account-session",
        json={"external_ref": f"account-a:{family}"},
        headers={"idempotency-key": key},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_http_chain_is_idempotent_end_to_end(client: TestClient) -> None:
    auth = _auth(client)
    subject = str(uuid.uuid4())

    start = client.post(
        f"/families/{FAMILY}/assessments/sessions",
        json={"subject_person_id": subject},
        headers={**auth, "idempotency-key": "start-1"},
    )
    assert start.status_code == 200, start.text

    # Same key, same payload: a replay must return the original receipt rather
    # than opening a second session. Comparing the whole body, not just the
    # status, is the point — a second session would also answer 200.
    replay = client.post(
        f"/families/{FAMILY}/assessments/sessions",
        json={"subject_person_id": subject},
        headers={**auth, "idempotency-key": "start-1"},
    )
    assert replay.status_code == 200
    assert start.json() == replay.json()

    session_id = start.json()["session_id"]

    assert (
        client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/responses",
            json={"item_ref": "item-1", "response_type": "TEXT", "response_value": "沟通"},
            headers={**auth, "idempotency-key": "response-1"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/submit",
            json={},
            headers={**auth, "idempotency-key": "submit-1"},
        ).status_code
        == 200
    )

    hypothesis = client.post(
        f"/families/{FAMILY}/assessments/{session_id}/growth-hypothesis",
        json={},
        headers={**auth, "idempotency-key": "hypothesis-1"},
    )
    assert hypothesis.status_code == 200, hypothesis.text

    decision = client.post(
        f"/families/{FAMILY}/growth-hypotheses/decisions",
        json={
            "assessment_session_id": session_id,
            "hypothesis_ref": hypothesis.json()["hypothesis_ref"],
            "decision_type": "CONFIRM",
        },
        headers={**auth, "idempotency-key": "decision-1"},
    )
    assert decision.status_code == 200, decision.text

    # R9: confirming a hypothesis produces a GrowthIntent, and the hypothesis
    # itself stays non-canonical. A confirmed hypothesis becoming a fact is the
    # exact failure R9 exists to prevent.
    body = decision.json()
    assert body["hypothesis"]["canonical_fact"] is False
    assert body["growth_intent"]["kind"] == "GrowthIntent"


def test_missing_credential_is_401_not_403(client: TestClient) -> None:
    """No usable credential and wrong-family credential are different answers.

    Collapsing them would tell a caller holding a valid token for family A that
    family B does not exist.
    """
    assert client.get(f"/families/{FAMILY}/ui/02/assessment").status_code == 401


def test_cross_family_request_is_rejected(client: TestClient) -> None:
    auth = _auth(client, family=FAMILY)
    assert client.get(f"/families/{OTHER_FAMILY}/ui/02/assessment", headers=auth).status_code == 403


def test_mutation_without_idempotency_key_is_rejected(client: TestClient) -> None:
    """Fails for the stated reason only.

    `subject_person_id` is a real UUID here so the request survives payload
    validation and is rejected by the missing-key check. The previous version
    passed a non-UUID and so never reached that check.
    """
    auth = _auth(client)
    response = client.post(
        f"/families/{FAMILY}/assessments/sessions",
        json={"subject_person_id": str(uuid.uuid4())},
        headers=auth,
    )
    assert response.status_code == 400
    assert "idempotency" in response.text.lower()


def test_malformed_subject_person_id_is_rejected(client: TestClient) -> None:
    """The rejection the old fixture was accidentally relying on, now explicit."""
    auth = _auth(client)
    response = client.post(
        f"/families/{FAMILY}/assessments/sessions",
        json={"subject_person_id": "child-a"},
        headers={**auth, "idempotency-key": "malformed-1"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "valid_subject_person_id_required"
