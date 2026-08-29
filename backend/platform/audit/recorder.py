"""AuditRecorder — in-memory buffer in front of the durable audit table.

`record()` buffers; `flush(session)` writes the buffer to
`platform_audit_events` through the caller's session and only then clears it.
The buffer exists so callers can assert on "the event I just recorded" without
a database round-trip, not because durability is optional.

Transaction model (the load-bearing decision)
---------------------------------------------
`flush()` takes the **caller's** `AsyncSession` — the one the domain
repositories write through — and issues no commit. Audit rows therefore become
visible exactly when the domain rows they describe do. This is a same-
transaction design, chosen over an outbox: an outbox makes "domain row
committed, audit row not yet written, process dies" reachable, and that is the
precise state R6 forbids. The cost is that a failing audit insert aborts the
business write; that is the correct direction of failure for "无审计不得改状态".
Full argument in `store.py`'s module docstring.

Failure handling: if the insert raises, the buffer is **left intact** and the
exception propagates. Losing the events on a failed write would turn a visible
error into a silent gap in the trail — and since the caller's transaction is
now doomed anyway, the domain write those events describe will not survive
either.

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

from sqlalchemy.ext.asyncio import AsyncSession

from backend.platform.audit.models import AuditActionKind, AuditEvent
from backend.platform.audit.store import persist_events


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

    async def flush(self, session: AsyncSession) -> int:
        """Persist buffered events through `session`, then clear the buffer.

        Returns the number of rows inserted.

        `session` is required, not optional-with-a-default. A default would let
        `flush()` be called with no transaction in scope and quietly open its
        own — which is the outbox failure mode wearing a same-transaction
        signature (the audit would commit independently of the business write).
        Making the session an argument means every call site has to name the
        transaction its audit rows join.

        No commit here: the caller's `UnitOfWork.commit()` owns that. The buffer
        is cleared only after `persist_events` returns, so a raised exception
        leaves every event still buffered.
        """
        if not self._events:
            return 0
        # Snapshot before the await: `record()` from another task during the
        # insert must not have its event dropped by the clear below.
        pending = tuple(self._events)
        written = await persist_events(session, pending)
        del self._events[: len(pending)]
        return written
