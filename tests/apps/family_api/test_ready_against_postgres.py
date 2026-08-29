"""Proves `/ready` is a real database check, on the database production uses.

`test_routes.py::test_ready_returns_200_when_database_is_reachable` already
exercises the endpoint, but against the default in-memory SQLite — where "the
database is reachable" is nearly tautological, since the engine creates it on
connect. That test cannot distinguish "the readiness probe queries a database"
from "the readiness probe returns 200".

This module closes both halves of that gap:

* the positive case runs against real Postgres (gated on
  `AIFAMILY_TEST_DATABASE_URL`, skipped otherwise), so `/ready` is shown to
  complete an actual asyncpg round trip;
* the negative case points `DATABASE_URL` at a Postgres that is not listening
  and asserts a 503. That one needs no database at all and therefore always
  runs — it is the half that actually proves the probe can *fail*, which is the
  only property that makes a readiness probe worth having.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.main import create_app
from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url


def test_ready_returns_200_against_real_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    url = postgres_test_url()
    if url is None:
        pytest.skip(SKIP_REASON)

    monkeypatch.setenv(DATABASE_URL_ENV_VAR, url)
    client = TestClient(create_app())

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_postgres_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A readiness probe that cannot report "not ready" is decoration.

    Port 1 is chosen because nothing legitimately listens there, so the
    connection is refused promptly rather than hanging on a connect timeout.
    """
    monkeypatch.setenv(
        DATABASE_URL_ENV_VAR, "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nonexistent"
    )
    client = TestClient(create_app())

    response = client.get("/ready")

    assert response.status_code == 503
    assert "database not reachable" in response.json()["detail"]
