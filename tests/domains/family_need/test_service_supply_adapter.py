from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.domains.family_need.domain.value_objects import ResourceGapReason, SupplyShape
from backend.domains.family_need.infrastructure.service_supply_adapter import (
    ServiceSupplyAdapter,
)
from backend.domains.service.domain.entities import ServiceOffering
from backend.domains.service.infrastructure.fake_repository import FakeServiceRepository


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seeded_repository() -> FakeServiceRepository:
    repository = FakeServiceRepository()
    now = _now()
    await repository.save_offering(
        ServiceOffering(
            service_offering_id="offering-active",
            tenant_id="tenant-a",
            provider_id="provider-1",
            service_offering_ref="ACTIVE_OFFERING",
            title="陪伴课",
            admission_status="ADMITTED",
            source_ref="test",
            effective_from=now,
            created_at=now,
            created_by="system:test",
            updated_at=now,
            updated_by="system:test",
        )
    )
    await repository.save_offering(
        ServiceOffering(
            service_offering_id="offering-suspended",
            tenant_id="tenant-a",
            provider_id="provider-1",
            service_offering_ref="SUSPENDED_OFFERING",
            title="停用课",
            admission_status="SUSPENDED",
            source_ref="test",
            effective_from=now,
            created_at=now,
            created_by="system:test",
            updated_at=now,
            updated_by="system:test",
        )
    )
    return repository


@pytest.mark.asyncio
async def test_resolve_component_matches_bookable_offering():
    adapter = ServiceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-a",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.SERVICE,
        component_id="ACTIVE_OFFERING",
        version="1",
    )

    assert ref is not None
    assert ref.component_id == "ACTIVE_OFFERING"
    assert ref.shape is SupplyShape.SERVICE
    assert ref.version == "1"


@pytest.mark.asyncio
async def test_resolve_component_scoped_to_tenant():
    adapter = ServiceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-b",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.SERVICE,
        component_id="ACTIVE_OFFERING",
        version="1",
    )

    assert ref is None


@pytest.mark.asyncio
async def test_resolve_component_returns_none_for_non_service_shape():
    """A PRODUCT shape is not this adapter's concern; it must defer, not guess."""
    adapter = ServiceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-a",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.PRODUCT,
        component_id="ACTIVE_OFFERING",
        version="1",
    )

    assert ref is None


@pytest.mark.asyncio
async def test_resolve_component_returns_none_for_suspended_offering():
    adapter = ServiceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-a",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.SERVICE,
        component_id="SUSPENDED_OFFERING",
        version="1",
    )

    assert ref is None


@pytest.mark.asyncio
async def test_resolve_component_returns_none_for_unknown_id():
    adapter = ServiceSupplyAdapter(await _seeded_repository())

    ref = await adapter.resolve_component(
        tenant_id="tenant-a",
        region="CN",
        locale="zh-CN",
        shape=SupplyShape.SERVICE,
        component_id="NO_SUCH_OFFERING",
        version="1",
    )

    assert ref is None


@pytest.mark.asyncio
async def test_check_resource_capacity_flags_missing_offering():
    from backend.domains.family_need.domain.value_objects import SolutionComponentRef

    adapter = ServiceSupplyAdapter(await _seeded_repository())
    component_refs = (
        SolutionComponentRef(
            component_id="NO_SUCH_OFFERING", shape=SupplyShape.SERVICE, version="1"
        ),
    )

    gap = await adapter.check_resource_capacity(
        tenant_id="tenant-a", family_id="fam-1", need_id="need-1", component_refs=component_refs
    )

    assert gap is not None
    assert gap.reason is ResourceGapReason.NO_CAPACITY


@pytest.mark.asyncio
async def test_check_resource_capacity_passes_when_offering_available():
    from backend.domains.family_need.domain.value_objects import SolutionComponentRef

    adapter = ServiceSupplyAdapter(await _seeded_repository())
    component_refs = (
        SolutionComponentRef(
            component_id="ACTIVE_OFFERING", shape=SupplyShape.SERVICE, version="1"
        ),
    )

    gap = await adapter.check_resource_capacity(
        tenant_id="tenant-a", family_id="fam-1", need_id="need-1", component_refs=component_refs
    )

    assert gap is None


@pytest.mark.asyncio
async def test_get_resource_gap_returns_reason_and_detail():
    adapter = ServiceSupplyAdapter(await _seeded_repository())

    gap = await adapter.get_resource_gap(
        need_id="need-1", reason=ResourceGapReason.REGION_UNSUPPORTED, detail="no region"
    )

    assert gap.need_id == "need-1"
    assert gap.reason is ResourceGapReason.REGION_UNSUPPORTED
    assert gap.detail == "no region"
