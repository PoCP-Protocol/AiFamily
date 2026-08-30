"""Proves the Alembic baseline actually applies to a real, empty Postgres.

`tests/database/test_baseline_linearisation.py` proves the baseline SQL is the
legacy SQL. This module proves the baseline *runs* — that the replay mechanism
in `0001_legacy_schema_baseline.py` (raw simple-query execution through asyncpg,
which needed a specific escape hatch to handle multi-statement `DO $$` scripts)
works end to end, and that the resulting schema has the object counts a
faithful replay must produce.  Additive revisions are asserted separately so
their tables cannot silently change the historical baseline contract.

Gated on `AIFAMILY_TEST_DATABASE_URL` and skipped otherwise. Each run gets a
throwaway *database* rather than a schema, because `alembic upgrade head`
targets `public` and stamps `alembic_version`: running it inside the shared test
database would leave 151 legacy tables behind for every other test to trip over.

Expected baseline object counts come from an independent measurement, not from
this code: the 62 legacy files were applied to a scratch Postgres 16 with
`psql` (bypassing Alembic entirely) and the catalog was counted.  The head
expectation adds only tables owned by revisions 0002-0008; views and enum types
remain unchanged.  If the concurrent 0009 WIP revision is present, its single
additional table has its own explicit head expectation.  Keeping these two
contracts separate makes schema drift auditable instead of hiding it by
changing the baseline constant.
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
EXPECTED_LEGACY_TABLES = 151
EXPECTED_VIEWS = 7
EXPECTED_ENUM_TYPES = 60

_ALEMBIC_BOOKKEEPING_TABLES = 1

# Additive table owners after the baseline through revision 0008:
# 0002 (audit), 0003 (private check-in), 0006 (Human Gate), 0007 (outbox),
# and 0008 (experience run, event, checkpoint).
EXPECTED_0008_ADDITIVE_TABLES = 7
EXPECTED_BASELINE_COUNTS = {
    "tables": EXPECTED_LEGACY_TABLES + _ALEMBIC_BOOKKEEPING_TABLES,
    "views": EXPECTED_VIEWS,
    "enums": EXPECTED_ENUM_TYPES,
}
EXPECTED_0008_COUNTS = {
    "tables": EXPECTED_BASELINE_COUNTS["tables"] + EXPECTED_0008_ADDITIVE_TABLES,
    "views": EXPECTED_VIEWS,
    "enums": EXPECTED_ENUM_TYPES,
}

# 0009 is a concurrent WIP migration.  It is recognized explicitly when it
# remains in the checkout, but is not silently folded into the 0004-0008
# responsibility boundary.
EXPECTED_HEAD_COUNTS_BY_REVISION = {
    "0008_experience_runs": EXPECTED_0008_COUNTS,
    "0009_ai_model_drafts": {
        "tables": EXPECTED_0008_COUNTS["tables"] + 1,
        "views": EXPECTED_VIEWS,
        "enums": EXPECTED_ENUM_TYPES,
    },
}


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


def _single_head(database_url: str) -> str:
    """Return the one accepted migration head, failing on unknown branches."""

    result = _run_alembic("heads", database_url=database_url)
    assert result.returncode == 0, f"alembic heads failed:\n{result.stdout}\n{result.stderr}"
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"migration graph must have exactly one head, got: {lines!r}"
    head = lines[0].split(maxsplit=1)[0]
    assert head in EXPECTED_HEAD_COUNTS_BY_REVISION, (
        "unknown migration head; update the explicit object-owner map and review the chain: "
        f"{head!r}"
    )
    return head


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


async def test_upgrade_baseline_applies_to_empty_postgres(throwaway_database_url: str) -> None:
    """The historical baseline alone remains exactly 151/7/60 objects."""

    before = await _count_objects(throwaway_database_url)
    assert before == {"tables": 0, "views": 0, "enums": 0}, (
        f"the throwaway database was not empty: {before}"
    )

    result = _run_alembic(
        "upgrade", "0001_legacy_schema_baseline", database_url=throwaway_database_url
    )
    assert result.returncode == 0, (
        "alembic upgrade 0001_legacy_schema_baseline failed:\n"
        f"{result.stdout}\n{result.stderr}"
    )

    after = await _count_objects(throwaway_database_url)
    assert after == EXPECTED_BASELINE_COUNTS, (
        "replayed baseline schema does not match the psql-measured reference: "
        f"{after}"
    )

    current = _run_alembic("current", database_url=throwaway_database_url)
    assert "0001_legacy_schema_baseline" in current.stdout


async def test_upgrade_0008_applies_fgcn_human_gate_additive_revisions(
    throwaway_database_url: str,
) -> None:
    """0004-0008 add seven owned tables without changing views or enums."""

    result = _run_alembic(
        "upgrade", "0008_experience_runs", database_url=throwaway_database_url
    )
    assert result.returncode == 0, (
        "alembic upgrade 0008_experience_runs failed:\n"
        f"{result.stdout}\n{result.stderr}"
    )

    after = await _count_objects(throwaway_database_url)
    assert after == EXPECTED_0008_COUNTS, (
        "0008 schema does not match the baseline plus additive migration object reference: "
        f"{after}"
    )

    current = _run_alembic("current", database_url=throwaway_database_url)
    assert "0008_experience_runs" in current.stdout


async def test_downgrade_then_upgrade_is_repeatable(throwaway_database_url: str) -> None:
    """Guards the failure mode that `DROP SCHEMA public CASCADE` caused.

    The first version of `downgrade()` dropped the whole `public` schema, which
    took `alembic_version` with it; Alembic's very next statement is
    `DELETE FROM alembic_version`, so the downgrade blew up mid-flight and left
    the database in a state no command reported correctly. Asserting a full
    up -> down -> up cycle is what makes that class of bug visible.
    """
    head = _single_head(throwaway_database_url)
    expected_head_counts = EXPECTED_HEAD_COUNTS_BY_REVISION[head]

    up = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    assert up.returncode == 0, f"alembic upgrade head failed:\n{up.stdout}\n{up.stderr}"
    assert await _count_objects(throwaway_database_url) == expected_head_counts
    current = _run_alembic("current", database_url=throwaway_database_url)
    assert head in current.stdout and "(head)" in current.stdout

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
    assert after_up == expected_head_counts
    current_again = _run_alembic("current", database_url=throwaway_database_url)
    assert head in current_again.stdout and "(head)" in current_again.stdout
