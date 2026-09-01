"""Real-PostgreSQL lifecycle for canonical understanding scope binding."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url

HEAD_REVISION = "0007_understanding_snapshot"
PARENT = "0005_reviewed_signal"
TABLE_NAME = "assessment_reviewed_understanding_signals"
TENANT_ID = "10000000-0000-4000-8000-000000000001"
FAMILY_ID = "20000000-0000-4000-8000-000000000001"
GUARDIAN_ID = "30000000-0000-4000-8000-000000000001"
SUBJECT_ID = "40000000-0000-4000-8000-000000000001"
SESSION_ID = "60000000-0000-4000-8000-000000000001"


@pytest.fixture
async def throwaway_database_url() -> str:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    db_name = f"understanding_scope_{uuid.uuid4().hex[:12]}"
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


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


async def _seed_prerequisites(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            "INSERT INTO tenants(tenant_id,tenant_ref,display_name,tenant_type) "
            "VALUES (CAST(:tenant AS uuid),'SCOPE-TEST','Scope test','INTERNAL_SANDBOX')"
        ),
        {"tenant": TENANT_ID},
    )
    await connection.execute(
        text("INSERT INTO families(family_id,display_name) VALUES (CAST(:family AS uuid),'Test')"),
        {"family": FAMILY_ID},
    )
    await connection.execute(
        text(
            "INSERT INTO persons(person_id,family_id,person_type,parent_role,display_name) "
            "VALUES (CAST(:guardian AS uuid),CAST(:family AS uuid),'PARENT','GUARDIAN','Adult'),"
            "(CAST(:subject AS uuid),CAST(:family AS uuid),'CHILD',NULL,'Child')"
        ),
        {"guardian": GUARDIAN_ID, "subject": SUBJECT_ID, "family": FAMILY_ID},
    )
    await connection.execute(
        text(
            "INSERT INTO family_assessment_tools("
            "tool_ref,version_no,title,purpose,status,admission_status,schema_ref,item_schema,boundary"
            ") VALUES ('SCOPE_TEST',1,'Scope test','test','ACTIVE','ADMITTED','scope.v1','{}','{}')"
        )
    )
    await connection.execute(
        text(
            "INSERT INTO family_assessment_sessions("
            "assessment_session_id,tenant_id,family_id,subject_person_id,tool_ref,tool_version,"
            "started_by_person_id) VALUES (CAST(:session AS uuid),CAST(:tenant AS uuid),"
            "CAST(:family AS uuid),CAST(:subject AS uuid),'SCOPE_TEST',1,CAST(:guardian AS uuid))"
        ),
        {
            "session": SESSION_ID,
            "tenant": TENANT_ID,
            "family": FAMILY_ID,
            "subject": SUBJECT_ID,
            "guardian": GUARDIAN_ID,
        },
    )


async def _insert_signal(
    connection: AsyncConnection,
    *,
    receipt: str,
    scope: str,
    assessment_session_id: str | None,
    understanding_run_ref: str | None = None,
) -> None:
    await connection.execute(
        text(
            f"INSERT INTO {TABLE_NAME}("
            "reviewed_signal_id,tenant_id,family_id,assessment_session_id,understanding_run_ref,"
            "signal_ref,signal_version,scope_ref,reviewed_draft_ref,draft_version,provenance_ref,"
            "draft_source,output_schema_ref,view_event_ref,human_gate_receipt_ref,effective_status,"
            "reviewed_by_actor_id,reviewed_at,subject_person_id,need_type,goal_text,"
            "required_capability_keys,evidence_refs) VALUES ("
            "gen_random_uuid(),CAST(:tenant AS uuid),CAST(:family AS uuid),CAST(:session AS uuid),"
            ":run_ref,:signal,1,:scope,'draft-1',1,'air-provenance-1','MODEL_GATEWAY',"
            "'family_problem_understanding.v1','view-1',:receipt,'EFFECTIVE',"
            "CAST(:guardian AS uuid),now(),CAST(:subject AS uuid),'COMMUNICATION','Less conflict',"
            "ARRAY['FAMILY_COMMUNICATION'],ARRAY['evidence-1'])"
        ),
        {
            "tenant": TENANT_ID,
            "family": FAMILY_ID,
            "session": assessment_session_id,
            "run_ref": understanding_run_ref,
            "signal": f"signal-{receipt}",
            "scope": scope,
            "receipt": receipt,
            "guardian": GUARDIAN_ID,
            "subject": SUBJECT_ID,
        },
    )


async def _column_evidence(database_url: str) -> tuple[str, str, set[str], set[str]]:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT column_name,is_nullable FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=:table "
                        "AND column_name IN ('assessment_session_id','understanding_run_ref')"
                    ),
                    {"table": TABLE_NAME},
                )
            ).all()
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
            indexes = set(
                (
                    await connection.execute(
                        text(
                            "SELECT indexname FROM pg_indexes WHERE schemaname='public' "
                            "AND tablename=:table"
                        ),
                        {"table": TABLE_NAME},
                    )
                ).scalars()
            )
        nullable = dict(rows)
        return nullable["assessment_session_id"], nullable["understanding_run_ref"], checks, indexes
    finally:
        await engine.dispose()


async def test_upgrade_enforces_exact_scope_xor_and_downgrade_boundary(
    throwaway_database_url: str,
) -> None:
    at_parent = _run_alembic("upgrade", PARENT, database_url=throwaway_database_url)
    assert at_parent.returncode == 0, at_parent.stdout + at_parent.stderr

    engine = create_async_engine(throwaway_database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            await _seed_prerequisites(connection)
        upgrade = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
        assert upgrade.returncode == 0, upgrade.stdout + upgrade.stderr

        assessment_nullable, run_nullable, checks, indexes = await _column_evidence(
            throwaway_database_url
        )
        assert assessment_nullable == "YES"
        assert run_nullable == "YES"
        assert "ck_reviewed_understanding_scope_binding" in checks
        assert "idx_reviewed_understanding_run_timeline" in indexes

        assessment_scope = f"family://{TENANT_ID}/{FAMILY_ID}/assessment"
        problem_scope = f"family://{TENANT_ID}/{FAMILY_ID}/problem-understanding"
        async with engine.begin() as connection:
            await _insert_signal(
                connection,
                receipt="assessment-receipt",
                scope=assessment_scope,
                assessment_session_id=SESSION_ID,
            )
            await _insert_signal(
                connection,
                receipt="problem-receipt",
                scope=problem_scope,
                assessment_session_id=None,
                understanding_run_ref="air-run-1",
            )

        invalid = (
            (
                "cross-family",
                f"family://{TENANT_ID}/{uuid.uuid4()}/problem-understanding",
                None,
                "run",
            ),
            ("unknown", f"family://{TENANT_ID}/{FAMILY_ID}/unknown", None, "run"),
            ("extra", f"{problem_scope}/extra", None, "run"),
            ("problem-with-session", problem_scope, SESSION_ID, "run"),
            ("assessment-with-run", assessment_scope, SESSION_ID, "run"),
            ("problem-without-run", problem_scope, None, None),
        )
        for receipt, scope, session_id, run_ref in invalid:
            with pytest.raises(IntegrityError):
                async with engine.begin() as connection:
                    await _insert_signal(
                        connection,
                        receipt=receipt,
                        scope=scope,
                        assessment_session_id=session_id,
                        understanding_run_ref=run_ref,
                    )

        downgrade = _run_alembic("downgrade", PARENT, database_url=throwaway_database_url)
        assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr
        async with engine.connect() as connection:
            remaining = int(
                await connection.scalar(text(f"SELECT count(*) FROM {TABLE_NAME}")) or 0
            )
            run_column = await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' "
                    "AND table_name=:table AND column_name='understanding_run_ref'"
                ),
                {"table": TABLE_NAME},
            )
        assert remaining == 1
        assert int(run_column or 0) == 0

        reupgrade = _run_alembic("upgrade", "head", database_url=throwaway_database_url)
        assert reupgrade.returncode == 0, reupgrade.stdout + reupgrade.stderr
        assert (
            (_run_alembic("current", database_url=throwaway_database_url).stdout)
            .strip()
            .endswith(f"{HEAD_REVISION} (head)")
        )
    finally:
        await engine.dispose()
