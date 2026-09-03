from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.schema_registry import (
    SchemaAlreadyRegistered,
    SchemaBindingError,
    SchemaPersistenceBase,
    SqlAlchemySchemaRegistry,
)
from tests.intelligence.schema_registry.test_registry import _schema


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(SchemaPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_schema_registry_preserves_lifecycle_and_validation(session_factory) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        registry = SqlAlchemySchemaRegistry(session)
        draft = _schema(status="REVIEW")
        await registry.register(draft)
        published = await registry.transition(
            draft.schema_ref,
            draft.version,
            "PUBLISHED",
            reviewer="reviewer",
            effective_at=now - timedelta(minutes=1),
            change_reason="approved",
        )
    async with session_factory() as session:
        registry = SqlAlchemySchemaRegistry(session)
        resolved = await registry.resolve("assessment_interpretation", "parent_advisor")
        valid = {
            "summary": "A bounded perspective.",
            "evidence_refs": ["evidence:1"],
            "limitations": "Not a diagnosis.",
            "boundary": "hypothesis_not_fact",
        }
        assert (
            await registry.validate(valid, "assessment_interpretation", "parent_advisor")
            == valid
        )

    assert published.version != draft.version
    assert resolved.version == published.version


@pytest.mark.asyncio
async def test_sql_schema_registry_rejects_duplicate_and_ambiguous_versions(
    session_factory,
) -> None:
    async with session_factory() as session, session.begin():
        registry = SqlAlchemySchemaRegistry(session)
        first = _schema()
        second = replace(first, schema_ref="growth_perspective_other")
        await registry.register(first)
        with pytest.raises(SchemaAlreadyRegistered):
            await registry.register(first)
        await registry.register(second)
        with pytest.raises(SchemaBindingError, match="AMBIGUOUS_EFFECTIVE_SCHEMA"):
            await registry.resolve("assessment_interpretation", "parent_advisor")
