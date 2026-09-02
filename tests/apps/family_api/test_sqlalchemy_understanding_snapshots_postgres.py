"""Real-PostgreSQL contract for immutable understanding snapshot storage."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.apps.family_api.sqlalchemy_understanding_snapshots import (
    SqlAlchemyUnderstandingDraftSnapshots,
)
from backend.intelligence.family_understanding.snapshot import UnderstandingDraftSnapshot
from tests.support.postgres import SKIP_REASON, postgres_test_url

TENANT_ID = "10000000-0000-4000-8000-000000000001"
FAMILY_ID = "20000000-0000-4000-8000-000000000001"
OTHER_FAMILY_ID = "20000000-0000-4000-8000-000000000002"
SUBJECT_ID = "40000000-0000-4000-8000-000000000001"


def snapshot() -> UnderstandingDraftSnapshot:
    return UnderstandingDraftSnapshot(
        tenant_id=TENANT_ID,
        family_id=FAMILY_ID,
        understanding_run_ref="run-1",
        artifact_ref="artifact-1",
        artifact_version=2,
        prior_artifact_ref="artifact-0",
        provenance_ref="air-provenance-1",
        subject_person_id=SUBJECT_ID,
        desired_change="先减少冲突，再一起安排作业和手机使用",
        need_type="PARENT_CHILD_COMMUNICATION",
        required_capability_keys=("FAMILY_COMMUNICATION",),
        evidence_refs=("evidence-1",),
        source_refs=("guardian-input-1",),
        knowledge_refs=("knowledge-1",),
        provider_id="provider-1",
        model="model-1",
        model_version="2026-09-01",
        prompt_version="understanding-v1",
        schema_version="family_problem_understanding.v1",
        context_snapshot_ref="context-1",
        expires_at=datetime.now(UTC) + timedelta(days=21),
    )


@pytest.fixture
async def database_url() -> str:
    url = postgres_test_url()
    if url is None:
        pytest.skip(SKIP_REASON)
    return url


@pytest.fixture
async def prepared_database(database_url: str) -> str:
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM family_understanding_draft_snapshots "
                    "WHERE tenant_id=CAST(:tenant AS uuid)"
                ),
                {"tenant": TENANT_ID},
            )
            await connection.execute(
                text("DELETE FROM persons WHERE person_id=CAST(:subject AS uuid)"),
                {"subject": SUBJECT_ID},
            )
            await connection.execute(
                text(
                    "DELETE FROM families WHERE family_id IN "
                    "(CAST(:family AS uuid),CAST(:other AS uuid))"
                ),
                {"family": FAMILY_ID, "other": OTHER_FAMILY_ID},
            )
            await connection.execute(
                text("DELETE FROM tenants WHERE tenant_id=CAST(:tenant AS uuid)"),
                {"tenant": TENANT_ID},
            )
            await connection.execute(
                text(
                    "INSERT INTO tenants(tenant_id,tenant_ref,display_name,tenant_type) "
                    "VALUES (CAST(:tenant AS uuid),'SNAPSHOT-TEST','Snapshot test',"
                    "'INTERNAL_SANDBOX')"
                ),
                {"tenant": TENANT_ID},
            )
            await connection.execute(
                text(
                    "INSERT INTO families(family_id,display_name) VALUES "
                    "(CAST(:family AS uuid),'Snapshot family'),"
                    "(CAST(:other AS uuid),'Other family')"
                ),
                {"family": FAMILY_ID, "other": OTHER_FAMILY_ID},
            )
            await connection.execute(
                text(
                    "INSERT INTO persons(person_id,family_id,person_type,parent_role,display_name) "
                    "VALUES (CAST(:subject AS uuid),CAST(:family AS uuid),'CHILD',NULL,'Child')"
                ),
                {"subject": SUBJECT_ID, "family": FAMILY_ID},
            )
        yield database_url
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM family_understanding_draft_snapshots "
                    "WHERE tenant_id=CAST(:tenant AS uuid)"
                ),
                {"tenant": TENANT_ID},
            )
            await connection.execute(
                text("DELETE FROM persons WHERE person_id=CAST(:subject AS uuid)"),
                {"subject": SUBJECT_ID},
            )
            await connection.execute(
                text(
                    "DELETE FROM families WHERE family_id IN "
                    "(CAST(:family AS uuid),CAST(:other AS uuid))"
                ),
                {"family": FAMILY_ID, "other": OTHER_FAMILY_ID},
            )
            await connection.execute(
                text("DELETE FROM tenants WHERE tenant_id=CAST(:tenant AS uuid)"),
                {"tenant": TENANT_ID},
            )
        await engine.dispose()


async def test_save_restart_read_and_exact_idempotency(prepared_database: str) -> None:
    value = snapshot()
    engine = create_async_engine(prepared_database, connect_args={"statement_cache_size": 0})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        adapter = SqlAlchemyUnderstandingDraftSnapshots(session)
        await adapter.save(value)
        await adapter.save(value)
        await session.commit()
    await engine.dispose()

    restarted = create_async_engine(prepared_database, connect_args={"statement_cache_size": 0})
    restarted_sessions = async_sessionmaker(restarted, expire_on_commit=False)
    try:
        async with restarted_sessions() as session:
            adapter = SqlAlchemyUnderstandingDraftSnapshots(session)
            assert (
                await adapter.load(
                    tenant_id=TENANT_ID,
                    family_id=FAMILY_ID,
                    artifact_ref=value.artifact_ref,
                    artifact_version=value.artifact_version,
                    provenance_ref=value.provenance_ref,
                )
                == value
            )
            assert (
                await adapter.load(
                    tenant_id=TENANT_ID,
                    family_id=OTHER_FAMILY_ID,
                    artifact_ref=value.artifact_ref,
                    artifact_version=value.artifact_version,
                    provenance_ref=value.provenance_ref,
                )
                is None
            )
    finally:
        await restarted.dispose()


async def test_new_version_expires_prior_draft_but_keeps_history(
    prepared_database: str,
) -> None:
    first = replace(
        snapshot(),
        artifact_ref="artifact-v1",
        artifact_version=1,
        prior_artifact_ref=None,
        provenance_ref="air-provenance-v1",
    )
    second = replace(
        snapshot(),
        artifact_ref="artifact-v2",
        artifact_version=2,
        prior_artifact_ref=first.artifact_ref,
        provenance_ref="air-provenance-v2",
    )
    engine = create_async_engine(prepared_database, connect_args={"statement_cache_size": 0})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            adapter = SqlAlchemyUnderstandingDraftSnapshots(session)
            await adapter.save(first)
            await adapter.save(second)
            await session.commit()

        async with sessions() as session:
            adapter = SqlAlchemyUnderstandingDraftSnapshots(session)
            assert (
                await adapter.load(
                    tenant_id=TENANT_ID,
                    family_id=FAMILY_ID,
                    artifact_ref=first.artifact_ref,
                    artifact_version=first.artifact_version,
                    provenance_ref=first.provenance_ref,
                )
                is None
            )
            assert (
                await adapter.load(
                    tenant_id=TENANT_ID,
                    family_id=FAMILY_ID,
                    artifact_ref=second.artifact_ref,
                    artifact_version=second.artifact_version,
                    provenance_ref=second.provenance_ref,
                )
                == second
            )
            statuses = dict(
                (
                    await session.execute(
                        text(
                            "SELECT artifact_ref,status FROM family_understanding_draft_snapshots "
                            "WHERE tenant_id=:tenant ORDER BY artifact_version"
                        ),
                        {"tenant": UUID(TENANT_ID)},
                    )
                ).all()
            )
            assert statuses == {"artifact-v1": "EXPIRED", "artifact-v2": "DRAFT"}
    finally:
        await engine.dispose()


async def test_changed_replay_conflicts_and_revoked_snapshot_never_resurrects(
    prepared_database: str,
) -> None:
    value = snapshot()
    engine = create_async_engine(prepared_database, connect_args={"statement_cache_size": 0})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            adapter = SqlAlchemyUnderstandingDraftSnapshots(session)
            await adapter.save(value)
            await session.commit()

        async with sessions() as session:
            with pytest.raises(RuntimeError, match="understanding_snapshot_idempotency_conflict"):
                await SqlAlchemyUnderstandingDraftSnapshots(session).save(
                    replace(value, desired_change="tampered")
                )
            await session.rollback()

        async with sessions() as session:
            await session.execute(
                text(
                    "UPDATE family_understanding_draft_snapshots SET status='REVOKED',"
                    "revoked_at=now(),revocation_ref='guardian-withdrawn' "
                    "WHERE tenant_id=:tenant"
                ),
                {"tenant": UUID(TENANT_ID)},
            )
            await session.commit()

        async with sessions() as session:
            adapter = SqlAlchemyUnderstandingDraftSnapshots(session)
            assert (
                await adapter.load(
                    tenant_id=TENANT_ID,
                    family_id=FAMILY_ID,
                    artifact_ref=value.artifact_ref,
                    artifact_version=value.artifact_version,
                    provenance_ref=value.provenance_ref,
                )
                is None
            )
            with pytest.raises(RuntimeError, match="understanding_snapshot_not_effective"):
                await adapter.save(value)
            await session.rollback()
            status = await session.scalar(
                text(
                    "SELECT status FROM family_understanding_draft_snapshots "
                    "WHERE tenant_id=:tenant"
                ),
                {"tenant": UUID(TENANT_ID)},
            )
            assert status == "REVOKED"
    finally:
        await engine.dispose()


async def test_expired_snapshot_is_not_readable(prepared_database: str) -> None:
    value = snapshot()
    engine = create_async_engine(prepared_database, connect_args={"statement_cache_size": 0})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            await SqlAlchemyUnderstandingDraftSnapshots(session).save(value)
            await session.execute(
                text(
                    "UPDATE family_understanding_draft_snapshots "
                    "SET status='EXPIRED',expires_at=now() - interval '1 second'"
                )
            )
            await session.commit()
        async with sessions() as session:
            assert (
                await SqlAlchemyUnderstandingDraftSnapshots(session).load(
                    tenant_id=TENANT_ID,
                    family_id=FAMILY_ID,
                    artifact_ref=value.artifact_ref,
                    artifact_version=value.artifact_version,
                    provenance_ref=value.provenance_ref,
                )
                is None
            )
    finally:
        await engine.dispose()
