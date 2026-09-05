from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.apps.family_api.main import create_app
from backend.platform.persistence.session import clear_engine_cache
from tests.support.postgres import SKIP_REASON, postgres_test_url


@pytest_asyncio.fixture
async def baselined_database_url() -> AsyncIterator[str]:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    database_name = f"journey_e2e_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'create database "{database_name}"'))
        database_url = (
            make_url(admin_url)
            .set(database=database_name)
            .render_as_string(hide_password=False)
        )
        environment = {**os.environ, "DATABASE_URL": database_url}
        migrated = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(__import__("pathlib").Path(__file__).resolve().parents[3]),
            env=environment,
            capture_output=True,
            text=True,
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


async def _seed(database_url: str) -> tuple[dict[str, str], str]:
    ids = {name: str(uuid.uuid4()) for name in (
        "family", "guardian", "child", "account", "tenant", "onboarding",
        "perspective", "evidence", "profile", "session",
    )}
    token = "journey-e2e-opaque-token"
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            statements = [
                ("insert into families(family_id,display_name) values (:family,'E2E Family')", ids),
                (
                    "insert into persons(person_id,family_id,person_type,parent_role,display_name) "
                    "values (:guardian,:family,'PARENT','MOTHER','Guardian')",
                    ids,
                ),
                (
                    "insert into persons(person_id,family_id,person_type,display_name) "
                    "values (:child,:family,'CHILD','Child')",
                    ids,
                ),
                ("insert into accounts(account_id,status) values (:account,'ACTIVE')", ids),
                (
                    "insert into account_person_bindings(account_id,person_id,status) "
                    "values (:account,:guardian,'ACTIVE')",
                    ids,
                ),
                (
                    "insert into family_memberships(family_id,person_id,role,status,joined_at) "
                    "values (:family,:guardian,'OWNER_GUARDIAN','ACTIVE',now())",
                    ids,
                ),
                (
                    "insert into tenants(tenant_id,tenant_ref,display_name,tenant_type,status) "
                    "values (:tenant,'E2E-TENANT','E2E','INTERNAL_SANDBOX','ACTIVE')",
                    ids,
                ),
                (
                    "insert into tenant_account_memberships(tenant_id,account_id,role,status) "
                    "values (:tenant,:account,'TENANT_OWNER','ACTIVE')",
                    ids,
                ),
                (
                    "insert into tenant_family_bindings(tenant_id,family_id,status,effective_from) "
                    "values (:tenant,:family,'ACTIVE',now())",
                    ids,
                ),
                (
                    "insert into identity_sessions(session_id,token_hash,account_ref,expires_at) "
                    "values (:session,:token_hash,:account,now()+interval '1 hour')",
                    {**ids, "token_hash": hashlib.sha256(token.encode()).hexdigest()},
                ),
                (
                    "insert into growth_journeys("
                    "journey_id,family_id,journey_type,phase,status,started_at) "
                    "values (:onboarding,:family,'PARENT_CHILD_COMMUNICATION_CONFLICT'," 
                    "'ONBOARDING','ACTIVE',now())",
                    ids,
                ),
            ]
            for purpose in ("SERVICE", "ASSESSMENT", "GROWTH_TRACKING"):
                statements.append(
                    (
                        "insert into consents(family_id,subject_person_id,guardian_person_id," 
                        "purpose,status,policy_version,granted_at) values "
                        "(:family,:child,:guardian,:purpose,'GRANTED','E2E-V1',now())",
                        {**ids, "purpose": purpose},
                    )
                )
            statements.extend(
                [
                    (
                        "insert into growth_events("
                        "family_id,event_type,occurred_at,source,payload) "
                        "values (:family,'GrowthOnboardingStarted',now(),'E2E'," 
                        "cast(:payload as jsonb))",
                        {
                            **ids,
                            "payload": (
                                '{"onboarding_id":"' + ids["onboarding"] + '",'
                                '"safety_disposition":{"severity":"LOW",'
                                '"disposition":"NORMAL"}}'
                            ),
                        },
                    ),
                    (
                        "insert into perspectives(perspective_id,family_id,person_id," 
                        "perspective_type,statement,onboarding_id,subject_person_id," 
                        "author_person_id,safety_disposition) values "
                        "(:perspective,:family,:guardian,'PARENT','E2E perspective'," 
                        ":onboarding,:child,:guardian," 
                        "'{\"severity\":\"LOW\",\"disposition\":\"NORMAL\"}'::jsonb)",
                        ids,
                    ),
                    (
                        "insert into evidence_records(evidence_id,family_id,evidence_type,payload," 
                        "perspective_id,source) values "
                        "(:evidence,:family,'STRUCTURED','{}'::jsonb,:perspective,'ASSESSMENT')",
                        ids,
                    ),
                    (
                        "insert into growth_profiles(profile_id,family_id,subject_type," 
                        "subject_ref_id,life_stage_code,strengths,growth_opportunities,confidence," 
                        "version,effective_from,subject_person_id,status,evidence_snapshot," 
                        "confirmed_by_actor_id,confirmed_at) values "
                        "(:profile,:family,'CHILD',cast(:child as text),"
                        "'EARLY_ADOLESCENCE_12_15'," 
                        "'[]'::jsonb,'[]'::jsonb,0.8,1,now(),cast(:child as uuid),'WORKING'," 
                        "cast(:snapshot as jsonb),:guardian,now())",
                        {**ids, "snapshot": '{"evidence_ids":["' + ids["evidence"] + '"]}'},
                    ),
                    (
                        "insert into growth_profile_dimensions(profile_id,dimension_id,state," 
                        "observable_signals,evidence_ids,confidence) values "
                        "(:profile,'R03','DEVELOPING','[]'::jsonb," 
                        "cast(:evidence_ids as jsonb),0.8)",
                        {**ids, "evidence_ids": '["' + ids["evidence"] + '"]'},
                    ),
                ]
            )
            for sql, parameters in statements:
                await connection.execute(text(sql), parameters)
    finally:
        await engine.dispose()
    return ids, token


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_ui04_priority_to_confirmed_journey_over_real_http(
    baselined_database_url: str, monkeypatch
) -> None:
    ids, token = await _seed(baselined_database_url)
    monkeypatch.setenv("DATABASE_URL", baselined_database_url)
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    clear_engine_cache()
    app = create_app()
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/families/{ids['family']}/growth/onboardings/{ids['onboarding']}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        priority = await client.get(f"{base}/priority", headers=headers)
        assert priority.status_code == 200, priority.text
        draft = priority.json()["draft"]

        confirmed_priority = await client.post(
            f"{base}/priority/confirm",
            headers={**headers, "Idempotency-Key": "e2e-priority"},
            json={"draft_id": draft["draft_id"], "decision": "R03"},
        )
        assert confirmed_priority.status_code == 200, confirmed_priority.text
        priority_id = confirmed_priority.json()["priority"]["priority_id"]

        preview = await client.get(f"{base}/plan-preview", headers=headers)
        assert preview.status_code == 200
        assert preview.json()["state"] == "FAMILY_REVIEW"

        created = await client.post(
            f"{base}/journey-plan",
            headers={**headers, "Idempotency-Key": "e2e-plan-create"},
            json={"priority_id": priority_id},
        )
        assert created.status_code == 200, created.text
        plan_id = created.json()["plan"]["plan_id"]

        confirmed = await client.post(
            f"/families/{ids['family']}/growth/journey-plans/{plan_id}/confirm",
            headers={**headers, "Idempotency-Key": "e2e-plan-confirm"},
            json={},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["plan"]["status"] == "ACTIVE"

        service_journey = await client.get(f"{base}/service-journey", headers=headers)
        assert service_journey.status_code == 200, service_journey.text
        assert service_journey.json()["state"] == "READY"
        assert service_journey.json()["source_plan_id"] == plan_id
        assert service_journey.json()["process_summary"]["completed_actions"] == 0
        assert service_journey.json()["process_summary"]["boundary"] == (
            "PROCESS_PROJECTION_NOT_SCORE_OR_OUTCOME"
        )

        replay = await client.post(
            f"{base}/journey-plan",
            headers={**headers, "Idempotency-Key": "e2e-plan-create"},
            json={"priority_id": priority_id},
        )
        assert replay.json() == created.json()
