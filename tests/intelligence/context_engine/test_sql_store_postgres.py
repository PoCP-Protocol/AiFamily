from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.intelligence.context_engine.sql_store import (
    AsyncSqlContextBroker,
    ContextPersistenceBase,
)
from backend.platform.persistence.session import resolve_test_database_url
from tests.intelligence.context_engine.test_sql_store import _observation, _scope


@pytest.mark.asyncio
async def test_sql_context_postgres_schema_restart_and_delete() -> None:
    database_url = resolve_test_database_url()
    if database_url is None:
        pytest.skip("AIFAMILY_TEST_DATABASE_URL is not set")
    schema = f"ctx_probe_{uuid.uuid4().hex[:12]}"
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET search_path TO "{schema}"'))
            await connection.run_sync(ContextPersistenceBase.metadata.create_all)

        # schema_translate_map keeps every session isolated from the shared
        # public schema used by migration tests and production fixtures.
        probe_engine = engine.execution_options(schema_translate_map={None: schema})
        session_factory = async_sessionmaker(probe_engine, expire_on_commit=False)
        broker = AsyncSqlContextBroker(session_factory)
        scope = _scope()
        await broker.append(_observation())
        snapshot = await broker.snapshot(scope=scope)
        replay = await broker.read(snapshot.snapshot_ref, scope)

        assert replay.snapshot_ref == snapshot.snapshot_ref
        assert replay.observations[0].observation_id == "observation-1"
        assert await broker.delete_subject(scope.tenant_id, scope.subject_ids[0]) == 1
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
