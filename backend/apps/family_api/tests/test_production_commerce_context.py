from unittest.mock import AsyncMock

import pytest

from backend.apps.family_api.production_commerce_context import (
    ProductionCommerceReadContextResolver,
)
from backend.platform.identity.trusted_context import (
    InMemoryTrustedTenantScopeStore,
    TenantBindingStatus,
    TenantMembershipStatus,
    TenantRole,
    TrustedTenantScope,
    TrustedTenantScopeResolver,
)
from backend.platform.identity.context import TenantContext, TenantStatus


@pytest.mark.asyncio
async def test_context_contract_is_family_and_tenant_bound() -> None:
    scope = TrustedTenantScope(
        account_id="account-1",
        tenant=TenantContext("tenant-1", TenantStatus.ACTIVE),
        family_id="family-1",
        region_id="cn",
        role=TenantRole.TENANT_VIEWER,
        membership_status=TenantMembershipStatus.ACTIVE,
        binding_status=TenantBindingStatus.ACTIVE,
    )
    resolved = await TrustedTenantScopeResolver(InMemoryTrustedTenantScopeStore((scope,))).resolve(
        account_id="account-1", family_id="family-1"
    )
    assert resolved.tenant_id == "tenant-1"
    assert resolved.family_id == "family-1"


def test_resolver_requires_real_engine_and_session_factory() -> None:
    with pytest.raises(TypeError):
        ProductionCommerceReadContextResolver(  # type: ignore[arg-type]
            engine=object(), session_factory=AsyncMock()
        )
