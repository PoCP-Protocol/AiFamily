"""AuditRecorder — minimal recorder with an in-memory buffer + DB flush seam.

Wave 1 scope: hold recorded events in memory and make them queryable
immediately (so callers can assert "the event I just recorded is there"
without a database round-trip). The real durable audit table is deferred to
Batch 3 (Family Core, the first domain that mutates canonical state); at
that point `flush()` gains a real implementation that persists via
backend/platform/persistence's UnitOfWork instead of a no-op.
"""

from __future__ import annotations

from backend.platform.audit.models import AuditEvent


class AuditRecorder:
    """In-memory audit event recorder with a DB-flush seam."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)

    def all_events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def events_for_resource(self, resource_type: str, resource_id: str) -> tuple[AuditEvent, ...]:
        return tuple(
            e
            for e in self._events
            if e.resource_type == resource_type and e.resource_id == resource_id
        )

    async def flush(self) -> int:
        """Persist buffered events to durable storage and clear the buffer.

        Wave 1 has no durable audit table yet (see module docstring), so
        this is a no-op that reports how many events *would* have been
        flushed, without clearing the in-memory buffer — callers must not
        assume flush() empties memory until a real backing store lands.
        """
        return len(self._events)
