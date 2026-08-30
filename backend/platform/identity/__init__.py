"""Actor and Tenant identity context primitives.

See governance/MIGRATION_MANIFEST.yaml capability
`platform_actor_tenant_context` (disposition REIMPLEMENT — the source
repository has no shared ActorContext/TenantContext; only a private,
per-domain equivalent in membership).
"""

from __future__ import annotations

from backend.platform.identity.context import ActorContext, ActorType, TenantContext, TenantStatus
from backend.platform.identity.directory import (
    DenyAllTenantDirectory,
    InMemoryTenantDirectory,
    TenantDirectory,
)
from backend.platform.identity.trusted_context import (
    InMemoryTrustedTenantScopeStore,
    SqlAlchemyTrustedTenantScopeStore,
    TenantBindingStatus,
    TenantMembershipStatus,
    TenantRole,
    TenantScopeError,
    TrustedTenantScope,
    TrustedTenantScopeResolver,
    TrustedTenantScopeStore,
)

__all__ = [
    "ActorContext",
    "ActorType",
    "DenyAllTenantDirectory",
    "InMemoryTenantDirectory",
    "TenantContext",
    "TenantDirectory",
    "TenantBindingStatus",
    "TenantMembershipStatus",
    "TenantRole",
    "TenantScopeError",
    "TenantStatus",
    "TrustedTenantScope",
    "TrustedTenantScopeResolver",
    "TrustedTenantScopeStore",
    "InMemoryTrustedTenantScopeStore",
    "SqlAlchemyTrustedTenantScopeStore",
]
