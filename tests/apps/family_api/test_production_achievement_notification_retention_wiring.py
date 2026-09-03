from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.production_achievement_notification_retention_wiring import (
    AchievementNotificationRetentionSchedule,
    ProductionAchievementNotificationRetentionRuntime,
)
from backend.intelligence.experience.notification_retention import (
    InMemoryAchievementNotificationDeletionAudit,
)
from backend.intelligence.experience.persistence import ExperiencePersistenceBase
from backend.intelligence.experience.projections import AchievementNotificationRow


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
async def test_production_notification_retention_uses_one_transaction(session_factory) -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        session.add(
            AchievementNotificationRow(
                notification_id="retention-runtime-old",
                achievement_id="achievement:retention-old",
                tenant_id="tenant-1",
                family_id="family-1",
                subject_ids="[]",
                title="old",
                message="old",
                status="READ",
                created_at=now - timedelta(days=30),
            )
        )
    audit = InMemoryAchievementNotificationDeletionAudit()
    runtime = ProductionAchievementNotificationRetentionRuntime(
        session_factory,
        lambda _session: audit,
        environment="production",
        ttl=timedelta(days=7),
        batch_limit=10,
    )

    result = await runtime.run_once(now=now)

    assert result.deleted == 1
    assert tuple(audit.receipts) == ("achievement-notification-retention:retention-runtime-old",)
    async with session_factory() as session:
        assert await session.get(AchievementNotificationRow, "retention-runtime-old") is None


@pytest.mark.asyncio
async def test_notification_retention_scheduled_tick_uses_schedule_batch_limit(
    session_factory,
) -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        for index in range(2):
            session.add(
                AchievementNotificationRow(
                    notification_id=f"scheduled-old-{index}",
                    achievement_id=f"achievement:scheduled-old-{index}",
                    tenant_id="tenant-1",
                    family_id="family-1",
                    subject_ids="[]",
                    title="old",
                    message="old",
                    status="READ",
                    created_at=now - timedelta(days=30 + index),
                )
            )
    audit = InMemoryAchievementNotificationDeletionAudit()
    runtime = ProductionAchievementNotificationRetentionRuntime(
        session_factory,
        lambda _session: audit,
        environment="staging",
        ttl=timedelta(days=7),
        schedule=AchievementNotificationRetentionSchedule(
            interval=timedelta(hours=2), batch_limit=1
        ),
    )

    result = await runtime.run_scheduled_tick(now=now)

    assert result.deleted == 1


def test_notification_retention_schedule_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="interval must be positive"):
        AchievementNotificationRetentionSchedule(interval=timedelta(0))
    with pytest.raises(ValueError, match="batch_limit must be positive"):
        AchievementNotificationRetentionSchedule(batch_limit=0)


def test_production_notification_retention_rejects_invalid_configuration(session_factory) -> None:
    with pytest.raises(ValueError, match="staging or production"):
        ProductionAchievementNotificationRetentionRuntime(
            session_factory,
            lambda _session: InMemoryAchievementNotificationDeletionAudit(),
            environment="test",
            ttl=timedelta(days=1),
        )
    with pytest.raises(ValueError, match="ttl must be positive"):
        ProductionAchievementNotificationRetentionRuntime(
            session_factory,
            lambda _session: InMemoryAchievementNotificationDeletionAudit(),
            environment="staging",
            ttl=timedelta(0),
        )
    with pytest.raises(ValueError, match="batch_limit must be positive"):
        ProductionAchievementNotificationRetentionRuntime(
            session_factory,
            lambda _session: InMemoryAchievementNotificationDeletionAudit(),
            environment="staging",
            ttl=timedelta(days=1),
            batch_limit=0,
        )
