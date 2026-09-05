from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.dev_wiring import reset_dev_state
from backend.apps.family_api.main import create_app


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "dev")
    reset_dev_state()


def _auth(client: TestClient, family: str = "family-a") -> dict[str, str]:
    response = client.post(
        "/auth/account-session",
        json={"external_ref": f"guardian-1:{family}"},
        headers={"idempotency-key": f"auth:{family}"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _body(family: str = "family-a") -> dict:
    return {
        "raw_text": "最近每天写作业都很累，想找一个能一起坚持的小方法",
        "statement": "家庭需要一个可持续的学习陪伴方法",
        "desired_outcome": "今晚能完成一个十分钟的共同小行动",
        "source": "FAMILY_EXPRESSED",
        "purpose": "FAMILY_NEED",
        "consent_version": "v1",
        "data_class": "MINOR_PERSONAL_DATA",
        "subject_person_ids": [f"dev-child:{family}"],
    }


def test_create_app_exposes_family_need_vertical_slice() -> None:
    client = TestClient(create_app())
    headers = {**_auth(client), "idempotency-key": "need:1"}
    first = client.post(
        "/families/family-a/needs/signals", json=_body(), headers=headers
    )
    replay = client.post(
        "/families/family-a/needs/signals", json=_body(), headers=headers
    )
    assert first.status_code == 201, first.text
    assert first.json()["need"]["status"] == "CAPTURED"
    assert first.json()["boundary"] == "FAMILY_EXPRESSION_NOT_AI_DIAGNOSIS"
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True


def test_create_app_rejects_cross_family_need_path() -> None:
    client = TestClient(create_app())
    headers = {**_auth(client, "family-a"), "idempotency-key": "need:2"}
    response = client.post(
        "/families/family-b/needs/signals", json=_body("family-b"), headers=headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "family_access_denied"


def test_production_route_keeps_same_contract_but_fails_closed_without_real_wiring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    client = TestClient(create_app())
    response = client.post(
        "/families/family-a/needs/signals",
        json=_body(),
        headers={"idempotency-key": "need:production"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "family_need_actor_not_wired"


def test_create_app_exposes_need_clarification_profile_and_solution_gap() -> None:
    client = TestClient(create_app())
    auth = _auth(client)
    capture_headers = {**auth, "idempotency-key": "need:s1"}
    captured = client.post(
        "/families/family-a/needs/signals", json=_body(), headers=capture_headers
    )
    assert captured.status_code == 201, captured.text
    need = captured.json()["need"]
    need_id = need["need_id"]
    subject = "dev-child:family-a"

    clarify = client.post(
        f"/families/family-a/needs/{need_id}/clarify",
        json={
            "statement": need["statement"],
            "desired_outcome": need["desired_outcome"],
            "expected_version": need["version"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "need:s1:clarify"},
    )
    assert clarify.status_code == 200, clarify.text
    assert clarify.json()["boundary"] == "FAMILY_CONFIRMED_NEED_NOT_AI_DIAGNOSIS"

    profile = client.post(
        f"/families/family-a/needs/{need_id}/profile",
        json={
            "expected_need_version": clarify.json()["need"]["version"],
            "urgency": "SOON",
            "complexity": "SIMPLE",
            "risk_level": "LOW",
            "preferred_shapes": ["SERVICE"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "need:s1:profile"},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["boundary"] == "NEED_PROFILE_NOT_FAMILY_SCORE"

    draft = client.post(
        f"/families/family-a/needs/{need_id}/solution-drafts",
        json={
            "profile_id": profile.json()["profile"]["profile_id"],
            "expected_profile_version": profile.json()["profile"]["version"],
            "shape": "SERVICE",
            "component_refs": [
                {"component_id": "comp-missing", "shape": "SERVICE", "version": "v1"}
            ],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "need:s1:draft"},
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["draft"] is None
    assert draft.json()["resource_gap"]["reason"] == "NO_MATCHING_CAPABILITY"
