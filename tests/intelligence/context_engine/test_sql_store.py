from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.intelligence.context_engine.contracts import (
    ContextScope,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.sql_store import (
    AsyncSqlContextBroker,
    ContextPersistenceBase,
)

NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)


def _scope(*, family_id: str = "family-1") -> ContextScope:
    return ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id=family_id,
        subject_ids=("child-1",),
        purpose="family-image-summary",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=DataClass.OPERATIONAL_TEXT,
        locale="zh-CN",
        deletion_ref="delete:1",
        correlation_id="corr:1",
        causation_id="cause:1",
    )


def _observation() -> StateObservation:
    return StateObservation(
        observation_id="observation-1",
        tenant_id="tenant-1",
        family_id="family-1",
        subject_id="child-1",
        dimension="expression",
        observed_value="calm",
        evidence_refs=("media:1",),
        provenance="test",
        observed_at=NOW,
        data_class=DataClass.OPERATIONAL_TEXT,
        purpose="family-image-summary",
        consent_version="consent.v1",
        consent_granted=True,
        deletion_ref="delete:1",
        correlation_id="corr:1",
        causation_id="cause:1",
        expires_at=NOW + timedelta(hours=1),
        retention_policy="test-1h",
    )


@pytest.fixture
async def broker(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'context.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(ContextPersistenceBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield AsyncSqlContextBroker(session_factory)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_context_survives_fresh_session_and_reconstructs_scope(broker) -> None:
    await broker.append(_observation())
    snapshot = await broker.snapshot(scope=_scope(), now=NOW)

    # ``read`` opens a new session internally, modelling a process/request
    # boundary rather than relying on the session that created the snapshot.
    replay = await broker.read(snapshot.snapshot_ref, _scope(), now=NOW)

    assert broker.durability_mode == "DURABLE"
    assert replay.snapshot_ref == snapshot.snapshot_ref
    assert replay.scope == snapshot.scope
    assert replay.observations[0].observation_id == "observation-1"
    assert replay.source_refs == ("media:1",)


@pytest.mark.asyncio
async def test_sql_context_rejects_cross_family_and_expired_snapshot(broker) -> None:
    snapshot = await broker.snapshot(scope=_scope(), now=NOW, snapshot_ttl=timedelta(minutes=1))

    with pytest.raises(ValueError, match="CROSS_FAMILY"):
        await broker.read(snapshot.snapshot_ref, _scope(family_id="family-2"), now=NOW)
    with pytest.raises(ValueError, match="EXPIRED"):
        await broker.read(snapshot.snapshot_ref, _scope(), now=NOW + timedelta(minutes=1))


@pytest.mark.asyncio
async def test_sql_context_delete_scrubs_snapshot_and_observations(broker) -> None:
    await broker.append(_observation())
    snapshot = await broker.snapshot(scope=_scope(), now=NOW)

    assert await broker.delete_subject("tenant-1", "child-1") == 1
    with pytest.raises(ValueError, match="NOT_FOUND"):
        await broker.read(snapshot.snapshot_ref, _scope(), now=NOW)


@pytest.mark.asyncio
async def test_sql_context_duplicate_observation_is_rejected(broker) -> None:
    await broker.append(_observation())

    with pytest.raises(ValueError, match="ALREADY_EXISTS"):
        await broker.append(_observation())
