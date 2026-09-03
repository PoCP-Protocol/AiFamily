"""SQLAlchemy persistence adapter for the experience outbox.

The adapter stores an opaque, JSON-serialised envelope rather than ORM objects
from Family/Journey/Commerce.  This keeps the experience boundary portable and
lets a worker replay messages after a process restart. The outbox table is
created by Alembic revision ``0007_experience_outbox``; delivery attempt
metadata is added by ``0026_experience_outbox_delivery_attempts``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.experience.pipeline import ExperienceOutboxMessage


class ExperiencePersistenceBase(DeclarativeBase):
    """Metadata boundary for experience-owned persistence tables."""


class ExperienceOutboxRow(ExperiencePersistenceBase):
    __tablename__ = "experience_outbox_messages"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_experience_outbox_tenant_idempotency",
        ),
    )

    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    region_id: Mapped[str] = mapped_column(String(16), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperienceDeliveryAttemptStatus(StrEnum):
    """Durable delivery state for one outbox message."""

    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    DEAD_LETTERED = "DEAD_LETTERED"


class ExperienceDeliveryAttemptRow(ExperiencePersistenceBase):
    """Metadata-only delivery ledger; the original envelope stays in outbox."""

    __tablename__ = "experience_outbox_delivery_attempts"

    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    last_error: Mapped[str | None] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True, slots=True)
class StoredExperienceDeliveryAttempt:
    """Stable, metadata-only DTO exposed to schedulers and diagnostics."""

    message_id: str
    attempts: int
    status: ExperienceDeliveryAttemptStatus
    last_error: str | None
    updated_at: datetime
    terminal_at: datetime | None
    lease_owner: str | None
    lease_until: datetime | None


@dataclass(frozen=True, slots=True)
class ExperienceDeliveryAttemptCursor:
    """Stable opaque-page position, ordered by updated_at DESC then message ID."""

    updated_at: datetime
    message_id: str

    def __post_init__(self) -> None:
        if self.updated_at.tzinfo is None:
            raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_CURSOR_TIMESTAMP_REQUIRED")
        if not self.message_id.strip():
            raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_CURSOR_MESSAGE_REQUIRED")


@dataclass(frozen=True, slots=True)
class ExperienceDeliveryAttemptPage:
    items: tuple[StoredExperienceDeliveryAttempt, ...]
    next_cursor: ExperienceDeliveryAttemptCursor | None


@dataclass(frozen=True, slots=True)
class ExperienceDeliveryAttemptSummary:
    counts: tuple[tuple[ExperienceDeliveryAttemptStatus, int], ...]

    def count(self, status: ExperienceDeliveryAttemptStatus) -> int:
        return dict(self.counts).get(status, 0)


class SqlAlchemyExperienceDeliveryAttemptStore:
    """Durable attempt counter sharing the caller-owned SQL transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def begin_attempt(self, message_id: str) -> int:
        row = await self._get(message_id, lock=True)
        now = datetime.now(UTC)
        if row is None:
            row = ExperienceDeliveryAttemptRow(
                message_id=message_id,
                attempts=1,
                status=ExperienceDeliveryAttemptStatus.PENDING,
                updated_at=now,
            )
            self._session.add(row)
        else:
            row.attempts += 1
            row.status = ExperienceDeliveryAttemptStatus.PENDING
            row.last_error = None
            row.updated_at = now
            row.terminal_at = None
        await self._session.flush()
        return row.attempts

    async def claim_attempt(
        self,
        message_id: str,
        *,
        worker_id: str,
        lease_ttl: timedelta,
        now: datetime | None = None,
    ) -> int | None:
        """Claim one message and increment its durable attempt atomically.

        A different worker may claim only after the previous lease expires. The
        same worker may retry before expiry, which keeps bounded schedulers
        responsive while still preventing cross-worker double consumption.
        """

        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id is required")
        if lease_ttl.total_seconds() <= 0:
            raise ValueError("lease_ttl must be positive")
        current = now or datetime.now(UTC)
        row = await self._get(message_id, lock=True)
        if row is not None and row.lease_until is not None:
            lease_until = _aware(row.lease_until)
            if lease_until > current and row.lease_owner != worker_id:
                return None
        if row is None:
            row = ExperienceDeliveryAttemptRow(
                message_id=message_id,
                attempts=1,
                status=ExperienceDeliveryAttemptStatus.PENDING,
                updated_at=current,
                lease_owner=worker_id,
                lease_until=current + lease_ttl,
            )
            self._session.add(row)
        else:
            row.attempts += 1
            row.status = ExperienceDeliveryAttemptStatus.PENDING
            row.last_error = None
            row.updated_at = current
            row.lease_owner = worker_id
            row.lease_until = current + lease_ttl
            row.terminal_at = None
        await self._session.flush()
        return row.attempts

    async def mark_published(self, message_id: str) -> StoredExperienceDeliveryAttempt:
        return await self._mark_terminal(message_id, ExperienceDeliveryAttemptStatus.PUBLISHED)

    async def mark_dead_lettered(
        self, message_id: str, *, error: str
    ) -> StoredExperienceDeliveryAttempt:
        return await self._mark_terminal(
            message_id,
            ExperienceDeliveryAttemptStatus.DEAD_LETTERED,
            error=error,
        )

    async def get(self, message_id: str) -> StoredExperienceDeliveryAttempt | None:
        row = await self._get(message_id)
        return _stored_attempt(row) if row is not None else None

    async def list(
        self,
        *,
        limit: int = 100,
        status: ExperienceDeliveryAttemptStatus | None = None,
    ) -> tuple[StoredExperienceDeliveryAttempt, ...]:
        """Return a bounded, metadata-only attempt snapshot for operations."""

        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_LIMIT_INVALID")
        if status is not None and not isinstance(status, ExperienceDeliveryAttemptStatus):
            raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_STATUS_INVALID")
        if limit == 0:
            return ()
        statement = select(ExperienceDeliveryAttemptRow)
        if status is not None:
            statement = statement.where(ExperienceDeliveryAttemptRow.status == status.value)
        statement = statement.order_by(
            ExperienceDeliveryAttemptRow.updated_at.desc(),
            ExperienceDeliveryAttemptRow.message_id,
        ).limit(limit)
        result = await self._session.execute(statement)
        return tuple(_stored_attempt(row) for row in result.scalars())

    async def list_page(
        self,
        *,
        limit: int = 100,
        status: ExperienceDeliveryAttemptStatus | None = None,
        after: ExperienceDeliveryAttemptCursor | None = None,
    ) -> ExperienceDeliveryAttemptPage:
        """Return one stable metadata-only page and an optional continuation cursor."""

        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_LIMIT_INVALID")
        if status is not None and not isinstance(status, ExperienceDeliveryAttemptStatus):
            raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_STATUS_INVALID")
        if after is not None and not isinstance(after, ExperienceDeliveryAttemptCursor):
            raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_CURSOR_INVALID")
        if limit == 0:
            return ExperienceDeliveryAttemptPage(items=(), next_cursor=None)
        statement = select(ExperienceDeliveryAttemptRow)
        if status is not None:
            statement = statement.where(ExperienceDeliveryAttemptRow.status == status.value)
        if after is not None:
            cursor_time = after.updated_at
            statement = statement.where(
                or_(
                    ExperienceDeliveryAttemptRow.updated_at < cursor_time,
                    and_(
                        ExperienceDeliveryAttemptRow.updated_at == cursor_time,
                        ExperienceDeliveryAttemptRow.message_id > after.message_id,
                    ),
                )
            )
        statement = statement.order_by(
            ExperienceDeliveryAttemptRow.updated_at.desc(),
            ExperienceDeliveryAttemptRow.message_id,
        ).limit(limit + 1)
        result = await self._session.execute(statement)
        rows = tuple(result.scalars())
        has_more = len(rows) > limit
        visible = rows[:limit]
        next_cursor = (
            ExperienceDeliveryAttemptCursor(
                updated_at=_aware(visible[-1].updated_at),
                message_id=visible[-1].message_id,
            )
            if has_more and visible
            else None
        )
        return ExperienceDeliveryAttemptPage(
            items=tuple(_stored_attempt(row) for row in visible),
            next_cursor=next_cursor,
        )

    async def summary(self) -> ExperienceDeliveryAttemptSummary:
        """Return counts grouped by known status without exposing message data."""

        result = await self._session.execute(
            select(
                ExperienceDeliveryAttemptRow.status,
                func.count(ExperienceDeliveryAttemptRow.message_id),
            ).group_by(ExperienceDeliveryAttemptRow.status)
        )
        counts: list[tuple[ExperienceDeliveryAttemptStatus, int]] = []
        for raw_status, count in result.all():
            try:
                parsed = ExperienceDeliveryAttemptStatus(raw_status)
            except ValueError as error:
                raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_STATUS_INVALID") from error
            counts.append((parsed, int(count)))
        counts.sort(key=lambda item: item[0].value)
        return ExperienceDeliveryAttemptSummary(counts=tuple(counts))

    async def _mark_terminal(
        self,
        message_id: str,
        status: ExperienceDeliveryAttemptStatus,
        *,
        error: str | None = None,
    ) -> StoredExperienceDeliveryAttempt:
        row = await self._get(message_id, lock=True)
        if row is None:
            raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_NOT_FOUND")
        now = datetime.now(UTC)
        row.status = status
        row.last_error = error
        row.updated_at = now
        row.terminal_at = now
        row.lease_owner = None
        row.lease_until = None
        await self._session.flush()
        return _stored_attempt(row)

    async def _get(
        self, message_id: str, *, lock: bool = False
    ) -> ExperienceDeliveryAttemptRow | None:
        statement = select(ExperienceDeliveryAttemptRow).where(
            ExperienceDeliveryAttemptRow.message_id == message_id
        )
        if lock:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()


@dataclass(frozen=True, slots=True)
class StoredExperienceMessage:
    """Persistence DTO returned to a worker; no ORM row escapes the adapter."""

    message_id: str
    event_type: str
    tenant_id: str
    region_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    purpose: str
    consent_version: str
    idempotency_key: str
    schema_version: str
    payload: dict[str, Any]
    enqueued_at: datetime
    published_at: datetime | None

    @property
    def published(self) -> bool:
        return self.published_at is not None


class SqlAlchemyExperienceOutbox:
    """Async append/pending/publish adapter for the transactional outbox."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, message: ExperienceOutboxMessage) -> StoredExperienceMessage:
        existing = await self._find_by_key(
            message.scope.tenant_id,
            message.record.idempotency_key.scoped_value,
        )
        if existing is not None:
            incoming = _payload(message)
            if existing.payload != incoming:
                raise ValueError("IDEMPOTENCY_REPLAY_MISMATCH")
            return _stored(existing)

        row = ExperienceOutboxRow(
            message_id=message.message_id,
            event_type=message.event_type,
            tenant_id=message.scope.tenant_id,
            region_id=message.scope.region_id,
            family_id=message.scope.family_id,
            subject_ids=list(message.scope.subject_ids),
            purpose=message.scope.purpose,
            consent_version=message.scope.consent_version,
            idempotency_key=message.record.idempotency_key.scoped_value,
            schema_version=message.schema_version,
            payload=_payload(message),
            enqueued_at=message.enqueued_at,
            published_at=message.published_at,
        )
        self._session.add(row)
        await self._session.flush()
        return _stored(row)

    async def pending(self, *, limit: int = 100) -> tuple[StoredExperienceMessage, ...]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        result = await self._session.execute(
            select(ExperienceOutboxRow)
            .where(ExperienceOutboxRow.published_at.is_(None))
            .order_by(ExperienceOutboxRow.enqueued_at, ExperienceOutboxRow.message_id)
            .limit(limit)
        )
        return tuple(_stored(row) for row in result.scalars())

    async def mark_published(
        self,
        message_id: str,
        *,
        published_at: datetime | None = None,
    ) -> StoredExperienceMessage:
        row = await self._session.get(ExperienceOutboxRow, message_id)
        if row is None:
            raise ValueError("OUTBOX_MESSAGE_NOT_FOUND")
        if row.published_at is None:
            row.published_at = published_at or datetime.now(UTC)
            await self._session.flush()
        return _stored(row)

    async def _find_by_key(
        self,
        tenant_id: str,
        idempotency_key: str,
    ) -> ExperienceOutboxRow | None:
        result = await self._session.execute(
            select(ExperienceOutboxRow).where(
                ExperienceOutboxRow.tenant_id == tenant_id,
                ExperienceOutboxRow.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()


def _payload(message: ExperienceOutboxMessage) -> dict[str, Any]:
    encoded = _jsonable(message.record)
    return {"record": encoded}


def _stored(row: ExperienceOutboxRow) -> StoredExperienceMessage:
    return StoredExperienceMessage(
        message_id=row.message_id,
        event_type=row.event_type,
        tenant_id=row.tenant_id,
        region_id=row.region_id,
        family_id=row.family_id,
        subject_ids=tuple(row.subject_ids),
        purpose=row.purpose,
        consent_version=row.consent_version,
        idempotency_key=row.idempotency_key,
        schema_version=row.schema_version,
        payload=dict(row.payload),
        enqueued_at=row.enqueued_at,
        published_at=row.published_at,
    )


def _stored_attempt(row: ExperienceDeliveryAttemptRow) -> StoredExperienceDeliveryAttempt:
    try:
        status = ExperienceDeliveryAttemptStatus(row.status)
    except ValueError as error:
        raise ValueError("EXPERIENCE_DELIVERY_ATTEMPT_STATUS_INVALID") from error
    return StoredExperienceDeliveryAttempt(
        message_id=row.message_id,
        attempts=row.attempts,
        status=status,
        last_error=row.last_error,
        updated_at=row.updated_at,
        terminal_at=row.terminal_at,
        lease_owner=row.lease_owner,
        lease_until=(None if row.lease_until is None else _aware(row.lease_until)),
    )


def _aware(value: datetime) -> datetime:
    return (
        value
        if value.tzinfo is not None and value.utcoffset() is not None
        else value.replace(tzinfo=UTC)
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {
            field_name: _jsonable(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.loads(json.dumps(value, default=str))


__all__ = [
    "ExperienceDeliveryAttemptCursor",
    "ExperienceDeliveryAttemptPage",
    "ExperienceDeliveryAttemptRow",
    "ExperienceDeliveryAttemptStatus",
    "ExperienceDeliveryAttemptSummary",
    "ExperienceOutboxRow",
    "ExperiencePersistenceBase",
    "SqlAlchemyExperienceDeliveryAttemptStore",
    "SqlAlchemyExperienceOutbox",
    "StoredExperienceDeliveryAttempt",
    "StoredExperienceMessage",
]
