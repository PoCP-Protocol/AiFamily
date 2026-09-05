from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.prompt_registry import (
    PromptAlreadyRegistered,
    PromptBindingError,
    PromptPersistenceBase,
    SqlAlchemyPromptRegistry,
)
from tests.intelligence.prompt_registry.test_registry import _prompt


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(PromptPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_prompt_registry_preserves_lifecycle_and_resolution(session_factory) -> None:
    now = datetime.now(UTC)
    async with session_factory() as session, session.begin():
        registry = SqlAlchemyPromptRegistry(session)
        draft = _prompt(status="REVIEW")
        await registry.register(draft)
        published = await registry.transition(
            draft.prompt_ref,
            draft.version,
            "PUBLISHED",
            reviewer="reviewer",
            effective_at=now - timedelta(minutes=1),
            change_reason="approved",
        )
    async with session_factory() as session:
        registry = SqlAlchemyPromptRegistry(session)
        resolved = await registry.resolve(
            "assessment_interpretation", "parent_advisor", at=now
        )
        original = await registry.get(draft.prompt_ref, draft.version)

    assert published.version != draft.version
    assert resolved.version == published.version
    assert original is not None and original.status == "REVIEW"


@pytest.mark.asyncio
async def test_sql_prompt_registry_rejects_duplicate_and_ambiguous_versions(
    session_factory,
) -> None:
    async with session_factory() as session, session.begin():
        registry = SqlAlchemyPromptRegistry(session)
        first = _prompt()
        second = replace(first, prompt_ref="assessment.other")
        await registry.register(first)
        with pytest.raises(PromptAlreadyRegistered):
            await registry.register(first)
        await registry.register(second)
        with pytest.raises(PromptBindingError, match="AMBIGUOUS_EFFECTIVE_PROMPT"):
            await registry.resolve("assessment_interpretation", "parent_advisor")
