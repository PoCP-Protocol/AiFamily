"""Durable notification intent and delivery-attempt adapters.

The caller owns the SQLAlchemy transaction.  This module stores delivery
metadata only; domain facts remain in their canonical aggregates and outbox.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.platform.notification.contracts import (
    DeliveryStatus,
    NotificationIntent,
)


class NotificationPersistenceBase(DeclarativeBase):
    """Declarative base for the notification control-plane tables."""


class NotificationIntentRow(NotificationPersistenceBase):
    __tablename__ = "platform_notification_intents"

    intent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    template_key: Mapped[str] = mapped_column(String(256), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    external_effect: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationAttemptRow(NotificationPersistenceBase):
    __tablename__ = "platform_notification_attempts"

    attempt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(256), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationPersistenceError(RuntimeError):
    """Raised when a durable notification identity conflicts."""


class SqlAlchemyNotificationStore:
    """Caller-transaction-owned persistence operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_intent(self, intent: NotificationIntent) -> NotificationIntentRow:
        existing = await self._session.get(NotificationIntentRow, str(intent.intent_id))
        if existing is not None:
            if not _intent_matches(existing, intent):
                raise NotificationPersistenceError("notification_intent_payload_conflict")
            return existing
        row = NotificationIntentRow(
            intent_id=str(intent.intent_id),
            tenant_id=intent.scope.tenant_id,
            family_id=intent.scope.family_id,
            subject_id=intent.scope.subject_id,
            purpose=intent.scope.purpose,
            consent_version=intent.scope.consent_version,
            channel=intent.channel.value,
            template_key=intent.template_key,
            idempotency_key=intent.idempotency_key,
            correlation_id=intent.correlation_id,
            body=intent.body,
            external_effect=intent.external_effect,
            created_at=intent.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def enqueue_attempt(
        self,
        *,
        intent_id: UUID,
        now: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationAttemptRow:
        attempt_id = f"notification-attempt:{intent_id}"
        existing = await self._session.get(NotificationAttemptRow, attempt_id)
        if existing is not None:
            return existing
        row = NotificationAttemptRow(
            attempt_id=attempt_id,
            intent_id=str(intent_id),
            status=DeliveryStatus.PENDING.value,
            attempt_count=0,
            lease_owner=None,
            lease_until=None,
            next_attempt_at=now,
            provider_reference=None,
            last_error_code=None,
            metadata_payload=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def claim_due(
        self, *, owner: str, now: datetime, lease: timedelta
    ) -> NotificationAttemptRow | None:
        if not owner.strip() or lease <= timedelta(0):
            raise ValueError("notification claim owner and lease are required")
        query = (
            select(NotificationAttemptRow)
            .where(
                NotificationAttemptRow.status.in_(
                    (DeliveryStatus.PENDING.value, DeliveryStatus.RETRY.value)
                ),
                NotificationAttemptRow.next_attempt_at <= now,
            )
            .order_by(NotificationAttemptRow.next_attempt_at, NotificationAttemptRow.attempt_id)
            .limit(1)
        )
        row = (await self._session.execute(query)).scalars().first()
        if row is None:
            return None
        row.status = "leased"
        row.lease_owner = owner
        row.lease_until = now + lease
        row.updated_at = now
        await self._session.flush()
        return row

    async def record_failure(
        self,
        row: NotificationAttemptRow,
        *,
        now: datetime,
        error_code: str,
        retry_at: datetime | None,
        max_attempts: int,
    ) -> None:
        if row.status != "leased" or not error_code.strip():
            raise ValueError("only leased notification attempts can fail")
        row.attempt_count += 1
        row.last_error_code = error_code
        row.lease_owner = None
        row.lease_until = None
        row.updated_at = now
        if row.attempt_count >= max_attempts or retry_at is None:
            row.status = DeliveryStatus.DEAD_LETTER.value
        else:
            row.status = DeliveryStatus.RETRY.value
            row.next_attempt_at = retry_at
        await self._session.flush()

    async def record_success(
        self,
        row: NotificationAttemptRow,
        *,
        now: datetime,
        provider_reference: str | None = None,
    ) -> None:
        if row.status != "leased":
            raise ValueError("only leased notification attempts can succeed")
        row.status = DeliveryStatus.DELIVERED.value
        row.attempt_count += 1
        row.provider_reference = provider_reference
        row.lease_owner = None
        row.lease_until = None
        row.updated_at = now
        await self._session.flush()

    async def suppress(self, row: NotificationAttemptRow, *, now: datetime, reason: str) -> None:
        if row.status not in {DeliveryStatus.PENDING.value, DeliveryStatus.RETRY.value}:
            raise ValueError("only pending notification attempts can be suppressed")
        if not reason.strip():
            raise ValueError("notification suppression reason is required")
        row.status = DeliveryStatus.SUPPRESSED.value
        row.last_error_code = reason
        row.updated_at = now
        await self._session.flush()

    async def defer(self, row: NotificationAttemptRow, *, until: datetime, reason: str) -> None:
        if row.status not in {DeliveryStatus.PENDING.value, DeliveryStatus.RETRY.value}:
            raise ValueError("only pending notification attempts can be deferred")
        if not reason.strip():
            raise ValueError("notification deferral reason is required")
        row.status = DeliveryStatus.RETRY.value
        row.next_attempt_at = until
        row.last_error_code = reason
        row.updated_at = until
        await self._session.flush()

    async def recover_expired_leases(self, *, now: datetime) -> int:
        query = select(NotificationAttemptRow).where(
            NotificationAttemptRow.status == "leased",
            NotificationAttemptRow.lease_until < now,
        )
        rows = (await self._session.execute(query)).scalars().all()
        for row in rows:
            row.status = DeliveryStatus.RETRY.value
            row.lease_owner = None
            row.lease_until = None
            row.next_attempt_at = now
            row.updated_at = now
        if rows:
            await self._session.flush()
        return len(rows)

    async def replay_dead_letter(self, row: NotificationAttemptRow, *, now: datetime) -> None:
        if row.status != DeliveryStatus.DEAD_LETTER.value:
            raise ValueError("only dead-letter notification attempts can be replayed")
        row.status = DeliveryStatus.RETRY.value
        row.attempt_count = 0
        row.last_error_code = None
        row.next_attempt_at = now
        row.updated_at = now
        await self._session.flush()


def _intent_matches(row: NotificationIntentRow, intent: NotificationIntent) -> bool:
    return (
        row.tenant_id == intent.scope.tenant_id
        and row.family_id == intent.scope.family_id
        and row.subject_id == intent.scope.subject_id
        and row.purpose == intent.scope.purpose
        and row.consent_version == intent.scope.consent_version
        and row.channel == intent.channel.value
        and row.template_key == intent.template_key
        and row.idempotency_key == intent.idempotency_key
        and row.correlation_id == intent.correlation_id
        and row.body == intent.body
        and row.external_effect == intent.external_effect
    )


__all__ = [
    "NotificationAttemptRow",
    "NotificationIntentRow",
    "NotificationPersistenceBase",
    "NotificationPersistenceError",
    "SqlAlchemyNotificationStore",
]
