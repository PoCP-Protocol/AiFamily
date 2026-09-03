from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.platform.persistence.session import clear_engine_cache
from backend.workflow_worker.main import WorkflowWorkerSettings, build_runtime
from backend.workflow_worker.runtime import WorkerState
from tests.support.postgres import SKIP_REASON, postgres_test_url


@pytest_asyncio.fixture
async def migrated_worker_database() -> AsyncIterator[str]:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    database_name = f"workflow_worker_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"statement_cache_size": 0},
    )
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'create database "{database_name}"'))
        database_url = (
            make_url(admin_url)
            .set(database=database_name)
            .render_as_string(hide_password=False)
        )
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(Path(__file__).resolve().parents[2]),
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        yield database_url
    finally:
        clear_engine_cache()
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    "select pg_terminate_backend(pid) from pg_stat_activity "
                    "where datname=:database and pid<>pg_backend_pid()"
                ),
                {"database": database_name},
            )
            await connection.execute(text(f'drop database if exists "{database_name}"'))
        await admin.dispose()


def _settings(database_url: str, owner: str) -> WorkflowWorkerSettings:
    return WorkflowWorkerSettings(
        database_url=database_url,
        claim_owner=owner,
        poll_interval=timedelta(milliseconds=10),
        batch_limit=10,
        accepted_action_max_polls=2,
        degraded_after_failed_cycles=1,
        activity_timeout=timedelta(seconds=10),
        health_host="127.0.0.1",
        health_port=9082,
    )


@pytest.mark.asyncio
async def test_worker_composition_runs_and_restarts_on_fresh_postgres(
    migrated_worker_database: str,
) -> None:
    first = build_runtime(_settings(migrated_worker_database, "workflow-worker:first"))
    first_outcomes = await first.run_cycle()

    assert all(outcome.succeeded for outcome in first_outcomes)
    assert first.health.state is WorkerState.RUNNING
    assert first.health.ready is True

    clear_engine_cache()
    restarted = build_runtime(
        _settings(migrated_worker_database, "workflow-worker:restarted")
    )
    restarted_outcomes = await restarted.run_cycle()

    assert all(outcome.succeeded for outcome in restarted_outcomes)
    assert restarted.health.cycle_count == 1
    assert {outcome.activity for outcome in restarted_outcomes} == {
        "accepted_named_actions",
        "growth_action_experience_relay",
    }
