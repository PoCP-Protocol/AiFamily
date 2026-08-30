"""Exercise the 0011 binding migration against a disposable PostgreSQL database."""

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


@pytest.fixture
async def throwaway_database_url() -> str:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)

    database_name = f"growth_binding_{uuid.uuid4().hex[:12]}"
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
                    "WHERE datname = :database AND pid <> pg_backend_pid()"
                ),
                {"database": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        await admin.dispose()


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_upgrade_creates_binding_constraints_and_downgrade_removes_it(
    throwaway_database_url: str,
) -> None:
    upgrade = _run_alembic(
        "upgrade", "0011_growth_onboarding_intent", database_url=throwaway_database_url
    )
    assert upgrade.returncode == 0, f"upgrade failed:\n{upgrade.stdout}\n{upgrade.stderr}"

    engine = create_async_engine(throwaway_database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            columns = (
                (
                    await connection.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema='public' AND table_name="
                            "'growth_onboarding_intent_bindings' ORDER BY ordinal_position"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert columns == [
                "binding_id",
                "tenant_family_binding_id",
                "tenant_id",
                "family_id",
                "intent_id",
                "onboarding_id",
                "subject_person_id",
                "created_at",
            ]

            constraints = (
                (
                    await connection.execute(
                        text(
                            "SELECT conname FROM pg_constraint c "
                            "JOIN pg_class r ON r.oid=c.conrelid "
                            "JOIN pg_namespace n ON n.oid=r.relnamespace "
                            "WHERE n.nspname='public' AND r.relname="
                            "'growth_onboarding_intent_bindings'"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert {
                "growth_onboarding_intent_bindings_pkey",
                "uq_growth_binding_tenant_family_intent",
                "uq_growth_binding_tenant_family_onboarding",
                "fk_growth_binding_tenant_family_binding",
                "fk_growth_binding_tenant",
                "fk_growth_binding_family",
                "fk_growth_binding_intent",
                "fk_growth_binding_onboarding",
                "fk_growth_binding_subject_person",
            } <= set(constraints)

            assert (
                await connection.scalar(text("SELECT to_regclass('public.growth_intents')"))
                == "growth_intents"
            )
            assert (
                await connection.scalar(text("SELECT to_regclass('public.tenant_family_bindings')"))
                == "tenant_family_bindings"
            )
    finally:
        await engine.dispose()

    downgrade = _run_alembic(
        "downgrade", "0010_experience_run_interactions", database_url=throwaway_database_url
    )
    assert downgrade.returncode == 0, f"downgrade failed:\n{downgrade.stdout}\n{downgrade.stderr}"

    engine = create_async_engine(throwaway_database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT to_regclass('public.growth_onboarding_intent_bindings')")
                )
                is None
            )
            assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0010_experience_run_interactions"
            )
    finally:
        await engine.dispose()
