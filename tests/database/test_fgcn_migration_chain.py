"""Postgres-only upgrade/downgrade coverage for the FGCN/Human Gate chain.

The historical ``alembic_version.version_num`` column is ``varchar(32)``.  A
revision identifier longer than that can run its DDL successfully and still
fail while Alembic stamps the version row, leaving a misleading half-migrated
database.  This test deliberately drives the real Alembic subprocess against
an empty, throwaway Postgres database so both the identifier width and the
actual 0004 -> 0005 -> 0006 path are exercised.

The URL is opt-in through ``AIFAMILY_TEST_DATABASE_URL`` (the shared helper
normalises a bare ``postgresql://`` URL).  There is intentionally no SQLite
fallback: SQLite cannot express the JSONB, partial-index, and Postgres DDL
used by these revisions.
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VERSIONS_DIR = REPO_ROOT / "database" / "migrations" / "versions"
FGCN_CHAIN = (
    "0004_fgcn_p0_persistence",
    "0005_fgcn_assignment_idempotency",
    "0006_ai_human_tasks",
)
FGCN_FILES = (
    "0004_fgcn_p0_persistence.py",
    "0005_fgcn_assignment_request_idempotency.py",
    "0006_ai_human_tasks.py",
)


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    """Run the repository's actual Alembic entry point against one URL."""

    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


async def _scalar(database_url: str, statement: str) -> object:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn:
            return await conn.scalar(text(statement))
    finally:
        await engine.dispose()


@pytest.fixture
async def throwaway_database_url() -> str:
    """Create an empty disposable Postgres database for the chain test."""

    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    if not admin_url.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
        pytest.fail(
            "AIFAMILY_TEST_DATABASE_URL must be a Postgres URL for migration-chain tests; "
            f"got {admin_url!r}"
        )

    db_name = f"fgcn_chain_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"statement_cache_size": 0},
    )
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))

        database_url = make_url(admin_url).set(database=db_name).render_as_string(
            hide_password=False
        )
        yield database_url
    finally:
        async with admin.connect() as conn:
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        await admin.dispose()


def _module_constants(path: pathlib.Path) -> tuple[str, str | None]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value_node = node.value
        else:
            continue
        if name not in {"revision", "down_revision"} or value_node is None:
            continue
        try:
            values[name] = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            continue
    revision = values.get("revision")
    down_revision = values.get("down_revision")
    assert isinstance(revision, str), f"{path.name} must declare a string revision"
    assert down_revision is None or isinstance(down_revision, str)
    return revision, down_revision


def test_fgcn_revision_ids_fit_alembic_version_column() -> None:
    revisions = [_module_constants(VERSIONS_DIR / filename) for filename in FGCN_FILES]
    assert [revision for revision, _ in revisions] == list(FGCN_CHAIN)
    assert all(len(revision) <= 32 for revision, _ in revisions)
    assert [down_revision for _, down_revision in revisions] == [
        "0003_service_booking_additions",
        "0004_fgcn_p0_persistence",
        "0005_fgcn_assignment_idempotency",
    ]


async def test_fgcn_chain_upgrades_and_downgrades_on_postgres(
    throwaway_database_url: str,
) -> None:
    """Prove each new revision stamps and reverses in order on real Postgres."""

    for target in FGCN_CHAIN:
        result = _run_alembic("upgrade", target, database_url=throwaway_database_url)
        assert result.returncode == 0, (
            f"alembic upgrade {target} failed:\n{result.stdout}\n{result.stderr}"
        )
        current = await _scalar(
            throwaway_database_url, "SELECT version_num FROM alembic_version"
        )
        assert current == target

    assert await _scalar(
        throwaway_database_url,
        "SELECT to_regclass('public.uq_task_assignments_source_request')",
    ) == "uq_task_assignments_source_request"
    assert await _scalar(
        throwaway_database_url,
        "SELECT to_regclass('public.ai_human_tasks')",
    ) == "ai_human_tasks"

    down_to_0005 = _run_alembic(
        "downgrade", "0005_fgcn_assignment_idempotency", database_url=throwaway_database_url
    )
    assert down_to_0005.returncode == 0, (
        "alembic downgrade 0006 -> 0005 failed:\n"
        f"{down_to_0005.stdout}\n{down_to_0005.stderr}"
    )
    assert await _scalar(throwaway_database_url, "SELECT version_num FROM alembic_version") == (
        "0005_fgcn_assignment_idempotency"
    )
    assert await _scalar(
        throwaway_database_url,
        "SELECT to_regclass('public.ai_human_tasks')",
    ) is None
    assert await _scalar(
        throwaway_database_url,
        "SELECT to_regclass('public.uq_task_assignments_source_request')",
    ) == "uq_task_assignments_source_request"

    down_to_0004 = _run_alembic(
        "downgrade", "0004_fgcn_p0_persistence", database_url=throwaway_database_url
    )
    assert down_to_0004.returncode == 0, (
        "alembic downgrade 0005 -> 0004 failed:\n"
        f"{down_to_0004.stdout}\n{down_to_0004.stderr}"
    )
    assert await _scalar(throwaway_database_url, "SELECT version_num FROM alembic_version") == (
        "0004_fgcn_p0_persistence"
    )
    assert await _scalar(
        throwaway_database_url,
        "SELECT to_regclass('public.uq_task_assignments_source_request')",
    ) is None
