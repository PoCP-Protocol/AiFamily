"""Canonical ``outbox_events`` append adapter using the caller's session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, Index, Integer, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Uuid

from backend.platform.outbox.models import OutboxConflictError, OutboxEvent, canonical_json

OUTBOX_EVENTS_TABLE = "outbox_events"
OutboxMetadata = MetaData()
_JSON_PAYLOAD = JSON().with_variant(JSONB(), "postgresql")

outbox_events = Table(
    OUTBOX_EVENTS_TABLE,
    OutboxMetadata,
    Column("outbox_id", Uuid(as_uuid=True), primary_key=True),
    Column("aggregate_type", String(64), nullable=False),
    Column("aggregate_id", String(128), nullable=False),
    Column("event_name", String(128), nullable=False),
    Column("event_version", Integer, nullable=False),
    Column("event_id", Uuid(as_uuid=True), nullable=False, unique=True),
    Column("correlation_id", String(128), nullable=False),
    Column("payload", _JSON_PAYLOAD, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Index(
    "idx_outbox_unpublished",
    outbox_events.c.created_at,
    postgresql_where=outbox_events.c.published_at.is_(None),
)


@dataclass(frozen=True, slots=True)
class OutboxAppendResult:
    event_id: UUID
    replayed: bool


class OutboxWriterPort(Protocol):
    async def append(self, session: AsyncSession, event: OutboxEvent) -> OutboxAppendResult:
        """Stage one event in ``session`` without committing."""
        ...


class SqlAlchemyOutboxWriter:
    """Append or idempotently replay an immutable canonical outbox event."""

    async def append(self, session: AsyncSession, event: OutboxEvent) -> OutboxAppendResult:
        query = select(outbox_events).where(outbox_events.c.event_id == event.event_id)
        existing = (
            await session.execute(query)
        ).mappings().first()
        if existing is not None:
            if not _matches(existing, event):
                raise OutboxConflictError("outbox_event_id_payload_mismatch")
            return OutboxAppendResult(event_id=event.event_id, replayed=True)

        await session.execute(
            outbox_events.insert().values(
                outbox_id=uuid4(),
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_name=event.event_name,
                event_version=event.event_version,
                event_id=event.event_id,
                correlation_id=event.correlation_id,
                payload=event.storage_payload(),
                occurred_at=event.occurred_at,
                published_at=None,
                retry_count=0,
                created_at=datetime.now(UTC),
            )
        )
        return OutboxAppendResult(event_id=event.event_id, replayed=False)


async def read_outbox_event(session: AsyncSession, event_id: UUID) -> OutboxEvent | None:
    row = (
        await session.execute(select(outbox_events).where(outbox_events.c.event_id == event_id))
    ).mappings().first()
    return None if row is None else _from_row(row)


def _matches(row, event: OutboxEvent) -> bool:
    stored = _from_row(row)
    return (
        stored.aggregate_type == event.aggregate_type
        and stored.aggregate_id == event.aggregate_id
        and stored.event_name == event.event_name
        and stored.event_version == event.event_version
        and stored.correlation_id == event.correlation_id
        and stored.request_hash == event.request_hash
        and canonical_json(stored.payload) == canonical_json(event.payload)
    )


def _from_row(row) -> OutboxEvent:
    envelope = dict(row["payload"])
    platform = dict(envelope.get("platform") or {})
    occurred_at = row["occurred_at"]
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return OutboxEvent(
        event_id=row["event_id"],
        tenant_id=str(platform["tenant_id"]),
        family_id=str(platform["family_id"]),
        aggregate_type=row["aggregate_type"],
        aggregate_id=row["aggregate_id"],
        event_name=row["event_name"],
        event_version=row["event_version"],
        idempotency_key=str(platform["idempotency_key"]),
        request_hash=str(platform["request_hash"]),
        correlation_id=row["correlation_id"],
        payload=dict(envelope.get("event") or {}),
        occurred_at=occurred_at,
    )


__all__ = [
    "OUTBOX_EVENTS_TABLE",
    "OutboxAppendResult",
    "OutboxMetadata",
    "OutboxWriterPort",
    "SqlAlchemyOutboxWriter",
    "outbox_events",
    "read_outbox_event",
]
