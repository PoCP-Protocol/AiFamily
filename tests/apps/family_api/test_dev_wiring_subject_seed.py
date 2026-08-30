"""Acceptance checks for the dev-only synthetic assessment subject."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api import dev_wiring
from backend.apps.family_api.dev_wiring import (
    ENV_VAR,
    DevWiringNotPermittedError,
    install_dev_wiring,
    reset_dev_state,
)
from backend.apps.family_api.main import create_app


@pytest.fixture(autouse=True)
def _dev_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "dev")
    reset_dev_state()


def _authenticated_client() -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app())
    response = client.post(
        "/auth/account-session",
        json={"external_ref": "parent:family-a"},
        headers={"idempotency-key": "subject-seed-session"},
    )
    assert response.status_code == 200, response.text
    return client, {"Authorization": f"Bearer {response.json()['token']}"}


def test_authenticated_dev_family_get_seeds_one_synthetic_consented_child() -> None:
    client, headers = _authenticated_client()

    first = client.get("/families/family-a/ui/02/assessment", headers=headers)
    second = client.get("/families/family-a/ui/02/assessment", headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["availability"] == "AVAILABLE"
    assert len(first.json()["subjects"]) == 1
    assert first.json()["subjects"] == second.json()["subjects"]

    subjects = dev_wiring._assessment_repository.subjects["family-a"]
    assert len(subjects) == 1
    assert subjects[0]["person_id"] == dev_wiring._dev_subject_person_id("family-a")
    assert subjects[0]["data_class"] == "SYNTHETIC"
    assert subjects[0]["fixture_only"] is True
    assert ("family-a", subjects[0]["person_id"], "ASSESSMENT") in (
        dev_wiring._assessment_repository.consents
    )


def test_synthetic_subject_is_isolated_per_family_and_not_client_selected() -> None:
    client, headers = _authenticated_client()
    other_session = client.post(
        "/auth/account-session",
        json={"external_ref": "other-parent:family-b"},
        headers={"idempotency-key": "other-subject-seed-session"},
    )
    assert other_session.status_code == 200, other_session.text
    other_headers = {"Authorization": f"Bearer {other_session.json()['token']}"}

    own = client.get("/families/family-a/ui/02/assessment", headers=headers)
    other = client.get("/families/family-b/ui/02/assessment", headers=other_headers)

    assert own.status_code == 200
    assert other.status_code == 200
    assert own.json()["subjects"][0]["person_id"] != other.json()["subjects"][0]["person_id"]
    assert set(dev_wiring._assessment_repository.subjects) == {"family-a", "family-b"}


def test_dev_wiring_subject_seed_remains_guarded_outside_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "production")

    with pytest.raises(DevWiringNotPermittedError):
        install_dev_wiring(FastAPI())

    assert dev_wiring._assessment_repository.subjects == {}
