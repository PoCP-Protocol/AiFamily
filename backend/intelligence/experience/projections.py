"""Provider-neutral notification and analytics read projections.

These projections are deliberately downstream of the evidence-bound
Achievement/Experience contracts. They create no domain facts, never compute a
family score or rank, and store only scope-safe metadata (no model output or
raw event payload).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.intelligence.experience.achievement import Achievement
from backend.intelligence.experience.contracts import ExperienceEvent, ExperienceScope
from backend.intelligence.experience.persistence import ExperiencePersistenceBase


class AchievementNotificationProjection(Protocol):
    def publish(self, achievement: Achievement) -> None | Awaitable[None]: ...

    def unread(
        self, scope: ExperienceScope
    ) -> tuple[StoredAchievementNotification, ...] | Awaitable[
        tuple[StoredAchievementNotification, ...]
    ]: ...

    def mark_read(
        self, notification_id: str, scope: ExperienceScope
    ) -> StoredAchievementNotification | Awaitable[StoredAchievementNotification]: ...


class ExperienceAnalyticsProjection(Protocol):
    def record_event(self, event: ExperienceEvent) -> None | Awaitable[None]: ...

    def record_achievement(self, achievement: Achievement) -> None | Awaitable[None]: ...


@dataclass(frozen=True, slots=True)
class StoredAchievementNotification:
    notification_id: str
    achievement_id: str
    tenant_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    title: str
    message: str
    status: str
    created_at: datetime
    read_at: datetime | None


class AchievementNotificationRow(ExperiencePersistenceBase):
    __tablename__ = "ai_achievement_notifications"
    __table_args__ = (UniqueConstraint("achievement_id", name="uq_ai_achievement_notification"),)

    notification_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    achievement_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    subject_ids: Mapped[list[str]] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(String(4000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNREAD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperienceAnalyticsRow(ExperiencePersistenceBase):
    __tablename__ = "ai_experience_analytics"
    __table_args__ = (
        UniqueConstraint(
            "scope_fingerprint", "metric_key", name="uq_ai_experience_analytics_metric"
        ),
    )

    row_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    scope_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    region_id: Mapped[str] = mapped_column(String(16), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExperienceAnalyticsRecordRow(ExperiencePersistenceBase):
    """Idempotency ledger for analytics inputs; no event payload is stored."""

    __tablename__ = "ai_experience_analytics_records"

    record_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    record_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyAchievementNotificationProjection:
    """Idempotent in-app notification inbox; delivery is a separate concern."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def publish(self, achievement: Achievement) -> None:
        notification_id = f"achievement-notification:{achievement.achievement_id}"
        existing = await self._session.get(AchievementNotificationRow, notification_id)
        if existing is not None:
            if existing.achievement_id != achievement.achievement_id:
                raise ValueError("ACHIEVEMENT_NOTIFICATION_REPLAY_MISMATCH")
            return
        self._session.add(
            AchievementNotificationRow(
                notification_id=notification_id,
                achievement_id=achievement.achievement_id,
                tenant_id=achievement.scope.tenant_id,
                family_id=achievement.scope.family_id,
                subject_ids=json.dumps(list(achievement.scope.subject_ids)),
                title=achievement.title,
                message=achievement.message,
                status="UNREAD",
                created_at=_aware(achievement.earned_at),
            )
        )
        await self._session.flush()

    async def unread(self, scope: ExperienceScope) -> tuple[StoredAchievementNotification, ...]:
        rows = await self._session.scalars(
            select(AchievementNotificationRow)
            .where(
                AchievementNotificationRow.tenant_id == scope.tenant_id,
                AchievementNotificationRow.family_id == scope.family_id,
                AchievementNotificationRow.status == "UNREAD",
            )
            .order_by(
                AchievementNotificationRow.created_at,
                AchievementNotificationRow.notification_id,
            )
        )
        return tuple(_stored_notification(row) for row in rows)

    async def mark_read(
        self, notification_id: str, scope: ExperienceScope
    ) -> StoredAchievementNotification:
        """Converge one scope-local notification to READ, idempotently.

        This mutates only the notification read model.  The achievement and
        experience facts remain immutable and are never rewritten by feedback
        interactions.
        """

        if not notification_id.strip():
            raise ValueError("ACHIEVEMENT_NOTIFICATION_ID_REQUIRED")
        row = await self._session.scalar(
            select(AchievementNotificationRow)
            .where(
                AchievementNotificationRow.notification_id == notification_id,
                AchievementNotificationRow.tenant_id == scope.tenant_id,
                AchievementNotificationRow.family_id == scope.family_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ValueError("ACHIEVEMENT_NOTIFICATION_NOT_FOUND")
        if row.status != "READ":
            row.status = "READ"
            row.read_at = datetime.now(UTC)
            await self._session.flush()
        return _stored_notification(row)


class SqlAlchemyExperienceAnalyticsProjection:
    """Scope-local event/achievement counters with no score semantics."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_event(self, event: ExperienceEvent) -> None:
        if await self._seen(event.event_id, "event", event.scope):
            return
        await self._increment(event.scope, f"event:{event.event_type}", event.occurred_at)

    async def record_achievement(self, achievement: Achievement) -> None:
        if await self._seen(achievement.achievement_id, "achievement", achievement.scope):
            return
        await self._increment(
            achievement.scope,
            f"achievement:{achievement.key.value}",
            achievement.earned_at,
        )

    async def counts(
        self, scope: ExperienceScope
    ) -> tuple[tuple[str, int], ...]:
        rows = await self._session.scalars(
            select(ExperienceAnalyticsRow)
            .where(ExperienceAnalyticsRow.scope_fingerprint == _scope_fingerprint(scope))
            .order_by(ExperienceAnalyticsRow.metric_key)
        )
        return tuple((row.metric_key, row.value_count) for row in rows)

    async def _increment(
        self, scope: ExperienceScope, metric_key: str, seen_at: datetime
    ) -> None:
        fingerprint = _scope_fingerprint(scope)
        row = await self._session.scalar(
            select(ExperienceAnalyticsRow)
            .where(
                ExperienceAnalyticsRow.scope_fingerprint == fingerprint,
                ExperienceAnalyticsRow.metric_key == metric_key,
            )
            .with_for_update()
        )
        if row is None:
            row = ExperienceAnalyticsRow(
                row_id=f"analytics:{fingerprint}:{hashlib.sha256(metric_key.encode()).hexdigest()[:16]}",
                scope_fingerprint=fingerprint,
                tenant_id=scope.tenant_id,
                region_id=scope.region_id,
                family_id=scope.family_id,
                metric_key=metric_key,
                value_count=1,
                last_seen_at=_aware(seen_at),
            )
            self._session.add(row)
        else:
            row.value_count += 1
            row.last_seen_at = max(_aware(seen_at), _aware(row.last_seen_at))
        await self._session.flush()

    async def _seen(
        self, record_id: str, record_kind: str, scope: ExperienceScope
    ) -> bool:
        existing = await self._session.get(ExperienceAnalyticsRecordRow, record_id)
        if existing is not None:
            if (
                existing.record_kind != record_kind
                or existing.scope_fingerprint != _scope_fingerprint(scope)
            ):
                raise ValueError("ANALYTICS_RECORD_KIND_REPLAY_MISMATCH")
            return True
        self._session.add(
            ExperienceAnalyticsRecordRow(
                record_id=record_id,
                record_kind=record_kind,
                scope_fingerprint=_scope_fingerprint(scope),
                recorded_at=datetime.now(UTC),
            )
        )
        await self._session.flush()
        return False


def _scope_fingerprint(scope: ExperienceScope) -> str:
    identity = (
        scope.tenant_id,
        scope.region_id,
        scope.family_id,
        tuple(sorted(scope.subject_ids)),
        scope.purpose,
        scope.consent_version,
    )
    encoded = json.dumps(identity, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stored_notification(row: AchievementNotificationRow) -> StoredAchievementNotification:
    created = _aware(row.created_at)
    read_at = None if row.read_at is None else _aware(row.read_at)
    return StoredAchievementNotification(
        notification_id=row.notification_id,
        achievement_id=row.achievement_id,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        subject_ids=tuple(json.loads(row.subject_ids)),
        title=row.title,
        message=row.message,
        status=row.status,
        created_at=created,
        read_at=read_at,
    )


def _aware(value: datetime) -> datetime:
    return (
        value
        if value.tzinfo is not None and value.utcoffset() is not None
        else value.replace(tzinfo=UTC)
    )


__all__ = [
    "AchievementNotificationProjection",
    "AchievementNotificationRow",
    "ExperienceAnalyticsProjection",
    "ExperienceAnalyticsRow",
    "ExperienceAnalyticsRecordRow",
    "SqlAlchemyAchievementNotificationProjection",
    "SqlAlchemyExperienceAnalyticsProjection",
    "StoredAchievementNotification",
]
