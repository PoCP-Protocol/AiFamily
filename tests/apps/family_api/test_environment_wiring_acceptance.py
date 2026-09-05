"""P0 acceptance contract for explicit environment selection.

Synthetic account-session issuance is only valid when the process explicitly
opts into a development/test environment.  These tests intentionally remain
red until the current ``dev_wiring`` owner removes its implicit development
default; they must not be skipped or weakened to make the gate green.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


def _fresh_main_module():
    """Rebuild the composition root after changing ``AIFAMILY_ENV``."""

    sys.modules.pop("backend.apps.family_api.main", None)
    return importlib.import_module("backend.apps.family_api.main")


@pytest.mark.parametrize("environment", [None, "prod-eu", "productionish"])
def test_dev_auth_requires_explicit_known_environment(monkeypatch, environment: str | None) -> None:
    if environment is None:
        monkeypatch.delenv("AIFAMILY_ENV", raising=False)
    else:
        monkeypatch.setenv("AIFAMILY_ENV", environment)

    try:
        main = _fresh_main_module()
    except (RuntimeError, ValueError) as error:
        # A composition root may reject an unsafe environment at import/startup
        # instead of constructing a route-less app.  Both are fail-closed; the
        # rejection must identify the environment configuration.
        assert "environment" in str(error).lower() or "aifamily_env" in str(error).lower()
        return
    try:
        dev_enabled = main.is_dev_environment()
    except (RuntimeError, ValueError) as error:
        assert "environment" in str(error).lower() or "aifamily_env" in str(error).lower()
        return
    assert dev_enabled is False
    client = TestClient(main.create_app())

    assert "/auth/account-session" not in client.get("/openapi.json").json()["paths"]
    response = client.post(
        "/auth/account-session",
        json={"external_ref": "arbitrary-account:arbitrary-family"},
        headers={"idempotency-key": "environment-gate"},
    )
    assert response.status_code in {404, 403}
