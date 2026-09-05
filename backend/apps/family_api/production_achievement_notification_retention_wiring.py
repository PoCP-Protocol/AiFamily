"""Production composition root for achievement-notification retention.

The deployment scheduler owns recurrence.  This runtime owns one bounded SQL
transaction and requires an explicit audit sink so notification read-model
deletion cannot be silently unproven.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.experience.notification_retention import (
    AchievementNotificationDeletionAuditSink,
    AchievementNotificationRetentionRun,
    AchievementNotificationRetentionWorker,
    SqlAlchemyAchievementNotificationRetentionStore,
)

ACHIEVEMENT_NOTIFICATION_RETENTION_ENVIRONMENTS = frozenset({"staging", "production"})
AchievementNotificationAuditFactory = Callable[
    [AsyncSession], AchievementNotificationDeletionAuditSink
]


@dataclass(frozen=True, slots=True)
class AchievementNotificationRetentionSchedule:
    """Deployment-owned recurrence and bounded purge parameters."""

    interval: timedelta = timedelta(hours=1)
    batch_limit: int = 100

    def __post_init__(self) -> None:
        if self.interval <= timedelta(0):
            raise ValueError(
                "achievement notification retention schedule interval must be positive"
            )
        if not isinstance(self.batch_limit, int) or isinstance(self.batch_limit, bool):
            raise ValueError(
                "achievement notification retention schedule batch_limit must be an integer"
            )
        if self.batch_limit < 1:
            raise ValueError(
                "achievement notification retention schedule batch_limit must be positive"
            )


@dataclass(frozen=True, slots=True)
class ProductionAchievementNotificationRetentionRuntime:
    """One restart-safe, caller-scheduled notification retention pass."""

    session_factory: async_sessionmaker[AsyncSession]
    audit_factory: AchievementNotificationAuditFactory
    environment: str
    ttl: timedelta
    batch_limit: int = 100
    schedule: AchievementNotificationRetentionSchedule = field(
        default_factory=AchievementNotificationRetentionSchedule
    )

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not callable(self.audit_factory):
            raise TypeError("audit_factory must be callable")
        if self.environment not in ACHIEVEMENT_NOTIFICATION_RETENTION_ENVIRONMENTS:
            raise ValueError(
                "achievement notification retention runtime requires staging or production"
            )
        if self.ttl <= timedelta(0):
            raise ValueError("achievement notification retention ttl must be positive")
        if not isinstance(self.batch_limit, int) or isinstance(self.batch_limit, bool):
            raise ValueError(
                "achievement notification retention batch_limit must be an integer"
            )
        if self.batch_limit < 1:
            raise ValueError(
                "achievement notification retention batch_limit must be positive"
            )
        if not isinstance(self.schedule, AchievementNotificationRetentionSchedule):
            raise TypeError(
                "schedule must be an AchievementNotificationRetentionSchedule"
            )

    async def run_once(
        self,
        *,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> AchievementNotificationRetentionRun:
        effective_limit = self.batch_limit if limit is None else limit
        if not isinstance(effective_limit, int) or isinstance(effective_limit, bool):
            raise ValueError("achievement notification retention limit must be an integer")
        if effective_limit < 0:
            raise ValueError(
                "achievement notification retention limit must not be negative"
            )
        async with self.session_factory() as session, session.begin():
            audit = self.audit_factory(session)
            if not callable(getattr(audit, "record", None)):
                raise TypeError(
                    "audit_factory must return an AchievementNotificationDeletionAuditSink"
                )
            worker = AchievementNotificationRetentionWorker(
                SqlAlchemyAchievementNotificationRetentionStore(session),
                audit=audit,
            )
            return await worker.run_once(
                ttl=self.ttl,
                limit=effective_limit,
                now=now,
            )

    async def run_scheduled_tick(
        self, *, now: datetime | None = None
    ) -> AchievementNotificationRetentionRun:
        """Run one deployment-triggered bounded purge; never sleeps."""

        return await self.run_once(now=now, limit=self.schedule.batch_limit)


__all__ = [
    "ACHIEVEMENT_NOTIFICATION_RETENTION_ENVIRONMENTS",
    "AchievementNotificationRetentionSchedule",
    "ProductionAchievementNotificationRetentionRuntime",
]
