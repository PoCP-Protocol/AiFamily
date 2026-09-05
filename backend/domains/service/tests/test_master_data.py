from backend.domains.service.application.master_data import ensure_mobile_master_data
from backend.domains.service.application.queries import list_activity_catalog
from backend.domains.service.infrastructure.fake_repository import FakeServiceRepository


async def test_mobile_master_data_is_idempotent_and_bookable():
    repo = FakeServiceRepository()
    await ensure_mobile_master_data(repo, "tenant-1")
    await ensure_mobile_master_data(repo, "tenant-1")

    offerings = await repo.list_offerings("tenant-1")
    slots = await repo.list_slots("tenant-1")
    assert {item.service_offering_ref for item in offerings} == {
        "COMMUNICATION",
        "HABIT",
    }
    assert len(slots) == 2
    assert all(item.is_bookable for item in offerings)
    assert all(item.is_open for item in slots)
    activities = await repo.list_activities()
    assert {item.activity_ref for item in activities} == {
        "ACTIVITY_COMMUNICATION",
        "ACTIVITY_HABIT",
    }


async def test_master_data_is_tenant_scoped():
    repo = FakeServiceRepository()
    await ensure_mobile_master_data(repo, "tenant-1")
    await ensure_mobile_master_data(repo, "tenant-2")
    assert len(await repo.list_offerings("tenant-1")) == 2
    assert len(await repo.list_offerings("tenant-2")) == 2
    catalog = await list_activity_catalog(repo)
    assert catalog[0]["detail_route"] == "activity-detail"
    assert catalog[0]["summary"]
