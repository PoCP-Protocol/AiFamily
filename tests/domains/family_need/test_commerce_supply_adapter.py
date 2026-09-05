from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.domains.commerce.domain.entities import ProductOffering
from backend.domains.commerce.infrastructure.fake_repository import FakeCommerceRepository
from backend.domains.family_need.domain.value_objects import ResourceGapReason, SupplyShape
from backend.domains.family_need.infrastructure.commerce_supply_adapter import (
    CommerceSupplyAdapter,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seeded_repository() -> FakeCommerceRepository:
    repository = FakeCommerceRepository()
    await repository.save_product(
        ProductOffering(
            product_id="platform-product",
            product_ref="PLATFORM_PRODUCT",
            title="平台方案",
            source_ref="test",
            effective_from=_now(),
        )
    )
    await repository.save_product(
        ProductOffering(
            product_id="tenant-product",
            scope_type="TENANT",
            tenant_id="tenant-a",
            product_ref="TENANT_PRODUCT",
            title="租户方案",
            source_ref="test",
            effective_from=_now(),
        )
    )
    await repository.save_product(
        ProductOffering(
            product_id="retired-product",
            product_ref="RETIRED_PRODUCT",
            title="已下架",
            source_ref="test",
            status="RETIRED",
            effective_from=_now(),
        )
    )
    return repository


@pytest.mark.asyncio
async def test_resolve_component_matches_bookable_product():
    adapter = CommerceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-a",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.PRODUCT,
        component_id="PLATFORM_PRODUCT",
        version="1",
    )

    assert ref is not None
    assert ref.component_id == "PLATFORM_PRODUCT"
    assert ref.shape is SupplyShape.PRODUCT
    assert ref.version == "1"


@pytest.mark.asyncio
async def test_resolve_component_scoped_to_tenant():
    adapter = CommerceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-b",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.PRODUCT,
        component_id="TENANT_PRODUCT",
        version="1",
    )

    assert ref is None


@pytest.mark.asyncio
async def test_resolve_component_returns_none_for_non_product_shape():
    """A SERVICE shape is not this adapter's concern; it must defer, not guess."""
    adapter = CommerceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-a",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.SERVICE,
        component_id="PLATFORM_PRODUCT",
        version="1",
    )

    assert ref is None


@pytest.mark.asyncio
async def test_resolve_component_returns_none_for_retired_product():
    adapter = CommerceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-a",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.PRODUCT,
        component_id="RETIRED_PRODUCT",
        version="1",
    )

    assert ref is None


@pytest.mark.asyncio
async def test_resolve_component_returns_none_for_unknown_id():
    adapter = CommerceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-a",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.PRODUCT,
        component_id="NO_SUCH_PRODUCT",
        version="1",
    )

    assert ref is None


@pytest.mark.asyncio
async def test_check_resource_capacity_flags_missing_product():
    from backend.domains.family_need.domain.value_objects import SolutionComponentRef

    adapter = CommerceSupplyAdapter(await _seeded_repository())
    component_refs = (
        SolutionComponentRef(
            component_id="NO_SUCH_PRODUCT", shape=SupplyShape.PRODUCT, version="1"
        ),
    )

    gap = await adapter.check_resource_capacity(
        tenant_id="tenant-a", family_id="fam-1", need_id="need-1", component_refs=component_refs
    )

    assert gap is not None
    assert gap.reason is ResourceGapReason.NO_CAPACITY


@pytest.mark.asyncio
async def test_check_resource_capacity_passes_when_product_available():
    from backend.domains.family_need.domain.value_objects import SolutionComponentRef

    adapter = CommerceSupplyAdapter(await _seeded_repository())
    component_refs = (
        SolutionComponentRef(
            component_id="PLATFORM_PRODUCT", shape=SupplyShape.PRODUCT, version="1"
        ),
    )

    gap = await adapter.check_resource_capacity(
        tenant_id="tenant-a", family_id="fam-1", need_id="need-1", component_refs=component_refs
    )

    assert gap is None


@pytest.mark.asyncio
async def test_get_resource_gap_returns_reason_and_detail():
    adapter = CommerceSupplyAdapter(await _seeded_repository())

    gap = await adapter.get_resource_gap(
        need_id="need-1", reason=ResourceGapReason.NO_MATCHING_CAPABILITY, detail="no match"
    )

    assert gap.need_id == "need-1"
    assert gap.reason is ResourceGapReason.NO_MATCHING_CAPABILITY
    assert gap.detail == "no match"
