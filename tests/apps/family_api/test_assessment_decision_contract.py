"""HTTP contract tests for the reviewed-understanding decision boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api import dev_wiring
from backend.apps.family_api.main import create_app
from backend.domains.assessment.application.growth_intent_handoff import (
    ViewedUnderstandingSignal,
)

FAMILY = "family-a"
SUBJECT = "subject-a"
SESSION = "session-a"
SIGNAL = "signal-a"
GATE = "dev-synthetic:human-gate:signal-a"


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "dev")
    dev_wiring.reset_dev_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _auth(
    client: TestClient,
    *,
    account: str = "account-a",
    family: str = FAMILY,
) -> dict[str, str]:
    response = client.post(
        "/auth/account-session",
        json={"external_ref": f"{account}:{family}"},
        headers={"idempotency-key": f"auth:{account}:{family}"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _signal(**changes: Any) -> ViewedUnderstandingSignal:
    base = ViewedUnderstandingSignal(
        tenant_id=FAMILY,
        family_id=FAMILY,
        assessment_session_id=SESSION,
        signal_ref=SIGNAL,
        signal_version=2,
        scope_ref=f"family://{FAMILY}/{FAMILY}/assessment",
        reviewed_draft_ref="draft-a",
        draft_version=3,
        provenance_ref="provenance-a",
        human_gate_receipt_ref=GATE,
        human_gate_effective_status="EFFECTIVE",
        reviewed_by_actor_id="account-a",
        subject_person_id=SUBJECT,
        need_type="PARENT_CHILD_COMMUNICATION",
        goal_text="希望晚饭后的沟通少一点争吵",
        required_capability_keys=("FAMILY_COMMUNICATION",),
        evidence_refs=("assessment-evidence-a",),
    )
    return replace(base, **changes)


def _body(**changes: Any) -> dict[str, Any]:
    signal = _signal()
    body: dict[str, Any] = {
        "assessment_session_id": signal.assessment_session_id,
        "hypothesis_ref": signal.signal_ref,
        "decision_type": "CONFIRM",
        "scope_ref": signal.scope_ref,
        "signal_version": signal.signal_version,
        "reviewed_draft_ref": signal.reviewed_draft_ref,
        "draft_version": signal.draft_version,
        "provenance_ref": signal.provenance_ref,
        "human_gate_receipt_ref": signal.human_gate_receipt_ref,
    }
    body.update(changes)
    return body


def _seed(signal: ViewedUnderstandingSignal | None = None) -> None:
    signal = signal or _signal()
    dev_wiring._assessment_repository.consents.add(
        (signal.family_id, signal.subject_person_id, "ASSESSMENT")
    )
    dev_wiring.seed_reviewed_understanding_signal(signal)


def _decide(
    client: TestClient,
    body: dict[str, Any],
    *,
    auth: dict[str, str] | None = None,
    key: str = "decision-a",
):
    return client.post(
        f"/families/{FAMILY}/growth-hypotheses/decisions",
        json=body,
        headers={**(auth or _auth(client)), "idempotency-key": key},
    )


def test_confirm_binds_seeded_signal_and_growth_replays_once(client: TestClient) -> None:
    _seed()

    first = _decide(client, _body())
    replay = _decide(client, _body())

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert first.json()["signal_ref"] == SIGNAL
    assert first.json()["signal_version"] == 2
    assert first.json()["scope_ref"] == f"family://{FAMILY}/{FAMILY}/assessment"
    assert first.json()["human_gate_receipt_ref"] == GATE
    assert first.json()["intent"]["reviewed_draft_ref"] == "draft-a"
    assert first.json()["intent"]["draft_version"] == 3
    assert first.json()["intent"]["provenance_ref"] == "provenance-a"
    assert first.json()["intent"]["receipt_ref"].startswith("dev-synthetic-receipt:")
    assert first.json()["replayed"] is False
    assert replay.json()["replayed"] is True
    assert dev_wiring._growth_intent_confirmation.call_count == 1
    assert not hasattr(dev_wiring._dev_growth_hypothesis_handler(), "_interpretation")


def test_dismiss_records_no_growth_intent(client: TestClient) -> None:
    _seed()
    response = _decide(client, _body(decision_type="DISMISS"))

    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "NO_ACTION"
    assert response.json()["intent"] is None
    assert dev_wiring._growth_intent_confirmation.call_count == 0


@pytest.mark.parametrize(
    "invalid",
    [
        {"scope_ref": " "},
        {"signal_version": 0},
        {"reviewed_draft_ref": ""},
        {"draft_version": 0},
        {"provenance_ref": " "},
        {"human_gate_receipt_ref": ""},
        {"actor_type": "AI"},
        {"effective_status": "EFFECTIVE"},
        {"tenant_id": "other-tenant"},
        {"family_id": "other-family"},
    ],
)
def test_missing_invalid_or_client_owned_policy_fields_are_422(
    client: TestClient, invalid: dict[str, Any]
) -> None:
    body = _body()
    body.update(invalid)
    assert _decide(client, body).status_code == 422


def test_missing_review_binding_fields_are_422(client: TestClient) -> None:
    assert _decide(client, {"decision_type": "CONFIRM"}).status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"signal_version": 1},
        {"reviewed_draft_ref": "draft-stale"},
        {"draft_version": 2},
        {"provenance_ref": "provenance-stale"},
        {"human_gate_receipt_ref": "dev-synthetic:human-gate:stale"},
    ],
)
def test_stale_or_mismatched_review_binding_is_409(
    client: TestClient, change: dict[str, Any]
) -> None:
    _seed()
    response = _decide(client, _body(**change))
    assert response.status_code == 409, response.text


def test_cross_scope_and_cross_actor_are_403(client: TestClient) -> None:
    _seed()
    assert _decide(client, _body(scope_ref="family://other/other/assessment")).status_code == 403
    other_guardian = _auth(client, account="account-b")
    assert _decide(client, _body(), auth=other_guardian, key="decision-b").status_code == 403


@pytest.mark.parametrize("status", ["REVOKED", "EXPIRED"])
def test_revoked_or_expired_gate_is_403(client: TestClient, status: str) -> None:
    _seed(_signal(human_gate_effective_status=status))
    response = _decide(client, _body())
    assert response.status_code == 403, response.text


def test_consent_withdrawal_blocks_even_an_existing_replay(client: TestClient) -> None:
    _seed()
    first = _decide(client, _body())
    assert first.status_code == 200, first.text

    dev_wiring._assessment_repository.consents.discard((FAMILY, SUBJECT, "ASSESSMENT"))
    replay = _decide(client, _body())

    assert replay.status_code == 403, replay.text
    assert dev_wiring._growth_intent_confirmation.call_count == 1


def test_unseeded_reviewed_signal_is_404(client: TestClient) -> None:
    response = _decide(client, _body())
    assert response.status_code == 404, response.text
