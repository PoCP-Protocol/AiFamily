from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.experience_operations_query_wiring import (
    build_production_experience_operations_audit_sink,
    build_sql_experience_operations_audit_sink,
)
from backend.intelligence.experience.operations_audit_persistence import (
    ExperienceOperationsAuditPersistenceBase,
    ExperienceOperationsAuditPersistenceError,
    SqlAlchemyExperienceOperationsAuditSessionSink,
    SqlAlchemyExperienceOperationsAuditSink,
)
from backend.intelligence.experience.operations_query import ExperienceOperationsAuditEvent


def test_operations_audit_migration_is_linear_and_revision_fits_storage_limit() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    migration = run_path(
        str(repo_root / "database/migrations/versions/0037_ai_experience_operations_audit.py")
    )

    assert migration["revision"] == "0037_ops_audit"
    assert migration["down_revision"] == "0036_ai_context_engine"
    assert len(migration["revision"]) <= 32


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperienceOperationsAuditPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _event(*, outcome: str = "ALLOWED") -> ExperienceOperationsAuditEvent:
    return ExperienceOperationsAuditEvent(
        operator_id="operator-1",
        authorization_ref="authz-1",
        environment="production",
        operation="summary",
        outcome=outcome,
        occurred_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_sql_operations_audit_sink_round_trips_and_flushes_only(session_factory) -> None:
    async with session_factory() as session:
        sink = SqlAlchemyExperienceOperationsAuditSink(
            session, event_id_factory=lambda: "event-1"
        )
        await sink.record(_event())
        rows = await sink.list_events()
        assert rows == (_event(),)
        await session.commit()


@pytest.mark.asyncio
async def test_sql_operations_audit_sink_filters_metadata(session_factory) -> None:
    async with session_factory() as session:
        sink = SqlAlchemyExperienceOperationsAuditSink(session)
        await sink.record(_event())
        await sink.record(_event(outcome="DENIED"))

        assert len(await sink.list_events(operator_id="operator-1", environment="production")) == 2
        assert await sink.list_events(operator_id="other") == ()


@pytest.mark.asyncio
async def test_sql_operations_audit_sink_rejects_sensitive_or_invalid_metadata(
    session_factory,
) -> None:
    async with session_factory() as session:
        sink = SqlAlchemyExperienceOperationsAuditSink(session)
        with pytest.raises(ExperienceOperationsAuditPersistenceError, match="OUTCOME_INVALID"):
            await sink.record(_event(outcome="PAYLOAD:" + "secret"))

        naive = _event()
        object.__setattr__(naive, "occurred_at", datetime(2026, 8, 30, 12))
        with pytest.raises(
            ExperienceOperationsAuditPersistenceError,
            match="TIMESTAMP_TIMEZONE_REQUIRED",
        ):
            await sink.record(naive)


@pytest.mark.asyncio
async def test_sql_operations_audit_sink_bounds_reads(session_factory) -> None:
    async with session_factory() as session:
        sink = SqlAlchemyExperienceOperationsAuditSink(session)
        with pytest.raises(ExperienceOperationsAuditPersistenceError, match="LIMIT_INVALID"):
            await sink.list_events(limit=0)
        with pytest.raises(ExperienceOperationsAuditPersistenceError, match="LIMIT_INVALID"):
            await sink.list_events(limit=1001)


@pytest.mark.asyncio
async def test_composition_helper_requires_caller_owned_async_session(session_factory) -> None:
    async with session_factory() as session:
        assert isinstance(
            build_sql_experience_operations_audit_sink(session),
            SqlAlchemyExperienceOperationsAuditSink,
        )
    with pytest.raises(TypeError, match="requires AsyncSession"):
        build_sql_experience_operations_audit_sink(object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_production_audit_sink_commits_access_before_query_returns(session_factory) -> None:
    sink = build_production_experience_operations_audit_sink(session_factory)
    assert isinstance(sink, SqlAlchemyExperienceOperationsAuditSessionSink)

    await sink.record(_event(outcome="DENIED"))

    async with session_factory() as session:
        rows = await SqlAlchemyExperienceOperationsAuditSink(session).list_events()
    assert rows == (_event(outcome="DENIED"),)

    with pytest.raises(TypeError, match="session factory is required"):
        build_production_experience_operations_audit_sink(object())  # type: ignore[arg-type]
