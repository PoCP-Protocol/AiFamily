"""AuditEvent — the record R6 requires for every canonical state mutation.

Per REPOSITORY_CONSTITUTION.md R6: "任何对权威业务状态的写入，必须产生
AuditEvent，至少记录 actor / tenant / action / resource / before / after /
reason / correlation_id / timestamp." Every one of those fields is
represented below and none are optional except `before`/`after` (a create
has no `before`; a delete may have no `after`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One immutable record of a state-changing action."""

    actor_id: str
    tenant_id: str
    action: str
    resource_type: str
    resource_id: str
    reason: str
    correlation_id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        required_fields = {
            "actor_id": self.actor_id,
            "tenant_id": self.tenant_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "reason": self.reason,
            "correlation_id": self.correlation_id,
        }
        missing = [name for name, value in required_fields.items() if not value]
        if missing:
            raise ValueError(f"AuditEvent is missing required field(s): {missing}")
