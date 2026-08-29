"""AuditEvent + AuditRecorder — R6 (no state mutation without audit).

See governance/MIGRATION_MANIFEST.yaml capability `platform_audit`
(disposition REIMPLEMENT — the source repository's AuditModule was judged
"too thin" to copy). This Wave 1 implementation is intentionally minimal: an
in-memory recorder with a `flush()` seam for a real DB table, which arrives
in Batch 3 alongside Family Core (the first domain that actually mutates
canonical state and therefore actually needs durable audit).
"""

from __future__ import annotations

from backend.platform.audit.models import AuditEvent
from backend.platform.audit.recorder import AuditRecorder

__all__ = ["AuditEvent", "AuditRecorder"]
