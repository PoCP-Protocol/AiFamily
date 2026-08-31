"""Proves the Alembic baseline actually applies to a real, empty Postgres.

`tests/database/test_baseline_linearisation.py` proves the baseline SQL is the
legacy SQL. This module proves the baseline *runs* — that the replay mechanism
in `0001_legacy_schema_baseline.py` (raw simple-query execution through asyncpg,
which needed a specific escape hatch to handle multi-statement `DO $$` scripts)
works end to end, and that the resulting schema has the object counts a
faithful replay must produce.

Gated on `AIFAMILY_TEST_DATABASE_URL` and skipped otherwise. Each run gets a
throwaway *database* rather than a schema, because `alembic upgrade head`
targets `public` and stamps `alembic_version`: running it inside the shared test
database would leave 151 legacy tables behind for every other test to trip over.

Expected object counts come from an independent measurement, not from this code:
the 62 legacy files were applied to a scratch Postgres 16 with `psql` (bypassing
Alembic entirely) and the catalog was counted. If the Alembic path produces
different numbers, the replay mechanism is lossy — which is exactly what this
test exists to catch.
"""

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

# Measured by applying the 62 linearised files with psql on an empty Postgres 16.
# The historical replay creates 151 tables.  Revisions after the replay own
# six additional tables: the platform audit table, the service check-in
# table, and the four Journey MVP tables. Keep this explicit so a new domain
# migration must update the object-count contract rather than silently pass.
EXPECTED_LEGACY_TABLES = 151
EXPECTED_POST_BASELINE_TABLES = 6
EXPECTED_VIEWS = 7
EXPECTED_ENUM_TYPES = 60

_ALEMBIC_BOOKKEEPING_TABLES = 1


@pytest.fixture
async def throwaway_database_url() -> str:
    """Create an empty database, yield its URL, drop it afterwards."""
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)

    db_name = f"alembic_baseline_{uuid.uuid4().hex[:12]}"

    # CREATE/DROP DATABASE cannot run inside a transaction block, hence
    # AUTOCOMMIT rather than the usual `engine.begin()`.
    admin = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        # `str(URL)` masks the password as "***"; the subprocess needs the real
        # one, so render explicitly.
        yield make_url(admin_url).set(database=db_name).render_as_string(hide_password=False)
    finally:
        async with admin.connect() as conn:
            # Terminate leftover sessions first: asyncpg pools can hold a
            # connection open past engine disposal, and DROP DATABASE fails
            # while any session is attached.
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    """Invoke Alembic as a subprocess, exactly as an operator or CI would.

    Calling `alembic.command.upgrade()` in-process would skip `alembic.ini`
    parsing and `env.py` loading — the two places T-03 actually changed, and the
    two places that broke during development (an `alembic.ini` comment with a
    non-ASCII character made `configparser` fail under Windows' GBK locale).
    A subprocess exercises the real entry point.
    """
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


async def _count_objects(database_url: str) -> dict[str, int]:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn:
            tables = await conn.scalar(
                text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
            )
            views = await conn.scalar(
                text("SELECT count(*) FROM information_schema.views WHERE table_schema = 'public'")
            )
            enums = await conn.scalar(
                text(
                    "SELECT count(DISTINCT t.typname) FROM pg_type t "
                    "JOIN pg_enum e ON e.enumtypid = t.oid "
                    "JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = 'public'"
                )
            )
        return {"tables": tables or 0, "views": views or 0, "enums": enums or 0}
    finally:
        await engine.dispose()


async def test_upgrade_head_applies_to_empty_postgres(throwaway_database_url: str) -> None:
    before = await _count_objects(throwaway_database_url)
    assert before == {"tables": 0, "views": 0, "enums": 0}, (
        f"the throwaway database was not empty: {before}"
    )

    result = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"

    after = await _count_objects(throwaway_database_url)
    assert after == {
        "tables": EXPECTED_LEGACY_TABLES
        + EXPECTED_POST_BASELINE_TABLES
        + _ALEMBIC_BOOKKEEPING_TABLES,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    }, f"replayed schema does not match the psql-measured reference: {after}"

    current = _run_alembic("current", database_url=throwaway_database_url)
    assert "0004_journey_mvp_persistence" in current.stdout
    assert "(head)" in current.stdout


async def test_downgrade_then_upgrade_is_repeatable(throwaway_database_url: str) -> None:
    """Guards the failure mode that `DROP SCHEMA public CASCADE` caused.

    The first version of `downgrade()` dropped the whole `public` schema, which
    took `alembic_version` with it; Alembic's very next statement is
    `DELETE FROM alembic_version`, so the downgrade blew up mid-flight and left
    the database in a state no command reported correctly. Asserting a full
    up -> down -> up cycle is what makes that class of bug visible.
    """
    assert _run_alembic("upgrade", "head", database_url=throwaway_database_url).returncode == 0

    down = _run_alembic("downgrade", "base", database_url=throwaway_database_url)
    assert down.returncode == 0, f"alembic downgrade base failed:\n{down.stdout}\n{down.stderr}"

    after_down = await _count_objects(throwaway_database_url)
    assert after_down == {"tables": _ALEMBIC_BOOKKEEPING_TABLES, "views": 0, "enums": 0}, (
        "downgrade must remove every legacy object but keep Alembic's own "
        f"version table: {after_down}"
    )

    up_again = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    assert up_again.returncode == 0, f"re-upgrade failed:\n{up_again.stdout}\n{up_again.stderr}"

    after_up = await _count_objects(throwaway_database_url)
    assert (
        after_up["tables"]
        == EXPECTED_LEGACY_TABLES + EXPECTED_POST_BASELINE_TABLES + _ALEMBIC_BOOKKEEPING_TABLES
    )
