from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.notification_retention import (
    AchievementNotificationRecord,
    AchievementNotificationRetentionWorker,
    InMemoryAchievementNotificationDeletionAudit,
    InMemoryAchievementNotificationRetentionStore,
    SqlAlchemyAchievementNotificationRetentionStore,
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


def _record(notification_id: str, created_at: datetime) -> AchievementNotificationRecord:
    return AchievementNotificationRecord(
        notification_id=notification_id,
        tenant_id="tenant-1",
        family_id="family-1",
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_in_memory_retention_is_bounded_and_auditable() -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    store = InMemoryAchievementNotificationRetentionStore(
        [
            _record("old-a", now - timedelta(days=10)),
            _record("old-b", now - timedelta(days=9)),
            _record("fresh", now - timedelta(hours=1)),
        ]
    )
    audit = InMemoryAchievementNotificationDeletionAudit()
    worker = AchievementNotificationRetentionWorker(store, audit=audit)

    run = await worker.run_once(ttl=timedelta(days=7), limit=1, now=now)

    assert run.deleted == 1
    assert run.receipts[0].notification_id == "old-a"
    assert tuple(item.notification_id for item in store.remaining()) == ("fresh", "old-b")
    assert tuple(audit.receipts) == ("achievement-notification-retention:old-a",)


@pytest.mark.asyncio
async def test_sql_retention_deletes_only_expired_notification_rows(session_factory) -> None:
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        session.add_all(
            [
                AchievementNotificationRow(
                    notification_id="old-sql",
                    achievement_id="achievement:old",
                    tenant_id="tenant-1",
                    family_id="family-1",
                    subject_ids="[]",
                    title="old",
                    message="old",
                    status="READ",
                    created_at=now - timedelta(days=10),
                ),
                AchievementNotificationRow(
                    notification_id="fresh-sql",
                    achievement_id="achievement:fresh",
                    tenant_id="tenant-1",
                    family_id="family-1",
                    subject_ids="[]",
                    title="fresh",
                    message="fresh",
                    status="UNREAD",
                    created_at=now - timedelta(hours=1),
                ),
            ]
        )
    async with session_factory() as session, session.begin():
        receipts = await SqlAlchemyAchievementNotificationRetentionStore(session).purge_before(
            now - timedelta(days=7), limit=100, deleted_at=now
        )
        assert [receipt.notification_id for receipt in receipts] == ["old-sql"]
    async with session_factory() as session:
        assert await session.get(AchievementNotificationRow, "old-sql") is None
        assert await session.get(AchievementNotificationRow, "fresh-sql") is not None


@pytest.mark.asyncio
async def test_retention_rejects_unbounded_inputs() -> None:
    worker = AchievementNotificationRetentionWorker(
        InMemoryAchievementNotificationRetentionStore()
    )
    with pytest.raises(ValueError, match="TTL_MUST_BE_POSITIVE"):
        await worker.run_once(ttl=timedelta(0))
    with pytest.raises(ValueError, match="LIMIT_INVALID"):
        await worker.run_once(ttl=timedelta(days=1), limit=-1)
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        await worker.run_once(ttl=timedelta(days=1), now=datetime(2026, 8, 30))
