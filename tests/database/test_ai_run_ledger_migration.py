"""Real-PostgreSQL contract test for the canonical AI run ledger revision."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url

HEAD_REVISION = "0007_understanding_snapshot"


@pytest.fixture
async def throwaway_database_url() -> str:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)

    db_name = f"ai_run_ledger_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{db_name}"'))
        yield make_url(admin_url).set(database=db_name).render_as_string(hide_password=False)
    finally:
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": db_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


async def _relation_exists(database_url: str) -> bool:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            return bool(await connection.scalar(text("SELECT to_regclass('ai_run_ledger')")))
    finally:
        await engine.dispose()


async def test_upgrade_downgrade_and_reupgrade_ai_run_ledger(
    throwaway_database_url: str,
) -> None:
    at_parent = _run_alembic(
        "upgrade", "0003_service_booking_additions", database_url=throwaway_database_url
    )
    assert at_parent.returncode == 0, at_parent.stdout + at_parent.stderr
    assert not await _relation_exists(throwaway_database_url)

    upgrade = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    assert await _relation_exists(throwaway_database_url)

    current = _run_alembic("current", database_url=throwaway_database_url)
    assert current.returncode == 0, current.stdout + current.stderr
    assert f"{HEAD_REVISION} (head)" in current.stdout

    downgrade = _run_alembic(
        "downgrade", "0003_service_booking_additions", database_url=throwaway_database_url
    )
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    assert not await _relation_exists(throwaway_database_url)

    reupgrade = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    assert reupgrade.returncode == 0, reupgrade.stdout + reupgrade.stderr
    assert await _relation_exists(throwaway_database_url)
