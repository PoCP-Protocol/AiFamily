"""TenantDirectory — the lookup that makes ``TenantContext.is_active`` a gate.

``TenantContext.is_active`` existed before this module and had **zero callers**
(recorded as `docs/06_platform/IDENTITY.md` §3 gap 3). A suspended tenant could
be represented and then read and written exactly like an active one, because
nothing ever asked. A property nobody calls is not a rule; it is a comment with
a return type.

The missing piece was never the predicate — it was the *lookup*. An
``ActorContext`` carries a bare ``tenant_id`` string; deciding "is this tenant
allowed to act" requires resolving that string to a status, and there is no
tenant store in this repository yet (`governance/DOMAIN_REGISTRY.yaml` →
`auth_identity`, `family_core`). So this module defines the port and two
implementations, and `backend/platform/authorization/policy.py` makes the
directory a **required constructor argument** of ``PolicyEngine``. That is the
enforcement design:

* The gate lives at the authorization boundary, evaluated once per decision, so
  it cannot be forgotten in one business method out of forty. Putting
  ``is_active`` checks inside domain methods is exactly the failure mode R14
  warns about — a rule enforced by convention in N places is enforced in N-1.
* The directory is not optional and has no permissive default. A caller that
  constructs a ``PolicyEngine`` must say where tenant status comes from. A
  default would fail *open* for every tenant nobody remembered to register.
* An **unknown** tenant is denied, not allowed. "Not in the directory" and
  "suspended" are both DENY, for the same reason
  `backend/platform/authorization/policy.py` denies unregistered actions:
  unknown must never be more permissive than forbidden.

``DenyAllTenantDirectory`` is what a production app gets until the real
Account → TenantMembership → Family chain exists. It denies everything, loudly
and by construction, rather than pretending every tenant is active.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.platform.identity.context import TenantContext, TenantStatus


class TenantDirectory(ABC):
    """Resolves a ``tenant_id`` to its ``TenantContext``, or ``None``."""

    @abstractmethod
    def resolve(self, tenant_id: str) -> TenantContext | None:
        """Return the tenant's context, or ``None`` if the tenant is unknown.

        ``None`` must be treated by callers as DENY, never as "assume active".
        """
        ...


class DenyAllTenantDirectory(TenantDirectory):
    """Knows no tenants, so every lookup denies.

    This is the honest default for an app with no tenant store: it makes the
    absence of tenant status visible as a refusal instead of hiding it behind an
    implicit "everything is active".
    """

    def resolve(self, tenant_id: str) -> TenantContext | None:
        return None


class InMemoryTenantDirectory(TenantDirectory):
    """Dict-backed directory for tests and dev wiring.

    Deliberately has no "default status" parameter: registering a tenant is the
    only way to make it resolvable, so a test cannot accidentally assert against
    a directory that silently activates everything.
    """

    def __init__(self, tenants: dict[str, TenantStatus] | None = None) -> None:
        self._tenants: dict[str, TenantStatus] = dict(tenants or {})

    def register(self, tenant_id: str, status: TenantStatus) -> None:
        if not tenant_id:
            raise ValueError("tenant_id must not be empty")
        self._tenants[tenant_id] = status

    def resolve(self, tenant_id: str) -> TenantContext | None:
        status = self._tenants.get(tenant_id)
        if status is None:
            return None
        return TenantContext(tenant_id=tenant_id, status=status)
