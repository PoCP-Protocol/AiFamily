from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.apps.family_api.growth_plan_evidence_reader import (
    GrowthPlanEvidenceForbiddenError,
    GrowthPlanEvidenceNotFoundError,
    SqlAlchemyGrowthPlanEvidenceReader,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from tests.apps.family_api.test_journey_onboarding_postgres_e2e import (
    CHILD_ID,
    FAMILY_ID,
    INTENT_ID,
    PARENT_ID,
    TENANT_ID,
    _seed,
)
from tests.support.postgres import SKIP_REASON, postgres_test_url

ROOT = Path(__file__).resolve().parents[3]
ONBOARDING_ID = "71000000-0000-4000-8000-000000000001"
BINDING_ID = "71000000-0000-4000-8000-000000000002"
PRIORITY_ID = "71000000-0000-4000-8000-000000000003"
PROFILE_ID = "71000000-0000-4000-8000-000000000004"


@pytest.fixture
async def database_url() -> AsyncIterator[str]:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    name = f"growth_reader_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
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
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={**__import__("os").environ, "DATABASE_URL": url},
        )
        assert result.returncode == 0, f"alembic failed:\n{result.stdout}\n{result.stderr}"
        await _seed(url)
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
async def _session_factory(database_url: str):
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def _scope(*, family_id: str = FAMILY_ID, subject_id: str = CHILD_ID) -> ContextScope:
    return ContextScope(
        tenant_id=TENANT_ID,
        region_id="CN",
        family_id=family_id,
        subject_ids=(subject_id,),
        purpose="growth_tracking",
        consent_version="consent-v1",
        consent_granted=True,
        data_class=DataClass.MINOR_PERSONAL_DATA,
        locale="zh-CN",
        deletion_ref="deletion:active",
        correlation_id="growth-reader-test",
        causation_id="growth-reader-test",
    )


async def _seed_growth_binding(database_url: str, *, boundary: str) -> None:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "insert into growth_profiles(profile_id,family_id,subject_type,"
                    "subject_ref_id,life_stage_code,strengths,growth_opportunities,"
                    "confidence,version,effective_from,profile_scope,subject_person_id,"
                    "status,basis,evidence_snapshot,policy_version) values("
                    "cast(:profile as uuid),cast(:family as uuid),'CHILD',:subject_ref,"
                    "'EARLY_ADOLESCENCE_12_15','{}'::jsonb,'{}'::jsonb,0.8,1,now(),'FAMILY',"
                    "cast(:subject as uuid),'ACTIVE','{}'::jsonb,'{}'::jsonb,'profile-v1')"
                ),
                {
                    "profile": PROFILE_ID,
                    "family": FAMILY_ID,
                    "subject_ref": CHILD_ID,
                    "subject": CHILD_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into growth_journeys(" 
                    "journey_id,family_id,journey_type,phase,status,started_at,version) "
                    "values (cast(:journey as uuid),cast(:family as uuid),"
                    "'PARENT_CHILD_COMMUNICATION_CONFLICT','ONBOARDING','ACTIVE',now(),1)"
                ),
                {"journey": ONBOARDING_ID, "family": FAMILY_ID},
            )
            await connection.execute(
                text(
                    "insert into family_memberships(membership_id,family_id,person_id,role,status) "
                    "values (gen_random_uuid(),cast(:family as uuid),cast(:subject as uuid),"
                    "'CHILD_SUBJECT','ACTIVE')"
                ),
                {"family": FAMILY_ID, "subject": CHILD_ID},
            )
            await connection.execute(
                text(
                    "insert into growth_onboarding_intent_bindings(" 
                    "binding_id,tenant_family_binding_id,tenant_id,family_id,intent_id," 
                    "onboarding_id,subject_person_id) "
                    "select cast(:binding as uuid),tenant_family_binding_id,tenant_id,family_id,"
                    "cast(:intent as uuid),cast(:journey as uuid),cast(:subject as uuid) "
                    "from tenant_family_bindings where tenant_id=cast(:tenant as uuid) "
                    "and family_id=cast(:family as uuid)"
                ),
                {
                    "binding": BINDING_ID,
                    "intent": INTENT_ID,
                    "journey": ONBOARDING_ID,
                    "subject": CHILD_ID,
                    "tenant": TENANT_ID,
                    "family": FAMILY_ID,
                },
            )
            await connection.execute(
                text(
                    "insert into growth_priorities(" 
                    "priority_id,family_id,subject_person_id,onboarding_id,profile_id," 
                    "dimension_id,rank,confirmed_by_actor_id,confirmed_at,status,version,boundary," 
                    "reason_codes,evidence_refs,policy_version) values(" 
                    "cast(:priority as uuid),cast(:family as uuid),cast(:subject as uuid),"
                    "cast(:journey as uuid),cast(:profile as uuid),'P03',1,:actor,now(),'ACTIVE',1,"
                    ":boundary,'[]'::jsonb,'[]'::jsonb,'M2_104_DETERMINISTIC_V2')"
                ),
                {
                    "priority": PRIORITY_ID,
                    "family": FAMILY_ID,
                    "subject": CHILD_ID,
                    "journey": ONBOARDING_ID,
                    "profile": PROFILE_ID,
                    "actor": PARENT_ID,
                    "boundary": boundary,
                },
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reader_loads_canonical_postgres_binding(database_url: str) -> None:
    await _seed_growth_binding(
        database_url, boundary="PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS"
    )
    async with _session_factory(database_url) as factory:
        evidence = await SqlAlchemyGrowthPlanEvidenceReader(factory, lambda: PARENT_ID).load(
            scope=_scope(), onboarding_id=ONBOARDING_ID
        )
    assert evidence.intent_id == INTENT_ID
    assert evidence.onboarding_id == ONBOARDING_ID
    assert evidence.priority_id == PRIORITY_ID
    assert evidence.confirmed_by_actor_id == PARENT_ID
    assert evidence.priority_confirmed_by_actor_id == PARENT_ID


@pytest.mark.asyncio
async def test_reader_fails_closed_for_unbound_onboarding(database_url: str) -> None:
    await _seed_growth_binding(
        database_url, boundary="PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS"
    )
    async with _session_factory(database_url) as factory:
        with pytest.raises(GrowthPlanEvidenceNotFoundError):
            await SqlAlchemyGrowthPlanEvidenceReader(factory, lambda: PARENT_ID).load(
                scope=_scope(), onboarding_id="71000000-0000-4000-8000-000000000099"
            )


@pytest.mark.asyncio
async def test_reader_rejects_non_growth_tracking_scope(database_url: str) -> None:
    async with _session_factory(database_url) as factory:
        with pytest.raises(GrowthPlanEvidenceForbiddenError):
            await SqlAlchemyGrowthPlanEvidenceReader(factory, lambda: PARENT_ID).load(
                scope=replace(_scope(), purpose="assessment"),
                onboarding_id=ONBOARDING_ID,
            )
