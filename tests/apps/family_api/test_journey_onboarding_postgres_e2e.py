"""Real ``family_api`` HTTP evidence for GrowthIntent -> Onboarding.

The application is created through the actual ``family_api.create_app`` root
in production mode and wired to a fresh database upgraded by Alembic.  This
test therefore cannot pass by using the in-memory onboarding fake or a
hand-crafted SQLAlchemy metadata subset.

The PostgreSQL dependency is explicit: without ``AIFAMILY_TEST_DATABASE_URL``
the test is skipped with the setup command, and it never falls back to SQLite.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import NAMESPACE_URL, uuid5

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.apps.family_api.main import create_app
from backend.domains.journey.application.growth_onboarding import (
    StartGrowthOnboardingCommand,
    idempotency_storage_key,
)
from backend.domains.journey.infrastructure import growth_onboarding_postgres
from backend.platform.persistence.session import (
    DATABASE_URL_ENV_VAR,
    clear_engine_cache,
)
from tests.support.postgres import SKIP_REASON, postgres_test_url

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

TENANT_ID = "10000000-0000-4000-8000-000000000001"
FAMILY_ID = "10000000-0000-4000-8000-000000000002"
PARENT_ID = "10000000-0000-4000-8000-000000000003"
CHILD_ID = "10000000-0000-4000-8000-000000000004"
ACCOUNT_ID = "10000000-0000-4000-8000-000000000005"
TENANT_MEMBERSHIP_ID = "10000000-0000-4000-8000-000000000006"
TENANT_FAMILY_BINDING_ID = "10000000-0000-4000-8000-000000000007"
PARENT_ACCOUNT_BINDING_ID = "10000000-0000-4000-8000-000000000008"
PARENT_FAMILY_MEMBERSHIP_ID = "10000000-0000-4000-8000-000000000009"
SESSION_ID = "10000000-0000-4000-8000-000000000010"
INTENT_ID = "10000000-0000-4000-8000-000000000011"
SECOND_INTENT_ID = "10000000-0000-4000-8000-000000000012"
CONSENT_ID = "10000000-0000-4000-8000-000000000013"

PARENT_TOKEN = "postgres-parent-token"
BOUNDARY = "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


async def _scalar(
    database_url: str, statement: str, **params: object
) -> object:
    engine = create_async_engine(
        database_url, connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(statement), params)
    finally:
        await engine.dispose()


async def _execute(database_url: str, statement: str, **params: object) -> None:
    engine = create_async_engine(
        database_url, connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(text(statement), params)
    finally:
        await engine.dispose()


async def _columns(database_url: str, table_name: str) -> set[str]:
    engine = create_async_engine(
        database_url, connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    """
                    select column_name
                    from information_schema.columns
                    where table_schema='public' and table_name=:table_name
                    """
                ),
                {"table_name": table_name},
            )
            return {str(row.column_name) for row in result}
    finally:
        await engine.dispose()


@pytest.fixture
async def disposable_database_url() -> AsyncIterator[str]:
    """Create one migrated database and remove it after the HTTP scenario."""

    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    if not admin_url.startswith(("postgresql://", "postgresql+asyncpg://", "postgres://")):
        pytest.fail(
            "AIFAMILY_TEST_DATABASE_URL must be a PostgreSQL URL; "
            f"got {admin_url!r}"
        )

    database_name = f"family_api_onboarding_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"statement_cache_size": 0},
    )
    created = False
    try:
        try:
            async with admin.connect() as connection:
                await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
            created = True
        except (OSError, SQLAlchemyError) as error:
            pytest.skip(
                "external dependency unavailable: cannot create disposable "
                f"PostgreSQL database ({type(error).__name__}: {error})"
            )

        database_url = make_url(admin_url).set(database=database_name).render_as_string(
            hide_password=False
        )
        result = _run_alembic("upgrade", "head", database_url=database_url)
        assert result.returncode == 0, (
            f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
        )
        yield database_url
    finally:
        if created:
            try:
                async with admin.connect() as connection:
                    await connection.execute(
                        text(
                            "SELECT pg_terminate_backend(pid) "
                            "FROM pg_stat_activity "
                            "WHERE datname=:database_name "
                            "AND pid <> pg_backend_pid()"
                        ),
                        {"database_name": database_name},
                    )
                    await connection.execute(
                        text(f'DROP DATABASE IF EXISTS "{database_name}"')
                    )
            finally:
                await admin.dispose()
        else:
            await admin.dispose()


@asynccontextmanager
async def _open_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        database_url, connect_args={"statement_cache_size": 0}
    )
    try:
        yield engine
    finally:
        await engine.dispose()


async def _seed(database_url: str) -> None:
    """Seed only real canonical tables; no onboarding rows are pre-created."""

    intent_columns = await _columns(database_url, "growth_intents")
    if "boundary" not in intent_columns:
        pytest.fail(
            "schema_gap: HTTP seed needs growth_intents.boundary, but the "
            "complete Alembic chain did not create it"
        )
    consent_columns = await _columns(database_url, "consents")
    required_consent_columns = {
        "family_id",
        "subject_person_id",
        "purpose",
        "status",
        "policy_version",
        "granted_at",
        "withdrawn_at",
    }
    assert required_consent_columns <= consent_columns, (
        "schema_gap: HTTP seed needs the canonical consent columns "
        f"{sorted(required_consent_columns - consent_columns)}; "
        f"current columns={sorted(consent_columns)}"
    )
    assert "tenant_id" not in consent_columns
    assert "expires_at" not in consent_columns
    assert "effective_from" not in consent_columns
    assert "effective_to" not in consent_columns

    async with _open_engine(database_url) as engine, engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into families(family_id,display_name,status) "
                    "values (cast(:family_id as uuid),'Postgres Evidence Family','ACTIVE')"
                ),
                {"family_id": FAMILY_ID},
            )
            await connection.execute(
                text(
                    "insert into persons(person_id,family_id,person_type,parent_role,display_name) "
                    "values "
                    "(cast(:parent_id as uuid),cast(:family_id as uuid),"
                    "'PARENT','GUARDIAN','Parent'),"
                    "(cast(:child_id as uuid),cast(:family_id as uuid),'CHILD',null,'Child')"
                ),
                {"parent_id": PARENT_ID, "child_id": CHILD_ID, "family_id": FAMILY_ID},
            )
            await connection.execute(
                text(
                    "insert into accounts(account_id,external_ref,status) "
                    "values (cast(:account_id as uuid),'postgres-evidence-parent','ACTIVE')"
                ),
                {"account_id": ACCOUNT_ID},
            )
            await connection.execute(
                text(
                    "insert into account_person_bindings(binding_id,account_id,person_id,status) "
                    "values (cast(:binding_id as uuid),cast(:account_id as uuid),"
                    "cast(:person_id as uuid),'ACTIVE')"
                ),
                {
                    "binding_id": PARENT_ACCOUNT_BINDING_ID,
                    "account_id": ACCOUNT_ID,
                    "person_id": PARENT_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into family_memberships(membership_id,family_id,person_id,role,status) "
                    "values (cast(:membership_id as uuid),cast(:family_id as uuid),"
                    "cast(:person_id as uuid),'OWNER_GUARDIAN','ACTIVE')"
                ),
                {
                    "membership_id": PARENT_FAMILY_MEMBERSHIP_ID,
                    "family_id": FAMILY_ID,
                    "person_id": PARENT_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into tenants(tenant_id,tenant_ref,display_name,tenant_type,status) "
                    "values (cast(:tenant_id as uuid),'postgres-evidence-tenant',"
                    "'Postgres Evidence Tenant','DIRECT_CUSTOMER','ACTIVE')"
                ),
                {"tenant_id": TENANT_ID},
            )
            await connection.execute(
                text(
                    "insert into tenant_account_memberships("
                    "tenant_membership_id,tenant_id,account_id,"
                    "role,status,valid_from) values (cast(:membership_id as uuid),"
                    "cast(:tenant_id as uuid),cast(:account_id as uuid),"
                    "'TENANT_OWNER','ACTIVE',now())"
                ),
                {
                    "membership_id": TENANT_MEMBERSHIP_ID,
                    "tenant_id": TENANT_ID,
                    "account_id": ACCOUNT_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into tenant_family_bindings("
                    "tenant_family_binding_id,tenant_id,family_id,"
                    "status,effective_from,effective_to) values (cast(:binding_id as uuid),"
                    "cast(:tenant_id as uuid),cast(:family_id as uuid),'ACTIVE',now(),null)"
                ),
                {
                    "binding_id": TENANT_FAMILY_BINDING_ID,
                    "tenant_id": TENANT_ID,
                    "family_id": FAMILY_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into identity_sessions(session_id,token_hash,person_id,family_id,"
                    "account_ref,expires_at) values (cast(:session_id as uuid),:token_hash,"
                    "cast(:person_id as uuid),cast(:family_id as uuid),cast(:account_id as uuid),"
                    "now()+interval '1 hour')"
                ),
                {
                    "session_id": SESSION_ID,
                    "token_hash": hashlib.sha256(PARENT_TOKEN.encode()).hexdigest(),
                    "person_id": PARENT_ID,
                    "family_id": FAMILY_ID,
                    "account_id": ACCOUNT_ID,
                },
            )
            for intent_id, goal in (
                (INTENT_ID, "先完整听完，再确认彼此听到的内容。"),
                (SECOND_INTENT_ID, "一起约定一个更平静的讨论时间。"),
            ):
                await connection.execute(
                    text(
                        "insert into growth_intents(intent_id,family_id,subject_person_id,"
                        "need_type,goal_text,required_capability_keys,status,confirmed_by,"
                        "confirmed_at,boundary) values (cast(:intent_id as uuid),"
                        "cast(:family_id as uuid),cast(:subject_id as uuid),"
                        "'COMMUNICATION_SUPPORT',"
                        ":goal,cast(:capabilities as text[]),'OPEN',cast(:confirmed_by as uuid),"
                        "now(),:boundary)"
                    ),
                    {
                        "intent_id": intent_id,
                        "family_id": FAMILY_ID,
                        "subject_id": CHILD_ID,
                        "goal": goal,
                        "capabilities": ["CAP_PARENT_CHILD_COMMUNICATION"],
                        "confirmed_by": PARENT_ID,
                        "boundary": BOUNDARY,
                    },
                )
            await connection.execute(
                text(
                    "insert into consents(consent_id,family_id,subject_person_id,"
                    "guardian_person_id,purpose,status,policy_version,granted_at,withdrawn_at) "
                    "values (cast(:consent_id as uuid),cast(:family_id as uuid),"
                    "cast(:subject_id as uuid),cast(:guardian_id as uuid),"
                    "'GROWTH_TRACKING','GRANTED','consent-v1',now(),null)"
                ),
                {
                    "consent_id": CONSENT_ID,
                    "tenant_id": TENANT_ID,
                    "family_id": FAMILY_ID,
                    "subject_id": CHILD_ID,
                    "guardian_id": PARENT_ID,
                },
            )


def _headers(key: str, *, token: str = PARENT_TOKEN) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": key,
        "X-Correlation-Id": f"http:{key}",
    }


def _expected_onboarding_id(intent_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"growth-onboarding:{TENANT_ID}:{FAMILY_ID}:{intent_id}"))


def _stored_idempotency_key(key: str, intent_id: str) -> str:
    return idempotency_storage_key(
        StartGrowthOnboardingCommand(
            tenant_id=TENANT_ID,
            family_id=FAMILY_ID,
            actor_id=PARENT_ID,
            intent_id=intent_id,
            correlation_id=f"http:{key}",
            idempotency_key=key,
        )
    )


async def _assert_counts(
    database_url: str,
    *,
    intent_id: str,
    idempotency_key: str,
) -> tuple[int, int, int, int, int]:
    onboarding_id = _expected_onboarding_id(intent_id)
    return (
        int(
            await _scalar(
                database_url,
                "select count(*) from growth_journeys "
                "where journey_id=cast(:onboarding_id as uuid)",
                onboarding_id=onboarding_id,
            )
        ),
        int(
            await _scalar(
                database_url,
                "select count(*) from growth_onboarding_intent_bindings "
                "where intent_id=cast(:intent_id as uuid)",
                intent_id=intent_id,
            )
        ),
        int(
            await _scalar(
                database_url,
                "select count(*) from idempotency_keys where idempotency_key=:key",
                key=_stored_idempotency_key(idempotency_key, intent_id),
            )
        ),
        int(
            await _scalar(
                database_url,
                "select count(*) from platform_audit_events "
                "where resource_id=:onboarding_id",
                onboarding_id=onboarding_id,
            )
        ),
        int(
            await _scalar(
                database_url,
                "select count(*) from outbox_events where aggregate_id=:onboarding_id",
                onboarding_id=onboarding_id,
            )
        ),
    )


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_production_family_api_onboarding_http_lifecycle_and_restart_readback(
    disposable_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(disposable_database_url)
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)

    app = create_app(growth_onboarding_database_url=disposable_database_url)
    path = f"/families/{FAMILY_ID}/growth/onboardings"
    with TestClient(app, raise_server_exceptions=False) as client:
        success = client.post(
            path,
            headers=_headers("http-success"),
            json={"intent_id": INTENT_ID},
        )
        assert success.status_code == 200, success.text
        success_body = success.json()
        assert success_body["created"] is True
        assert success_body["replayed"] is False
        assert success_body["event"]["event_name"] == "GrowthOnboardingStarted"
        assert success_body["onboarding"]["intent_binding"]["intent_id"] == INTENT_ID

        replay = client.post(
            path,
            headers=_headers("http-success"),
            json={"intent_id": INTENT_ID},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["event"] == success_body["event"]

        unauthorized = client.post(
            path,
            headers={"Idempotency-Key": "http-unauthorized"},
            json={"intent_id": INTENT_ID},
        )
        assert unauthorized.status_code == 401, unauthorized.text
        assert unauthorized.json() == {"detail": "authorization_required"}

        await _execute(
            disposable_database_url,
            "update consents set status='WITHDRAWN',withdrawn_at=now() "
            "where consent_id=cast(:consent_id as uuid)",
            consent_id=CONSENT_ID,
        )
        consent_rejected = client.post(
            path,
            headers=_headers("http-consent-rejected"),
            json={"intent_id": INTENT_ID},
        )
        assert consent_rejected.status_code == 403, consent_rejected.text
        assert consent_rejected.json() == {"detail": "missing_consent:GROWTH_TRACKING"}
        assert await _assert_counts(
            disposable_database_url,
            intent_id=INTENT_ID,
            idempotency_key="http-consent-rejected",
        ) == (1, 1, 0, 1, 1)

        await _execute(
            disposable_database_url,
            "update consents set status='GRANTED',withdrawn_at=null,"
                    "granted_at=now() "
            "where consent_id=cast(:consent_id as uuid)",
            consent_id=CONSENT_ID,
        )

        original_outbox_writer = growth_onboarding_postgres._append_outbox

        async def fail_outbox(*_args: object) -> None:
            raise RuntimeError("evidence_outbox_failure")

        monkeypatch.setattr(growth_onboarding_postgres, "_append_outbox", fail_outbox)
        rollback_app = create_app(growth_onboarding_database_url=disposable_database_url)
        with TestClient(rollback_app, raise_server_exceptions=False) as rollback_client:
            rolled_back = rollback_client.post(
                path,
                headers=_headers("http-rollback"),
                json={"intent_id": SECOND_INTENT_ID},
            )
        monkeypatch.setattr(
            growth_onboarding_postgres, "_append_outbox", original_outbox_writer
        )
        assert rolled_back.status_code == 500, rolled_back.text
        assert await _assert_counts(
            disposable_database_url,
            intent_id=SECOND_INTENT_ID,
            idempotency_key="http-rollback",
        ) == (0, 0, 0, 0, 0)

    clear_engine_cache()
    restarted_app = create_app(growth_onboarding_database_url=disposable_database_url)
    with TestClient(restarted_app, raise_server_exceptions=False) as restarted_client:
        replay_after_restart = restarted_client.post(
            path,
            headers=_headers("http-success"),
            json={"intent_id": INTENT_ID},
        )
        assert replay_after_restart.status_code == 200, replay_after_restart.text
        assert replay_after_restart.json()["replayed"] is True
        assert replay_after_restart.json()["onboarding"]["intent_binding"]["intent_id"] == INTENT_ID

    assert await _assert_counts(
        disposable_database_url,
        intent_id=INTENT_ID,
        idempotency_key="http-success",
    ) == (1, 1, 1, 1, 1)
