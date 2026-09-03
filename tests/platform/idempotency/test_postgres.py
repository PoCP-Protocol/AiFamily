"""Real-PostgreSQL transaction and restart tests for platform idempotency."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from backend.platform.idempotency.keys import IdempotencyKey
from backend.platform.idempotency.postgres import (
    IDEMPOTENCY_METADATA,
    IdempotencyConflictError,
    SqlAlchemyIdempotencyStore,
)
from tests.support.postgres import SKIP_REASON, postgres_test_url


@pytest.fixture
async def postgres_schema() -> AsyncIterator[tuple[str, str]]:
    url = postgres_test_url()
    if url is None:
        pytest.skip(SKIP_REASON)
    schema = f"t_idem_{uuid.uuid4().hex[:12]}"
    bootstrap = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        yield url, schema
    finally:
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await bootstrap.dispose()


def _engine(url: str, schema: str) -> AsyncEngine:
    return create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={
            "statement_cache_size": 0,
            "server_settings": {"search_path": schema},
        },
    )


async def _create_table(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(IDEMPOTENCY_METADATA.create_all)


def _key(tenant_id: str = "tenant-a") -> IdempotencyKey:
    return IdempotencyKey(tenant_id=tenant_id, value="confirm-understanding-1")


async def _reserve(
    session: AsyncSession,
    *,
    key: IdempotencyKey | None = None,
    request_hash: str = "request-v1",
) -> bool:
    return await SqlAlchemyIdempotencyStore().reserve(
        session,
        key=key or _key(),
        action_name="understanding.confirm",
        request_hash=request_hash,
    )


async def test_postgres_reservation_is_tenant_scoped_and_replay_safe(postgres_schema) -> None:
    url, schema = postgres_schema
    engine = _engine(url, schema)
    await _create_table(engine)
    try:
        async with AsyncSession(engine) as session:
            assert await _reserve(session) is True
            await session.commit()
        async with AsyncSession(engine) as session:
            assert await _reserve(session) is False
            assert await _reserve(session, key=_key("tenant-b")) is True
            await session.commit()
    finally:
        await engine.dispose()


async def test_postgres_changed_request_is_rejected(postgres_schema) -> None:
    url, schema = postgres_schema
    engine = _engine(url, schema)
    await _create_table(engine)
    try:
        async with AsyncSession(engine) as session:
            assert await _reserve(session) is True
            await session.commit()
        async with AsyncSession(engine) as session:
            with pytest.raises(
                IdempotencyConflictError,
                match="idempotency_key_reused_with_different_request",
            ):
                await _reserve(session, request_hash="request-v2")
    finally:
        await engine.dispose()


async def test_outer_rollback_removes_reservation(postgres_schema) -> None:
    url, schema = postgres_schema
    engine = _engine(url, schema)
    await _create_table(engine)
    try:
        async with AsyncSession(engine) as session:
            assert await _reserve(session) is True
            await session.rollback()
        async with AsyncSession(engine) as session:
            assert await _reserve(session) is True
            await session.commit()
    finally:
        await engine.dispose()


async def test_reservation_survives_engine_restart(postgres_schema) -> None:
    url, schema = postgres_schema
    first_engine = _engine(url, schema)
    await _create_table(first_engine)
    async with AsyncSession(first_engine) as session:
        assert await _reserve(session) is True
        await session.commit()
    await first_engine.dispose()

    restarted_engine = _engine(url, schema)
    try:
        async with AsyncSession(restarted_engine) as session:
            assert await _reserve(session) is False
    finally:
        await restarted_engine.dispose()
