"""AuditEvent + AuditRecorder — R6 (no state mutation without audit) plus
read-access logging (《未成年人网络保护条例》第36条, see
docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md §8).

See governance/MIGRATION_MANIFEST.yaml capability `platform_audit`
(disposition REIMPLEMENT — the source repository's AuditModule was judged
"too thin" to copy). This Wave 1 implementation is intentionally minimal: an
in-memory recorder with a `flush()` seam for a real DB table, which arrives
in Batch 3 alongside Family Core (the first domain that actually mutates
canonical state and therefore actually needs durable audit).
"""

from __future__ import annotations

from backend.platform.audit.models import AuditActionKind, AuditEvent
from backend.platform.audit.recorder import AuditRecorder

__all__ = ["AuditActionKind", "AuditEvent", "AuditRecorder"]
