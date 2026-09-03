"""Real-PostgreSQL lifecycle tests for revision 0040."""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION = (
    REPO_ROOT / "database" / "migrations" / "versions" / "0040_experience_interaction_evaluation.py"
)
POSTGRES_CONTAINER_ENV_VAR = "AIFAMILY_TEST_POSTGRES_CONTAINER"
REVISION = "0040_interaction_evaluation"
DOWN_REVISION = "0039_competitor_evidence"
CONSTRAINT = "ck_experience_run_interaction_type"


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


def _assert_alembic_ok(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def _module_revisions() -> tuple[str, str]:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"), filename=str(MIGRATION))
    values: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        if node.target.id in {"revision", "down_revision"} and node.value is not None:
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            values[node.target.id] = value
    return values["revision"], values["down_revision"]


@pytest.fixture
async def throwaway_database_url() -> str:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    database_name = f"interaction_eval_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        yield make_url(admin_url).set(database=database_name).render_as_string(hide_password=False)
    finally:
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        await admin.dispose()


async def _execute(database_url: str, statement: str) -> None:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def _scalar(database_url: str, statement: str) -> object:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(statement))
    finally:
        await engine.dispose()


async def _insert_interaction(database_url: str, interaction_type: str) -> None:
    interaction_id = f"interaction-{interaction_type}-{uuid.uuid4().hex[:8]}"
    await _execute(
        database_url,
        "INSERT INTO experience_run_interactions ("
        "tenant_id, run_id, interaction_id, family_id, subject_ids, interaction_type, "
        "payload, fingerprint, idempotency_key, event_sequence, occurred_at"
        ") VALUES ("
        f"'tenant-eval', 'run-eval', '{interaction_id}', 'family-eval', "
        f"'[\"subject-eval\"]'::jsonb, '{interaction_type}', '{{}}'::jsonb, "
        f"'fingerprint-{interaction_id}', 'key-{interaction_id}', "
        "(SELECT COALESCE(MAX(event_sequence), 0) + 1 "
        "FROM experience_run_interactions WHERE tenant_id='tenant-eval' AND run_id='run-eval'), "
        "now())",
    )


def _restart_postgres() -> None:
    container = os.environ.get(POSTGRES_CONTAINER_ENV_VAR, "").strip()
    if not container:
        pytest.skip(f"{POSTGRES_CONTAINER_ENV_VAR} is required for restart evidence")
    restarted = subprocess.run(
        ["docker", "restart", container],
        capture_output=True,
        text=True,
    )
    assert restarted.returncode == 0, restarted.stdout + restarted.stderr
    for _ in range(60):
        ready = subprocess.run(
            ["docker", "exec", container, "pg_isready"],
            capture_output=True,
            text=True,
        )
        if ready.returncode == 0:
            return
        time.sleep(1)
    pytest.fail("PostgreSQL did not recover within 60 seconds")


def test_revision_is_the_single_successor_of_0039() -> None:
    assert _module_revisions() == (REVISION, DOWN_REVISION)
    assert len(REVISION) <= 32


async def test_fresh_upgrade_accepts_evaluation_and_survives_restart(
    throwaway_database_url: str,
) -> None:
    upgrade = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    _assert_alembic_ok(upgrade)
    assert (
        await _scalar(throwaway_database_url, "SELECT version_num FROM alembic_version") == REVISION
    )

    await _insert_interaction(throwaway_database_url, "evaluation")
    _restart_postgres()

    assert (
        await _scalar(
            throwaway_database_url,
            "SELECT count(*) FROM experience_run_interactions WHERE interaction_type='evaluation'",
        )
        == 1
    )
    assert (
        await _scalar(throwaway_database_url, "SELECT version_num FROM alembic_version") == REVISION
    )


async def test_downgrade_without_evaluation_restores_old_constraint(
    throwaway_database_url: str,
) -> None:
    _assert_alembic_ok(_run_alembic("upgrade", "head", database_url=throwaway_database_url))
    await _insert_interaction(throwaway_database_url, "feedback")

    downgrade = _run_alembic("downgrade", DOWN_REVISION, database_url=throwaway_database_url)
    _assert_alembic_ok(downgrade)
    assert (
        await _scalar(throwaway_database_url, "SELECT version_num FROM alembic_version")
        == DOWN_REVISION
    )
    with pytest.raises(IntegrityError, match=CONSTRAINT):
        await _insert_interaction(throwaway_database_url, "evaluation")

    _assert_alembic_ok(_run_alembic("upgrade", "head", database_url=throwaway_database_url))
    await _insert_interaction(throwaway_database_url, "evaluation")


async def test_downgrade_with_evaluation_fails_closed_and_preserves_data(
    throwaway_database_url: str,
) -> None:
    _assert_alembic_ok(_run_alembic("upgrade", "head", database_url=throwaway_database_url))
    await _insert_interaction(throwaway_database_url, "evaluation")

    downgrade = _run_alembic("downgrade", DOWN_REVISION, database_url=throwaway_database_url)
    assert downgrade.returncode != 0
    assert "0040 downgrade refused: evaluation interactions exist" in (
        downgrade.stdout + downgrade.stderr
    )
    assert (
        await _scalar(throwaway_database_url, "SELECT version_num FROM alembic_version") == REVISION
    )
    assert (
        await _scalar(
            throwaway_database_url,
            "SELECT count(*) FROM experience_run_interactions WHERE interaction_type='evaluation'",
        )
        == 1
    )

    await _execute(
        throwaway_database_url,
        "DELETE FROM experience_run_interactions WHERE interaction_type='evaluation'",
    )
    _assert_alembic_ok(
        _run_alembic("downgrade", DOWN_REVISION, database_url=throwaway_database_url)
    )
    _assert_alembic_ok(_run_alembic("upgrade", "head", database_url=throwaway_database_url))
    assert (
        await _scalar(throwaway_database_url, "SELECT version_num FROM alembic_version") == REVISION
    )
