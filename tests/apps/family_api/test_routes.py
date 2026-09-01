"""Integration tests for the family_api FastAPI app.

This is the first real FastAPI instance in the repository (R1's first
landing point). We use TestClient rather than an ASGI-async client because
these two endpoints are simple enough that a synchronous test client keeps
the test readable; nothing here depends on async test infrastructure.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.main import create_app
from backend.platform.persistence.session import clear_engine_cache


@pytest.fixture(autouse=True)
def isolated_engine_cache() -> None:
    clear_engine_cache()
    yield
    clear_engine_cache()


def test_health_returns_200_ok() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_200_when_database_is_reachable() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
