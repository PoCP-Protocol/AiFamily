from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.dev_operator_query_wiring import (
    install_dev_operator_query_wiring,
)
from backend.apps.family_api.dev_wiring import reset_dev_state
from backend.apps.family_api.main import create_app
from backend.domains.assessment.api.dev_auth import get_state


@pytest.fixture()
def dev_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    reset_dev_state()
    get_state().tokens.clear()
    get_state().receipts.clear()
    return TestClient(create_app())


def test_dev_query_routes_use_the_same_operator_contract(dev_client: TestClient) -> None:
    session = dev_client.post(
        "/auth/account-session",
        json={"external_ref": "synthetic-operator:synthetic-family"},
        headers={"idempotency-key": "dev-operator-query"},
    )
    assert session.status_code == 200, session.text
    headers = {"Authorization": f"Bearer {session.json()['token']}"}

    operations = dev_client.get(
        "/internal/ai/experience/delivery-attempts/summary", headers=headers
    )
    evaluations = dev_client.get("/internal/ai/evaluations/reports", headers=headers)

    assert operations.status_code == 200
    assert operations.json()["counts"]["PENDING"] == 1
    assert evaluations.status_code == 200
    assert evaluations.json()[0]["case_version"] == "gold.v1"
    assert evaluations.json()[0]["metadata"]["source"] == "synthetic"


def test_dev_query_wiring_refuses_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    with pytest.raises(RuntimeError, match="outside dev/test"):
        install_dev_operator_query_wiring(create_app())
