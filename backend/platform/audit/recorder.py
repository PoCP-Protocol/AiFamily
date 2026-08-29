"""AuditRecorder — minimal recorder with an in-memory buffer + DB flush seam.

Wave 1 scope: hold recorded events in memory and make them queryable
immediately (so callers can assert "the event I just recorded is there"
without a database round-trip). The real durable audit table is deferred to
Batch 3 (Family Core, the first domain that mutates canonical state); at
that point `flush()` gains a real implementation that persists via
backend/platform/persistence's UnitOfWork instead of a no-op.

Read access (《未成年人网络保护条例》第36条)
-------------------------------------------
`record_read()` is the single entry point for read-access logging. It exists
as a named method rather than leaving callers to hand-build an
`AuditEvent(action_kind=READ, ...)` for two reasons:

1. It is greppable. "Does any code path that reads minor data leave a trace?"
   is answerable by searching for one symbol, which is what makes the
   architecture checker in `tests/architecture/test_compliance_constraints.py`
   possible at all.
2. It cannot be called half-way. Every 第36条 element (subject, fields,
   purpose, approval) is a required keyword argument, so an incomplete
   read-access record fails at the call site rather than producing a
   record that merely looks compliant.
"""

from __future__ import annotations

from collections.abc import Iterable

from backend.platform.audit.models import AuditActionKind, AuditEvent


class AuditRecorder:
    """In-memory audit event recorder with a DB-flush seam."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)

    def record_read(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        subject_person_id: str,
        accessed_fields: Iterable[str],
        access_purpose: str,
        reason: str,
        correlation_id: str,
        subject_is_minor: bool = False,
        approval_ref: str | None = None,
    ) -> AuditEvent:
        """Record one read access to personal information.

        `subject_is_minor=True` makes `approval_ref` mandatory — the 审批
        requirement of 第36条. The recorder does not infer minority from the
        subject id: age is domain knowledge, and a recorder that guesses is a
        recorder that guesses wrong silently. The caller must state it.

        Returns the event so the caller can assert on it without reaching back
        into the buffer.
        """
        event = AuditEvent(
            actor_id=actor_id,
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            reason=reason,
            correlation_id=correlation_id,
            action_kind=AuditActionKind.READ,
            subject_person_id=subject_person_id,
            subject_is_minor=subject_is_minor,
            accessed_fields=tuple(accessed_fields),
            access_purpose=access_purpose,
            approval_ref=approval_ref,
        )
        self._events.append(event)
        return event

    def all_events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def events_for_resource(self, resource_type: str, resource_id: str) -> tuple[AuditEvent, ...]:
        return tuple(
            e
            for e in self._events
            if e.resource_type == resource_type and e.resource_id == resource_id
        )

    def read_events_for_subject(self, subject_person_id: str) -> tuple[AuditEvent, ...]:
        """Every read access recorded against one person.

        This is the query shape 第36条 compliance reporting needs ("who accessed
        this minor's information, when, for what purpose, under whose approval"),
        and it is also what the 第37条 annual audit has to be able to produce.
        """
        return tuple(
            e for e in self._events if e.is_read and e.subject_person_id == subject_person_id
        )

    async def flush(self) -> int:
        """Persist buffered events to durable storage and clear the buffer.

        Wave 1 has no durable audit table yet (see module docstring), so
        this is a no-op that reports how many events *would* have been
        flushed, without clearing the in-memory buffer — callers must not
        assume flush() empties memory until a real backing store lands.
        """
        return len(self._events)
