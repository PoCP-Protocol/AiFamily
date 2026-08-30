"""Composition-root guard for the synthetic account-session endpoints.

The assessment ``dev_auth`` router is intentionally useful in development and
test, but it must not be advertised or reachable from a production app.  Each
test imports a fresh ``main`` module after setting ``AIFAMILY_ENV`` so the
module-level ``app`` cannot retain routes from a previous environment.
"""

from __future__ import annotations

import importlib
import sys

from fastapi.testclient import TestClient


def _fresh_main_module():
    """Reload the composition root after changing its environment."""

    sys.modules.pop("backend.apps.family_api.main", None)
    return importlib.import_module("backend.apps.family_api.main")


def test_production_does_not_mount_or_advertise_dev_auth(monkeypatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    main = _fresh_main_module()
    client = TestClient(main.create_app())

    assert "/auth/account-session" not in client.get("/openapi.json").json()["paths"]
    response = client.post(
        "/auth/account-session",
        json={"external_ref": "arbitrary-account:arbitrary-family"},
        headers={"idempotency-key": "production-must-not-issue"},
    )
    assert response.status_code in {404, 403}


def test_test_environment_keeps_the_same_dev_auth_contract(monkeypatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    main = _fresh_main_module()
    client = TestClient(main.create_app())

    assert "/auth/account-session" in client.get("/openapi.json").json()["paths"]
    response = client.post(
        "/auth/account-session",
        json={"external_ref": "synthetic-account:synthetic-family"},
        headers={"idempotency-key": "test-session-1"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["family_id"] == "synthetic-family"
