from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.achievement import AchievementEngine
from backend.intelligence.experience.contracts import ExperienceEventType
from backend.intelligence.experience.persistence import ExperiencePersistenceBase
from backend.intelligence.experience.projections import (
    SqlAlchemyAchievementNotificationProjection,
    SqlAlchemyExperienceAnalyticsProjection,
)
from tests.intelligence.experience.test_gateway import _event, _scope


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
async def test_notification_and_analytics_are_scope_local_and_replay_safe(session_factory):
    event = _event(
        event_id="projection-event",
        event_type=ExperienceEventType.ACTION_COMPLETED,
    )
    achievement = AchievementEngine().apply(event)[0]

    async with session_factory() as session, session.begin():
        notifications = SqlAlchemyAchievementNotificationProjection(session)
        analytics = SqlAlchemyExperienceAnalyticsProjection(session)
        await analytics.record_event(event)
        await analytics.record_event(event)
        await analytics.record_achievement(achievement)
        await analytics.record_achievement(achievement)
        await notifications.publish(achievement)
        await notifications.publish(achievement)

        counts = dict(await analytics.counts(event.scope))
        unread = await notifications.unread(event.scope)
        receipt = await notifications.mark_read(unread[0].notification_id, event.scope)
        retry = await notifications.mark_read(unread[0].notification_id, event.scope)
        unread_after = await notifications.unread(event.scope)

    assert counts == {"achievement:first_step": 1, "event:action_completed": 1}
    assert len(unread) == 1
    assert unread[0].achievement_id == achievement.achievement_id
    assert not hasattr(unread[0], "scope_payload")
    assert receipt.status == "READ"
    assert receipt.read_at is not None
    assert retry.read_at == receipt.read_at
    assert unread_after == ()

    async with session_factory() as session, session.begin():
        notifications = SqlAlchemyAchievementNotificationProjection(session)
        with pytest.raises(ValueError, match="ACHIEVEMENT_NOTIFICATION_NOT_FOUND"):
            await notifications.mark_read(
                receipt.notification_id, _scope(family_id="other-family")
            )


@pytest.mark.asyncio
async def test_analytics_rejects_same_record_id_across_scopes(session_factory):
    event = _event(event_id="projection-scope-event")
    other = replace(event, scope=_scope(family_id="other-family"))

    async with session_factory() as session, session.begin():
        analytics = SqlAlchemyExperienceAnalyticsProjection(session)
        await analytics.record_event(event)
        with pytest.raises(ValueError, match="RECORD_KIND_REPLAY_MISMATCH"):
            await analytics.record_event(other)
