"""Server-derived action context for the service booking chain.

Same rule as membership's `application/context.py`: a client command must NOT
carry `tenant_id / family_id / actor_person_id / environment`. Those are derived
from the authenticated session and handed in as this object, so no request model
can inject them — a caller cannot ask to book on behalf of another family, and
cannot ask for `PRODUCTION`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.value_objects import Environment


@dataclass(frozen=True)
class ActionContext:
    tenant_id: str
    family_id: str
    actor_person_id: str
    actor: str
    correlation_id: str
    environment: Environment = "DEV"
    idempotency_key: str | None = None

    def child_key(self, suffix: str) -> str | None:
        """Derive a stable child idempotency key for a second row written by the
        same command, so a replay does not append a duplicate."""
        if self.idempotency_key is None:
            return None
        return f"{self.idempotency_key}:{suffix}"
