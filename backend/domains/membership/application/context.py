"""Server-derived action context.

Mirrors the rule already enforced by the TS commerce contract
(`family-commerce-intent.contract.ts`): a client command must NOT carry
`tenant_id / family_id / actor_person_id / price / payment / contact`. Those
are derived server-side from the authenticated session and handed to the
application layer as this object, so no request model can inject them.

`environment` is part of the context rather than the payload for the same
reason — a client cannot ask for `PRODUCTION`.
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

    def ledger_key(self, suffix: str) -> str | None:
        """Derive a stable child idempotency key for the append-only fact
        written alongside a command, so a replayed command does not append a
        second ledger row."""
        if self.idempotency_key is None:
            return None
        return f"{self.idempotency_key}:{suffix}"
