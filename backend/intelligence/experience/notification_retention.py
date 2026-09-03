"""Bounded retention for the evidence-bound achievement notification inbox.

The notification inbox is a read model, not a source of achievement facts.
This worker deletes only expired notification rows and emits metadata-only
receipts through an injected audit sink.  It never reads or reconstructs model
output, event payloads, or subject profile data.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.intelligence.experience.projections import AchievementNotificationRow


@dataclass(frozen=True, slots=True)
class AchievementNotificationRecord:
    """Minimal metadata used by the deterministic in-memory adapter."""

    notification_id: str
    tenant_id: str
    family_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.notification_id.strip():
            raise ValueError("ACHIEVEMENT_NOTIFICATION_ID_REQUIRED")
        if not self.tenant_id.strip() or not self.family_id.strip():
            raise ValueError("ACHIEVEMENT_NOTIFICATION_SCOPE_REQUIRED")
        _validate_timestamp(self.created_at)


@dataclass(frozen=True, slots=True)
class AchievementNotificationDeletionReceipt:
    """Metadata-only proof for one deleted notification read-model row."""

    receipt_id: str
    notification_id: str
    tenant_id: str
    family_id: str
    created_at: datetime
    cutoff: datetime
    deleted_at: datetime


@dataclass(frozen=True, slots=True)
class AchievementNotificationRetentionRun:
    cutoff: datetime
    limit: int
    receipts: tuple[AchievementNotificationDeletionReceipt, ...]
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def scanned(self) -> int:
        return len(self.receipts)

    @property
    def deleted(self) -> int:
        return len(self.receipts)


class AchievementNotificationRetentionStore(Protocol):
    async def purge_before(
        self,
        cutoff: datetime,
        *,
        limit: int,
        deleted_at: datetime | None = None,
    ) -> tuple[AchievementNotificationDeletionReceipt, ...]:
        """Delete at most ``limit`` notification rows older than ``cutoff``."""
        ...


class AchievementNotificationDeletionAuditSink(Protocol):
    async def record(
        self, receipts: tuple[AchievementNotificationDeletionReceipt, ...]
    ) -> None:
        """Persist metadata-only deletion receipts idempotently."""
        ...


class SqlAlchemyAchievementNotificationRetentionStore:
    """SQL adapter that deletes only the notification read model."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def purge_before(
        self,
        cutoff: datetime,
        *,
        limit: int,
        deleted_at: datetime | None = None,
    ) -> tuple[AchievementNotificationDeletionReceipt, ...]:
        _validate_timestamp(cutoff)
        _validate_limit(limit)
        if limit == 0:
            return ()
        result = await self._session.execute(
            select(AchievementNotificationRow)
            .where(AchievementNotificationRow.created_at < cutoff)
            .order_by(
                AchievementNotificationRow.created_at,
                AchievementNotificationRow.notification_id,
            )
            .limit(limit)
        )
        rows = tuple(result.scalars())
        deleted_moment = deleted_at or datetime.now(UTC)
        _validate_timestamp(deleted_moment)
        receipts = tuple(
            _receipt(row, cutoff=cutoff, deleted_at=deleted_moment) for row in rows
        )
        for row in rows:
            await self._session.delete(row)
        if rows:
            await self._session.flush()
        return receipts


class InMemoryAchievementNotificationRetentionStore:
    """Deterministic adapter for dev/test; production uses the SQL adapter."""

    def __init__(self, notifications: Iterable[AchievementNotificationRecord] = ()) -> None:
        self._notifications: dict[str, AchievementNotificationRecord] = {}
        for notification in notifications:
            self.add(notification)

    def add(self, notification: AchievementNotificationRecord) -> None:
        if notification.notification_id in self._notifications:
            raise ValueError("ACHIEVEMENT_NOTIFICATION_ID_CONFLICT")
        self._notifications[notification.notification_id] = notification

    async def purge_before(
        self,
        cutoff: datetime,
        *,
        limit: int,
        deleted_at: datetime | None = None,
    ) -> tuple[AchievementNotificationDeletionReceipt, ...]:
        _validate_timestamp(cutoff)
        _validate_limit(limit)
        if limit == 0:
            return ()
        deleted_moment = deleted_at or datetime.now(UTC)
        _validate_timestamp(deleted_moment)
        candidates = sorted(
            (item for item in self._notifications.values() if item.created_at < cutoff),
            key=lambda item: (item.created_at, item.notification_id),
        )[:limit]
        receipts = tuple(
            AchievementNotificationDeletionReceipt(
                receipt_id=_receipt_id(item.notification_id),
                notification_id=item.notification_id,
                tenant_id=item.tenant_id,
                family_id=item.family_id,
                created_at=item.created_at,
                cutoff=cutoff,
                deleted_at=deleted_moment,
            )
            for item in candidates
        )
        for item in candidates:
            del self._notifications[item.notification_id]
        return receipts

    def remaining(self) -> tuple[AchievementNotificationRecord, ...]:
        return tuple(sorted(self._notifications.values(), key=lambda item: item.notification_id))


class InMemoryAchievementNotificationDeletionAudit:
    """Idempotent metadata-only audit adapter for dev/test."""

    def __init__(self) -> None:
        self.receipts: dict[str, AchievementNotificationDeletionReceipt] = {}

    async def record(
        self, receipts: tuple[AchievementNotificationDeletionReceipt, ...]
    ) -> None:
        for receipt in receipts:
            existing = self.receipts.get(receipt.receipt_id)
            if existing is not None and existing != receipt:
                raise ValueError("ACHIEVEMENT_NOTIFICATION_DELETION_AUDIT_CONFLICT")
            self.receipts[receipt.receipt_id] = receipt


class AchievementNotificationRetentionWorker:
    """Run one bounded notification TTL deletion pass."""

    def __init__(
        self,
        store: AchievementNotificationRetentionStore,
        *,
        audit: AchievementNotificationDeletionAuditSink | None = None,
    ) -> None:
        self._store = store
        self._audit = audit

    async def run_once(
        self,
        *,
        ttl: timedelta,
        limit: int = 100,
        now: datetime | None = None,
    ) -> AchievementNotificationRetentionRun:
        if ttl <= timedelta(0):
            raise ValueError("ACHIEVEMENT_NOTIFICATION_TTL_MUST_BE_POSITIVE")
        _validate_limit(limit)
        reference = now or datetime.now(UTC)
        _validate_timestamp(reference)
        cutoff = reference - ttl
        receipts = await self._store.purge_before(
            cutoff,
            limit=limit,
            deleted_at=reference,
        )
        if self._audit is not None and receipts:
            await self._audit.record(receipts)
        return AchievementNotificationRetentionRun(
            cutoff=cutoff,
            limit=limit,
            receipts=receipts,
            completed_at=reference,
        )


def _receipt(
    row: AchievementNotificationRow,
    *,
    cutoff: datetime,
    deleted_at: datetime,
) -> AchievementNotificationDeletionReceipt:
    return AchievementNotificationDeletionReceipt(
        receipt_id=_receipt_id(row.notification_id),
        notification_id=row.notification_id,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        created_at=_aware(row.created_at),
        cutoff=cutoff,
        deleted_at=deleted_at,
    )


def _receipt_id(notification_id: str) -> str:
    return f"achievement-notification-retention:{notification_id}"


def _validate_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("ACHIEVEMENT_NOTIFICATION_RETENTION_LIMIT_INVALID")


def _validate_timestamp(moment: datetime) -> None:
    if moment.tzinfo is None:
        raise ValueError("ACHIEVEMENT_NOTIFICATION_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


__all__ = [
    "AchievementNotificationDeletionAuditSink",
    "AchievementNotificationDeletionReceipt",
    "AchievementNotificationRecord",
    "AchievementNotificationRetentionRun",
    "AchievementNotificationRetentionStore",
    "AchievementNotificationRetentionWorker",
    "InMemoryAchievementNotificationDeletionAudit",
    "InMemoryAchievementNotificationRetentionStore",
    "SqlAlchemyAchievementNotificationRetentionStore",
]
