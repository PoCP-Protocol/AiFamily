"""Real HTTP/PostgreSQL evidence for the Assessment -> Guardian Intent flow.

This test deliberately uses the application factory with an explicit
PostgreSQL URL.  The deterministic interpretation adapter is test plumbing;
the evidence being established here is the durable identity, authorization,
repository and restart-readback path.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from backend.apps.family_api.main import create_app
from backend.platform.persistence.session import DATABASE_URL_ENV_VAR, clear_engine_cache
from tests.support.postgres import SKIP_REASON, postgres_test_url

ROOT = Path(__file__).resolve().parents[3]
TENANT = "21000000-0000-4000-8000-000000000001"
FAMILY = "21000000-0000-4000-8000-000000000002"
PARENT = "21000000-0000-4000-8000-000000000003"
CHILD = "21000000-0000-4000-8000-000000000004"
ACCOUNT = "21000000-0000-4000-8000-000000000005"
ACCOUNT_BINDING = "21000000-0000-4000-8000-000000000006"
MEMBERSHIP = "21000000-0000-4000-8000-000000000007"
TENANT_MEMBERSHIP = "21000000-0000-4000-8000-000000000008"
TENANT_FAMILY = "21000000-0000-4000-8000-000000000009"
SESSION = "21000000-0000-4000-8000-000000000010"
CONSENT = "21000000-0000-4000-8000-000000000011"
GROWTH_CONSENT = "21000000-0000-4000-8000-000000000012"
TOKEN = "assessment-http-postgres-token"


def _alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
    )


@pytest.fixture
async def database_url() -> AsyncIterator[str]:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    name = f"assessment_http_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"statement_cache_size": 0},
    )
    created = False
    try:
        try:
            async with admin.connect() as connection:
                await connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        except (OSError, SQLAlchemyError) as error:
            pytest.skip(f"external PostgreSQL unavailable: {type(error).__name__}")
        url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
        result = _alembic(url, "upgrade", "head")
        assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"
        yield url
    finally:
        if created:
            async with admin.connect() as connection:
                await connection.execute(
                    text(
                        "select pg_terminate_backend(pid) from pg_stat_activity "
                        "where datname=:name and pid <> pg_backend_pid()"
                    ),
                    {"name": name},
                )
                await connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        await admin.dispose()


@asynccontextmanager
async def _engine(url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        yield engine
    finally:
        await engine.dispose()


async def _seed(url: str) -> None:
    async with _engine(url) as engine, engine.begin() as connection:
        await connection.execute(
            text(
                "insert into tenants(tenant_id,tenant_ref,display_name,tenant_type,status) "
                "values (cast(:tenant as uuid),'assessment-http','Assessment HTTP',"
                "'DIRECT_CUSTOMER','ACTIVE')"
            ),
            {"tenant": TENANT},
        )
        await connection.execute(
            text(
                "insert into families(family_id,display_name,status) values "
                "(cast(:family as uuid),'Assessment HTTP Family','ACTIVE')"
            ),
            {"family": FAMILY},
        )
        await connection.execute(
            text(
                "insert into persons(person_id,family_id,person_type,parent_role,display_name) "
                "values (cast(:parent as uuid),cast(:family as uuid),'PARENT','GUARDIAN','Parent'),"
                "(cast(:child as uuid),cast(:family as uuid),'CHILD',null,'Child')"
            ),
            {"parent": PARENT, "child": CHILD, "family": FAMILY},
        )
        await connection.execute(
            text(
                "insert into accounts(account_id,external_ref,status) values "
                "(cast(:account as uuid),'assessment-http-account','ACTIVE')"
            ),
            {"account": ACCOUNT},
        )
        await connection.execute(
            text(
                "insert into account_person_bindings(binding_id,account_id,person_id,status) "
                "values (cast(:binding as uuid),cast(:account as uuid),"
                "cast(:parent as uuid),'ACTIVE')"
            ),
            {"binding": ACCOUNT_BINDING, "account": ACCOUNT, "parent": PARENT},
        )
        await connection.execute(
            text(
                "insert into family_memberships(membership_id,family_id,person_id,role,status) "
                "values (cast(:membership as uuid),cast(:family as uuid),cast(:parent as uuid),"
                "'OWNER_GUARDIAN','ACTIVE')"
            ),
            {"membership": MEMBERSHIP, "family": FAMILY, "parent": PARENT},
        )
        await connection.execute(
            text(
                "insert into tenant_account_memberships(tenant_membership_id,tenant_id,account_id,"
                "role,status,valid_from) values (cast(:membership as uuid),cast(:tenant as uuid),"
                "cast(:account as uuid),'TENANT_OWNER','ACTIVE',now())"
            ),
            {"membership": TENANT_MEMBERSHIP, "tenant": TENANT, "account": ACCOUNT},
        )
        await connection.execute(
            text(
                "insert into tenant_family_bindings(tenant_family_binding_id,tenant_id,family_id,"
                "status,effective_from) values (cast(:binding as uuid),cast(:tenant as uuid),"
                "cast(:family as uuid),'ACTIVE',now())"
            ),
            {"binding": TENANT_FAMILY, "tenant": TENANT, "family": FAMILY},
        )
        await connection.execute(
            text(
                "insert into identity_sessions(session_id,token_hash,person_id,family_id,"
                "account_ref,expires_at) values (cast(:session as uuid),:hash,"
                "cast(:parent as uuid),cast(:family as uuid),cast(:account as uuid),"
                "now()+interval '1 hour')"
            ),
            {
                "session": SESSION,
                "hash": hashlib.sha256(TOKEN.encode()).hexdigest(),
                "parent": PARENT,
                "family": FAMILY,
                "account": ACCOUNT,
            },
        )
        await connection.execute(
            text(
                "insert into consents(consent_id,family_id,subject_person_id,guardian_person_id,"
                "purpose,status,policy_version,granted_at,withdrawn_at) values "
                "(cast(:consent as uuid),cast(:family as uuid),cast(:child as uuid),"
                "cast(:parent as uuid),:purpose,'GRANTED',:policy,now(),null)"
            ),
            {
                "consent": CONSENT,
                "family": FAMILY,
                "child": CHILD,
                "parent": PARENT,
                "purpose": "ASSESSMENT",
                "policy": "assessment-http-v1",
            },
        )
        await connection.execute(
            text(
                "insert into consents(consent_id,family_id,subject_person_id,guardian_person_id,"
                "purpose,status,policy_version,granted_at,withdrawn_at) values "
                "(cast(:consent as uuid),cast(:family as uuid),cast(:child as uuid),"
                "cast(:parent as uuid),'GROWTH_TRACKING','GRANTED','growth-http-v1',now(),null)"
            ),
            {
                "consent": GROWTH_CONSENT,
                "family": FAMILY,
                "child": CHILD,
                "parent": PARENT,
            },
        )
        await connection.execute(
            text(
                "insert into tenant_policy_profiles(tenant_id,policy_version,status,allowed_pages) "
                "values (cast(:tenant as uuid),'assessment-http-v1','ACTIVE',cast(:pages as jsonb))"
            ),
            {"tenant": TENANT, "pages": '["UI-01","UI-02","UI-03"]'},
        )


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Idempotency-Key": key,
        "X-Correlation-Id": f"http:{key}",
    }


@pytest.mark.asyncio
async def test_assessment_http_postgres_restart_readback_and_scope(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(database_url)
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, database_url)
    clear_engine_cache()

    app = create_app()
    with TestClient(app) as client:
        headers = _headers("assessment-http")
        ui02 = client.get(f"/families/{FAMILY}/ui/02/assessment", headers=headers)
        assert ui02.status_code == 200, ui02.text
        assert ui02.json()["availability"] == "AVAILABLE"

        started = client.post(
            f"/families/{FAMILY}/assessments/sessions",
            headers=headers,
            json={"subject_person_id": CHILD},
        )
        assert started.status_code == 200, started.text
        session_id = started.json()["session"]["assessment_session_id"]

        response = client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/responses",
            headers=_headers("assessment-response"),
            json={
                "item_ref": "FOCUS",
                "response_type": "SINGLE_CHOICE",
                "response_value": "PARENT_CHILD_COMMUNICATION",
            },
        )
        assert response.status_code == 200, response.text

        submitted = client.post(
            f"/families/{FAMILY}/assessments/sessions/{session_id}/submit",
            headers=_headers("assessment-submit"),
        )
        assert submitted.status_code == 200, submitted.text

        projection = client.get(f"/families/{FAMILY}/ui/03/growth-hypothesis", headers=headers)
        assert projection.status_code == 200, projection.text
        body = projection.json()
        assert body["availability"] == "READY"
        assert body["hypothesis"]["fact_boundary"] == "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS"

        decision = client.post(
            f"/families/{FAMILY}/growth-hypotheses/decisions",
            headers=_headers("assessment-confirm"),
            json={
                "assessment_session_id": session_id,
                "hypothesis_ref": body["hypothesis"]["hypothesis_ref"],
                "decision_type": "CONFIRM",
            },
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["intent"]["boundary"] == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"

        onboarding = client.post(
            f"/families/{FAMILY}/growth/onboardings",
            headers=_headers("assessment-onboarding"),
            json={"intent_id": decision.json()["intent"]["intent_id"]},
        )
        assert onboarding.status_code == 200, onboarding.text
        onboarding_body = onboarding.json()
        assert onboarding_body["created"] is True
        onboarding_id = onboarding_body["onboarding"]["onboarding_id"]

        priority = client.get(
            f"/families/{FAMILY}/growth/onboardings/{onboarding_id}/priority",
            headers=headers,
        )
        assert priority.status_code == 200, priority.text
        assert priority.json()["onboarding_id"] == onboarding_id
        assert priority.json()["boundary"] == "PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS_NOT_SCORE"

        async with _engine(database_url) as engine, engine.begin() as connection:
            before_counts = {
                table: int(
                    await connection.scalar(
                        text(
                            "select count(*) from ai_run_ledger l "
                            "join family_assessment_sessions s "
                            "on cast(s.assessment_session_id as text)="
                            "l.assessment_session_id "
                            "where s.family_id=cast(:family_id as uuid)"
                        )
                        if table == "ai_run_ledger"
                        else text(f"select count(*) from {table} where family_id=:family_id"),
                        {"family_id": FAMILY},
                    )
                )
                for table in (
                    "family_assessment_sessions",
                    "family_growth_hypothesis_decisions",
                    "ai_run_ledger",
                )
            }
            await connection.execute(
                text(
                    "update consents set status='WITHDRAWN', withdrawn_at=now() "
                    "where consent_id=cast(:consent_id as uuid)"
                ),
                {"consent_id": CONSENT},
            )

        withdrawn_projection = client.get(
            f"/families/{FAMILY}/ui/03/growth-hypothesis",
            headers=_headers("assessment-after-withdrawal"),
        )
        assert withdrawn_projection.status_code == 403, withdrawn_projection.text

        async with _engine(database_url) as engine, engine.begin() as connection:
            after_counts = {
                table: int(
                    await connection.scalar(
                        text(
                            "select count(*) from ai_run_ledger l "
                            "join family_assessment_sessions s "
                            "on cast(s.assessment_session_id as text)="
                            "l.assessment_session_id "
                            "where s.family_id=cast(:family_id as uuid)"
                        )
                        if table == "ai_run_ledger"
                        else text(f"select count(*) from {table} where family_id=:family_id"),
                        {"family_id": FAMILY},
                    )
                )
                for table in before_counts
            }
        assert after_counts == before_counts

        cross_family = client.get(
            "/families/21000000-0000-4000-8000-000000000099/ui/03/growth-hypothesis",
            headers=headers,
        )
        # The bearer session is bound to FAMILY.  Asking the trusted identity
        # resolver to authenticate it for another family yields 401 before a
        # route-level family comparison; either way, the cross-family read is
        # fail-closed and leaks no projection.
        assert cross_family.status_code == 401

    clear_engine_cache()
    restarted_app = create_app()
    with TestClient(restarted_app) as restarted:
        withdrawn_readback = restarted.get(
            f"/families/{FAMILY}/ui/03/growth-hypothesis", headers=headers
        )
        assert withdrawn_readback.status_code == 403, withdrawn_readback.text
