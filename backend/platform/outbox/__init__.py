"""Canonical application-neutral integration outbox."""

from backend.platform.outbox.models import OutboxConflictError, OutboxEvent
from backend.platform.outbox.writer import (
    OUTBOX_EVENTS_TABLE,
    OutboxAppendResult,
    OutboxMetadata,
    OutboxWriterPort,
    SqlAlchemyOutboxWriter,
    read_outbox_event,
)

__all__ = [
    "OUTBOX_EVENTS_TABLE",
    "OutboxAppendResult",
    "OutboxConflictError",
    "OutboxEvent",
    "OutboxMetadata",
    "OutboxWriterPort",
    "SqlAlchemyOutboxWriter",
    "read_outbox_event",
]
