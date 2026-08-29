"""AuditEvent + AuditRecorder — R6 (no state mutation without audit) plus
read-access logging (《未成年人网络保护条例》第36条, see
docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md §8).

See governance/MIGRATION_MANIFEST.yaml capability `platform_audit`
(disposition REIMPLEMENT — the source repository's AuditModule was judged
"too thin" to copy).

Three layers:

* `models.py` — the `AuditEvent` value object and its invariants.
* `recorder.py` — `AuditRecorder`, an in-memory buffer whose `flush(session)`
  writes durably.
* `store.py` — the append-only `platform_audit_events` table, written **inside
  the caller's transaction** so an audit row and the domain row it describes
  commit together or not at all. That same-transaction choice (rather than an
  outbox) is what makes R6 a mechanism instead of an intention; the reasoning
  and its costs are in `store.py`'s module docstring.
"""

from __future__ import annotations

from backend.platform.audit.models import AuditActionKind, AuditEvent
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.audit.store import (
    AUDIT_EVENTS_TABLE,
    AuditBase,
    AuditEventRow,
    create_audit_schema,
    persist_events,
    read_all_events,
    read_events_for_subject,
)

__all__ = [
    "AUDIT_EVENTS_TABLE",
    "AuditActionKind",
    "AuditBase",
    "AuditEvent",
    "AuditEventRow",
    "AuditRecorder",
    "create_audit_schema",
    "persist_events",
    "read_all_events",
    "read_events_for_subject",
]
