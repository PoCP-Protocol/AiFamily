"""Server-derived action context.

Same rule as the membership domain, and it exists as its own type rather than a
shared import on purpose: the two domains must not depend on each other (four-
axis separation). Duplicating a five-field dataclass is cheaper than an import
edge that makes "points cannot be converted into a tier" a matter of discipline.

A client command must never carry `tenant_id` / `family_id` / `actor_person_id` /
`environment`. Those come from the authenticated session, so there is no wire
format in which a caller can name another family or ask for `PRODUCTION`.
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
        """Derive a stable child idempotency key for a fact written alongside a
        command (e.g. the ledger row of a redemption), so a replayed command
        does not append a second one."""
        if self.idempotency_key is None:
            return None
        return f"{self.idempotency_key}:{suffix}"
