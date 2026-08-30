"""Acceptance tests for the first-value support-card loop.

The test follows the product promise rather than just checking isolated
handlers: a family submits a small assessment, corrects the perspective,
chooses one bounded action, and later records what happened. Every mutation
must be scoped, replayable, and visible in the existing audit/outbox seam.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api import dev_wiring
from backend.apps.family_api.dev_wiring import reset_dev_state
from backend.apps.family_api.main import create_app

FAMILY = "support-loop-family"


@pytest.fixture(autouse=True)
def _dev_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "dev")
    reset_dev_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/auth/account-session",
        json={"external_ref": f"support-loop-account:{FAMILY}"},
        headers={"idempotency-key": "support-loop-auth"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _seed_catalog() -> str:
    subject_id = str(uuid.uuid4())
    repository = dev_wiring._assessment_repository
    repository.seed_family(FAMILY, FAMILY)
    repository.grant_family_manage_permission(FAMILY, "support-loop-account")
    repository.seed_subject(FAMILY, subject_id, "家庭成员（合成）")
    repository.seed_need_type(
        "PARENT_CHILD_COMMUNICATION",
        "NEED_PARENT_CHILD_COMMUNICATION",
        "亲子沟通支持",
        "先从倾听开始，再一起找一个可尝试的小约定。",
        ["LISTENING_COACH"],
    )
    return subject_id


def _submit_assessment(client: TestClient, auth: dict[str, str]) -> str:
    subject_id = _seed_catalog()
    start = client.post(
        f"/families/{FAMILY}/assessments/sessions",
        json={"subject_person_id": subject_id},
        headers={**auth, "idempotency-key": "support-loop-start"},
    )
    assert start.status_code == 200, start.text
    session_id = start.json()["session"]["assessment_session_id"]
    response = client.post(
        f"/families/{FAMILY}/assessments/sessions/{session_id}/responses",
        json={
            "item_ref": "FOCUS",
            "response_type": "SINGLE_CHOICE",
            "response_value": "PARENT_CHILD_COMMUNICATION",
        },
        headers={**auth, "idempotency-key": "support-loop-focus"},
    )
    assert response.status_code == 200, response.text
    submit = client.post(
        f"/families/{FAMILY}/assessments/sessions/{session_id}/submit",
        json={},
        headers={**auth, "idempotency-key": "support-loop-submit"},
    )
    assert submit.status_code == 200, submit.text
    return session_id


def test_support_card_to_action_and_next_day_checkin(client: TestClient) -> None:
    auth = _auth(client)
    session_id = _submit_assessment(client, auth)

    result = client.get(
        f"/families/{FAMILY}/assessments/results/latest", headers=auth
    )
    assert result.status_code == 200, result.text
    assert result.json()["result"]["assessment_session_id"] == session_id

    feedback = client.post(
        f"/families/{FAMILY}/assessments/support-card/feedback",
        json={
            "assessment_session_id": session_id,
            "feedback_type": "ADD_CONTEXT",
            "supplement_text": "最难的是开始前的五分钟，不是整段作业。",
        },
        headers={**auth, "idempotency-key": "support-loop-feedback"},
    )
    assert feedback.status_code == 200, feedback.text
    assert feedback.json()["boundary"] == "FEEDBACK_REFINES_PERSPECTIVE_NOT_FACT"

    feedback_replay = client.post(
        f"/families/{FAMILY}/assessments/support-card/feedback",
        json={
            "assessment_session_id": session_id,
            "feedback_type": "ADD_CONTEXT",
            "supplement_text": "最难的是开始前的五分钟，不是整段作业。",
        },
        headers={**auth, "idempotency-key": "support-loop-feedback"},
    )
    assert feedback_replay.status_code == 200
    assert feedback_replay.json()["replayed"] is True

    feedback_projection = client.get(
        f"/families/{FAMILY}/assessments/support-card/latest", headers=auth
    )
    assert feedback_projection.status_code == 200, feedback_projection.text
    assert feedback_projection.json()["latest_feedback"]["feedback_type"] == "ADD_CONTEXT"
    assert feedback_projection.json()["small_step"] is None

    step = client.post(
        f"/families/{FAMILY}/assessments/support-card/small-step",
        json={"assessment_session_id": session_id, "action_ref": "TRY_TONIGHT"},
        headers={**auth, "idempotency-key": "support-loop-step"},
    )
    assert step.status_code == 200, step.text
    assert step.json()["small_step"]["available_for_checkin"] == "NEXT_DAY"
    assert step.json()["boundary"] == "FAMILY_CHOSEN_ACTION_NOT_OUTCOME"

    step_projection = client.get(
        f"/families/{FAMILY}/assessments/support-card/latest", headers=auth
    )
    assert step_projection.status_code == 200
    assert step_projection.json()["small_step"]["action_ref"] == "TRY_TONIGHT"

    checkin = client.post(
        f"/families/{FAMILY}/assessments/support-card/checkins",
        json={
            "assessment_session_id": session_id,
            "outcome": "HELPED",
            "note": "开始时少争了一会儿。",
        },
        headers={**auth, "idempotency-key": "support-loop-checkin"},
    )
    assert checkin.status_code == 200, checkin.text
    assert checkin.json()["checkin"]["outcome"] == "HELPED"
    assert checkin.json()["boundary"] == "FAMILY_FEEDBACK_NOT_OUTCOME_PROOF"

    final_projection = client.get(
        f"/families/{FAMILY}/assessments/support-card/latest", headers=auth
    )
    assert final_projection.status_code == 200
    assert final_projection.json()["latest_checkin"]["outcome"] == "HELPED"

    actions = [event["action"] for event in dev_wiring._assessment_repository.audit_log]
    assert "SUBMIT_SUPPORT_CARD_FEEDBACK" in actions
    assert "START_ASSESSMENT_SMALL_STEP" in actions
    assert "RECORD_ASSESSMENT_CHECKIN" in actions
    events = [event["event_name"] for event in dev_wiring._assessment_repository.outbox]
    assert "AssessmentSupportCardFeedbackSubmitted" in events
    assert "AssessmentSmallStepStarted" in events
    assert "AssessmentCheckinRecorded" in events


def test_support_card_mutations_remain_family_scoped(client: TestClient) -> None:
    auth = _auth(client)
    session_id = _submit_assessment(client, auth)
    response = client.post(
        "/families/another-family/assessments/support-card/feedback",
        json={
            "assessment_session_id": session_id,
            "feedback_type": "LIKE",
        },
        headers={**auth, "idempotency-key": "support-loop-cross-family"},
    )
    assert response.status_code == 403


def test_checkin_requires_the_family_to_choose_an_action(client: TestClient) -> None:
    auth = _auth(client)
    session_id = _submit_assessment(client, auth)
    response = client.post(
        f"/families/{FAMILY}/assessments/support-card/checkins",
        json={"assessment_session_id": session_id, "outcome": "NO_CHANGE"},
        headers={**auth, "idempotency-key": "support-loop-checkin-without-step"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "assessment_small_step_not_started"
