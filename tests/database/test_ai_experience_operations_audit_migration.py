"""Real-Postgres contract for the canonical 0037 Context Engine migration."""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect, make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.intelligence.context_engine.sql_store import ContextPersistenceBase
from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VERSIONS_DIR = REPO_ROOT / "database" / "migrations" / "versions"
CHAIN_FILES = (
    "0008_experience_runs.py",
    "0009_ai_model_drafts.py",
    "0010_experience_run_interactions.py",
    "0037_ai_experience_operations_audit.py",
    "0038_product_definition_education_fields.py",
    "0039_competitor_evidence_drafts.py",
    "0040_experience_interaction_evaluation.py",
)
CHAIN = (
    ("0008_experience_runs", "0007_experience_outbox"),
    ("0009_ai_model_drafts", "0008_experience_runs"),
    ("0010_experience_run_interactions", "0009_ai_model_drafts"),
    ("0037_ops_audit", "0010_experience_run_interactions"),
    ("0038_product_definition", "0037_ops_audit"),
    ("0039_competitor_evidence", "0038_product_definition"),
    ("0040_interaction_evaluation", "0039_competitor_evidence"),
)
CONTEXT_TABLES = {
    "ai_context_observations",
    "ai_context_snapshots",
    "ai_context_snapshot_observations",
}


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


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
        if name in {"revision", "down_revision"} and value_node is not None:
            values[name] = ast.literal_eval(value_node)
    revision = values.get("revision")
    down_revision = values.get("down_revision")
    assert isinstance(revision, str)
    assert down_revision is None or isinstance(down_revision, str)
    return revision, down_revision


@pytest.fixture
async def throwaway_database_url() -> str:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    if not admin_url.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
        pytest.fail(f"migration test requires PostgreSQL, got {admin_url!r}")

    database_name = f"ops_audit_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
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


async def _table_names(database_url: str) -> set[str]:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            return set(await connection.run_sync(lambda sync: inspect(sync).get_table_names()))
    finally:
        await engine.dispose()


async def _assert_context_schema_matches_orm(database_url: str) -> None:
    def type_contract(column_type: sa.types.TypeEngine[object]) -> tuple[object, ...]:
        if isinstance(column_type, sa.String):
            return ("string", column_type.length)
        if isinstance(column_type, sa.Text):
            return ("text",)
        if isinstance(column_type, sa.JSON):
            return ("json",)
        if isinstance(column_type, sa.DateTime):
            return ("datetime", column_type.timezone)
        if isinstance(column_type, sa.Boolean):
            return ("boolean",)
        if isinstance(column_type, sa.Integer):
            return ("integer",)
        return (type(column_type).__name__,)

    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:

            def inspect_schema(
                sync_connection: sa.Connection,
            ) -> dict[str, dict[str, tuple[tuple[object, ...], bool]]]:
                inspector = inspect(sync_connection)
                return {
                    table.name: {
                        column["name"]: (
                            type_contract(column["type"]),
                            column["nullable"],
                        )
                        for column in inspector.get_columns(table.name)
                    }
                    for table in ContextPersistenceBase.metadata.sorted_tables
                }

            actual = await connection.run_sync(inspect_schema)
    finally:
        await engine.dispose()

    expected = {
        table.name: {
            column.name: (type_contract(column.type), column.nullable) for column in table.columns
        }
        for table in ContextPersistenceBase.metadata.sorted_tables
    }
    assert actual == expected


def test_revision_chain_is_linear_and_fits_alembic_version_column() -> None:
    revisions = tuple(_module_constants(VERSIONS_DIR / filename) for filename in CHAIN_FILES)
    assert revisions == CHAIN
    assert all(len(revision) <= 32 for revision, _ in revisions)


async def test_upgrade_downgrade_and_reupgrade_on_postgres(
    throwaway_database_url: str,
) -> None:
    heads = _run_alembic("heads", database_url=throwaway_database_url)
    assert heads.returncode == 0, f"alembic heads failed:\n{heads.stdout}\n{heads.stderr}"
    assert heads.stdout.split()[:1] == ["0040_interaction_evaluation"]

    history = _run_alembic("history", database_url=throwaway_database_url)
    assert history.returncode == 0, f"alembic history failed:\n{history.stdout}\n{history.stderr}"
    for revision, down_revision in CHAIN[1:]:
        assert revision in history.stdout
        assert down_revision in history.stdout

    upgrade = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    assert upgrade.returncode == 0, (
        f"alembic upgrade head failed:\n{upgrade.stdout}\n{upgrade.stderr}"
    )
    assert (await _table_names(throwaway_database_url)) >= CONTEXT_TABLES
    await _assert_context_schema_matches_orm(throwaway_database_url)

    downgrade = _run_alembic(
        "downgrade",
        "0010_experience_run_interactions",
        database_url=throwaway_database_url,
    )
    assert downgrade.returncode == 0, (
        f"alembic downgrade 0040 -> 0010 failed:\n{downgrade.stdout}\n{downgrade.stderr}"
    )
    tables_after_downgrade = await _table_names(throwaway_database_url)
    assert CONTEXT_TABLES.isdisjoint(tables_after_downgrade)
    assert {"experience_runs", "experience_run_interactions", "ai_model_drafts"} <= (
        tables_after_downgrade
    )

    reupgrade = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
    assert reupgrade.returncode == 0, (
        f"alembic re-upgrade head failed:\n{reupgrade.stdout}\n{reupgrade.stderr}"
    )
    assert (await _table_names(throwaway_database_url)) >= CONTEXT_TABLES
    await _assert_context_schema_matches_orm(throwaway_database_url)
