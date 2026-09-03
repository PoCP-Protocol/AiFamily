from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.achievement import AchievementEngine, AchievementKey
from backend.intelligence.experience.achievement_consumer import ExperienceAchievementConsumer
from backend.intelligence.experience.achievement_persistence import (
    AchievementProjectionConflict,
    AchievementProjectionRow,
    SqlAlchemyAchievementProjection,
)
from backend.intelligence.experience.contracts import ExperienceEventType
from backend.intelligence.experience.persistence import (
    ExperiencePersistenceBase,
    SqlAlchemyExperienceOutbox,
)
from backend.intelligence.experience.pipeline import ExperienceOutboxMessage

from .test_gateway import _event


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExperiencePersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_projection_survives_new_session_and_preserves_evidence(session_factory) -> None:
    event = _event(
        event_id="durable-achievement",
        event_type=ExperienceEventType.ACTION_COMPLETED,
        occurred_at=datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
    )
    achievement = AchievementEngine().apply(event)[0]

    async with session_factory() as session:
        async with session.begin():
            projection = SqlAlchemyAchievementProjection(session)
            persisted = await projection.append(achievement)
        assert persisted == achievement

    async with session_factory() as session:
        projection = SqlAlchemyAchievementProjection(session)
        earned = await projection.earned(event.scope)
        assert tuple(item.key for item in earned) == (AchievementKey.FIRST_STEP,)
        assert earned[0].evidence_refs == ("experience-event:durable-achievement",)
        assert earned[0].provenance == event.provenance
        assert earned[0].earned_at == event.occurred_at


@pytest.mark.asyncio
async def test_scope_key_replay_returns_first_row_and_conflict_fails_closed(
    session_factory,
) -> None:
    event = _event(event_id="projection-replay", event_type=ExperienceEventType.ACTION_COMPLETED)
    achievement = AchievementEngine().apply(event)[0]
    changed = achievement.__class__(
        achievement_id=achievement.achievement_id,
        key=achievement.key,
        title=achievement.title,
        message=achievement.message,
        scope=achievement.scope,
        evidence_refs=("experience-event:different",),
        provenance=achievement.provenance,
        idempotency_key=achievement.idempotency_key,
        earned_at=datetime(2026, 8, 31, tzinfo=UTC),
    )

    async with session_factory() as session, session.begin():
        projection = SqlAlchemyAchievementProjection(session)
        first = await projection.append(achievement)
        replay = await projection.append(achievement)
        assert replay == first
        with pytest.raises(AchievementProjectionConflict, match="ACHIEVEMENT_REPLAY_MISMATCH"):
            await projection.append(changed)


@pytest.mark.asyncio
async def test_projection_flushes_but_caller_controls_commit(session_factory) -> None:
    event = _event(event_id="projection-rollback", event_type=ExperienceEventType.ACTION_COMPLETED)
    achievement = AchievementEngine().apply(event)[0]
    async with session_factory() as session:
        transaction = await session.begin()
        await SqlAlchemyAchievementProjection(session).append(achievement)
        # Deliberately roll back the caller transaction after the adapter
        # flushed; a durable read model must not commit behind the caller.
        await transaction.rollback()

    async with session_factory() as session:
        assert await SqlAlchemyAchievementProjection(session).earned(event.scope) == ()


@pytest.mark.asyncio
async def test_consumer_injected_sql_projection_is_idempotent_after_restart(
    session_factory,
) -> None:
    event = _event(event_id="consumer-durable", event_type=ExperienceEventType.ACTION_COMPLETED)
    message = ExperienceOutboxMessage(
        message_id="outbox:consumer-durable",
        event_type=f"experience.{event.event_type.value}",
        record=event,
        scope=event.scope,
    )

    async with session_factory() as session, session.begin():
        stored = await SqlAlchemyExperienceOutbox(session).append(message)
        projection = SqlAlchemyAchievementProjection(session)
        consumer = ExperienceAchievementConsumer(projection=projection)
        await consumer.consume(stored)
        assert consumer.achievements_for(stored.message_id)[0].key is AchievementKey.FIRST_STEP

    # A new session/engine simulates a worker restart.  The existing row is
    # read by scope/key, so replay emits no second achievement.
    async with session_factory() as session:
        projection = SqlAlchemyAchievementProjection(session)
        restarted = ExperienceAchievementConsumer(projection=projection)
        await restarted.consume(stored)
        assert restarted.achievements_for(stored.message_id) == ()
        earned = await projection.earned(event.scope)
        assert len(earned) == 1


def test_projection_schema_contains_no_comparative_fields() -> None:
    columns = {column.name for column in inspect(AchievementProjectionRow).columns}
    assert not columns.intersection({"score", "rank", "family_total", "streak"})
