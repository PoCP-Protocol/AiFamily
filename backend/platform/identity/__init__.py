"""Actor and Tenant identity context primitives.

See governance/MIGRATION_MANIFEST.yaml capability
`platform_actor_tenant_context` (disposition REIMPLEMENT — the source
repository has no shared ActorContext/TenantContext; only a private,
per-domain equivalent in membership).
"""

from __future__ import annotations

from backend.platform.identity.context import ActorContext, ActorType, TenantContext, TenantStatus

__all__ = ["ActorContext", "ActorType", "TenantContext", "TenantStatus"]
