"""Durable, metadata-only dead-letter sink for Experience Outbox messages.

The original envelope remains in ``experience_outbox_messages`` and is never
copied into this operational table.  This gives operators enough information
to locate and replay a message while keeping the DLQ index free of raw family
content.  The sink participates in the caller-owned transaction and is
idempotent by ``message_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.intelligence.experience.outbox_worker import ExperienceDeadLetterSink
from backend.intelligence.experience.persistence import (
    ExperiencePersistenceBase,
    StoredExperienceMessage,
)


class ExperienceDeadLetterRow(ExperiencePersistenceBase):
    """Operational DLQ index; deliberately contains no event payload."""

    __tablename__ = "experience_outbox_dead_letters"

    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    dead_lettered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class StoredExperienceDeadLetter:
    """Safe operational view of a dead-lettered message."""

    message_id: str
    event_type: str
    tenant_id: str
    family_id: str
    attempts: int
    error: str
    dead_lettered_at: datetime


class SqlAlchemyExperienceDeadLetterSink(ExperienceDeadLetterSink):
    """SQL sink that stores only bounded operational metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def publish(
        self,
        message: StoredExperienceMessage,
        *,
        attempts: int,
        error: str,
    ) -> None:
        if attempts < 1:
            raise ValueError("DEAD_LETTER_ATTEMPTS_INVALID")
        reason = error.strip() if isinstance(error, str) else ""
        if not reason:
            raise ValueError("DEAD_LETTER_ERROR_REQUIRED")
        if len(reason) > 4096:
            reason = reason[:4096]
        row = await self._session.get(ExperienceDeadLetterRow, message.message_id)
        if row is not None:
            if (
                row.event_type != message.event_type
                or row.tenant_id != message.tenant_id
                or row.family_id != message.family_id
                or row.attempts != attempts
                or row.error != reason
            ):
                raise ValueError("DEAD_LETTER_IDEMPOTENCY_REPLAY_MISMATCH")
            return
        self._session.add(
            ExperienceDeadLetterRow(
                message_id=message.message_id,
                event_type=message.event_type,
                tenant_id=message.tenant_id,
                family_id=message.family_id,
                attempts=attempts,
                error=reason,
                dead_lettered_at=datetime.now(UTC),
            )
        )
        await self._session.flush()

    async def list_dead_letters(
        self, *, limit: int = 100
    ) -> tuple[StoredExperienceDeadLetter, ...]:
        if limit < 0:
            raise ValueError("DEAD_LETTER_LIMIT_INVALID")
        result = await self._session.execute(
            select(ExperienceDeadLetterRow)
            .order_by(ExperienceDeadLetterRow.dead_lettered_at, ExperienceDeadLetterRow.message_id)
            .limit(limit)
        )
        return tuple(_stored(row) for row in result.scalars())


def _stored(row: ExperienceDeadLetterRow) -> StoredExperienceDeadLetter:
    timestamp = row.dead_lettered_at
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return StoredExperienceDeadLetter(
        message_id=row.message_id,
        event_type=row.event_type,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        attempts=row.attempts,
        error=row.error,
        dead_lettered_at=timestamp,
    )


__all__ = [
    "ExperienceDeadLetterRow",
    "SqlAlchemyExperienceDeadLetterSink",
    "StoredExperienceDeadLetter",
]
