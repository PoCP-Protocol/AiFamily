"""Real-PostgreSQL lifecycle for immutable understanding snapshots."""

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

REVISION = "0007_understanding_snapshot"
PARENT = "0006_understanding_scope_binding"
TABLE_NAME = "family_understanding_draft_snapshots"


@pytest.fixture
async def throwaway_database_url() -> str:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    db_name = f"understanding_snapshot_{uuid.uuid4().hex[:10]}"
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
                    "WHERE datname=:name AND pid <> pg_backend_pid()"
                ),
                {"name": db_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


async def _exists(database_url: str) -> bool:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("SELECT to_regclass(:name)"), {"name": f"public.{TABLE_NAME}"}
                )
            )
    finally:
        await engine.dispose()


async def test_snapshot_upgrade_downgrade_and_reupgrade(throwaway_database_url: str) -> None:
    parent = _alembic("upgrade", PARENT, database_url=throwaway_database_url)
    assert parent.returncode == 0, parent.stdout + parent.stderr
    assert not await _exists(throwaway_database_url)

    upgrade = _alembic("upgrade", "head", database_url=throwaway_database_url)
    assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr
    assert await _exists(throwaway_database_url)

    engine = create_async_engine(throwaway_database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            columns = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT column_name,is_nullable FROM information_schema.columns "
                            "WHERE table_schema='public' AND table_name=:table"
                        ),
                        {"table": TABLE_NAME},
                    )
                ).all()
            )
            checks = set(
                (
                    await connection.execute(
                        text(
                            "SELECT constraint_name FROM information_schema.table_constraints "
                            "WHERE table_schema='public' AND table_name=:table "
                            "AND constraint_type='CHECK'"
                        ),
                        {"table": TABLE_NAME},
                    )
                ).scalars()
            )
        assert columns["understanding_run_ref"] == "NO"
        assert columns["provenance_ref"] == "NO"
        assert columns["expires_at"] == "NO"
        assert {
            "ck_understanding_snapshot_nonempty_refs",
            "ck_understanding_snapshot_required_refs",
            "ck_understanding_snapshot_revocation",
        } <= checks
    finally:
        await engine.dispose()

    current = _alembic("current", database_url=throwaway_database_url)
    assert current.returncode == 0, current.stdout + current.stderr
    assert f"{REVISION} (head)" in current.stdout

    downgrade = _alembic("downgrade", PARENT, database_url=throwaway_database_url)
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
    assert not await _exists(throwaway_database_url)

    reupgrade = _alembic("upgrade", "head", database_url=throwaway_database_url)
    assert reupgrade.returncode == 0, reupgrade.stdout + reupgrade.stderr
    assert await _exists(throwaway_database_url)
