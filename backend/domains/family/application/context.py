"""Server-derived action context for family core.

Same rule as `service` and `membership`: a client command must NOT carry
`tenant_id / actor_person_id`, and must not be able to name the family it is
acting on for anything except `create_family`. Those values are derived from the
authenticated session and handed in as this object, so no request model can inject
them.

`family_id` is `None` on `create_family` and required for everything after it. It
is optional on the dataclass rather than split into two context types because the
alternative — `CreateFamilyContext` and `FamilyScopedContext` — would duplicate
the five fields they share and give every command two overloads. `require_family`
is how a scoped command gets a non-optional value, and it raises rather than
returning a default.

**There is no `tenant_id` column in `0001`.** `families`, `persons`,
`family_relationships`, `life_stage_assignments` and `consents` are all
single-tenant tables — the legacy system added `tenant_id` only from `0028`
onwards, to later tables. `tenant_id` is still carried here because
`AuditEvent.tenant_id` is required (R6) and `IdempotencyKey` is tenant-scoped by
construction, so the value is used for audit and idempotency scoping while not
being persisted on the domain rows. Making family core genuinely multi-tenant
means `ALTER TABLE` on five baselined tables plus a backfill, which is an ADR and
a migration, not a column added in passing. Registered as a known gap.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.errors import FamilyValidationError


@dataclass(frozen=True)
class ActionContext:
    tenant_id: str
    actor: str
    actor_person_id: str | None
    correlation_id: str
    family_id: str | None = None
    idempotency_key: str | None = None

    def require_family(self) -> str:
        if not self.family_id:
            raise FamilyValidationError("family_scope_required")
        return self.family_id

    def child_key(self, suffix: str) -> str | None:
        """A stable derived key for a second row written by the same command, so a
        replay does not append a duplicate. Same device as `service`'s context."""
        if self.idempotency_key is None:
            return None
        return f"{self.idempotency_key}:{suffix}"
