"""Development master-data catalogue used by the mobile service journey.

The records here are supply masters, not family facts.  They mirror the
UI-19→UI-21 scenarios and are intentionally marked fixture-only by the domain
entities.  Production must replace this provider with a persisted catalogue;
it must never import this module as a source of business data.
"""

from datetime import UTC, datetime, timedelta

from ..domain.activity_catalog import ActivityCatalogItem
from ..domain.entities import AvailabilitySlot, ServiceOffering, ServiceProvider
from .ports import ServiceRepositoryPort

CATALOGUE = (
    ("TEACHER_LI", "李老师", "COMMUNICATION", "亲子沟通支持", "VIDEO"),
    ("TEACHER_ZHANG", "张老师", "HABIT", "学习习惯陪练", "TEXT"),
)

ACTIVITY_CATALOGUE = (
    ("ACTIVITY_COMMUNICATION", "亲子沟通小练习", "WORKSHOP", "视频活动"),
    ("ACTIVITY_HABIT", "学习习惯陪练沙龙", "SALON", "线上沙龙"),
)


async def ensure_mobile_master_data(repo: ServiceRepositoryPort, tenant_id: str) -> None:
    """Idempotently make the two mobile service journeys browsable.

    This only writes to the dev fake repository supplied by ``dev_wiring``.
    Stable refs make repeated calls and hot reloads safe without creating
    duplicate catalogue rows.
    """
    existing = {item.service_offering_ref for item in await repo.list_offerings(tenant_id)}
    now = datetime.now(UTC).replace(tzinfo=None)
    for index, (provider_ref, name, offering_ref, title, channel) in enumerate(CATALOGUE):
        if offering_ref in existing:
            continue
        tenant_key = tenant_id.replace("-", "_")
        provider_id = f"master-provider-{tenant_key}-{provider_ref.lower()}"
        offering_id = f"master-offering-{tenant_key}-{offering_ref.lower()}"
        await repo.save_provider(
            ServiceProvider(
                provider_id=provider_id,
                tenant_id=tenant_id,
                provider_ref=provider_ref,
                display_name=name,
                provider_kind="TEACHER",
                qualification_status="ACTIVE",
                admission_status="ADMITTED",
                source_ref="aifamily.mobile.master-data.v1",
                effective_from=now,
                created_at=now,
                created_by="system:dev-master-data",
                updated_at=now,
                updated_by="system:dev-master-data",
                # FGCN's `_DevProviderAdmissionQuery` (and, in production, its
                # real `SqlAlchemyProviderAdmissionQuery` counterpart) reads
                # provider admission for a real teacher out of these two
                # attributes rather than trusting whatever the FGCN call site
                # asked for. `service_collaboration` is the fixed purpose
                # `need_fulfillment_flow.fulfil_confirmed_draft` uses when it
                # requests a real teacher assignment.
                attributes={
                    "fgcn_capability_keys": [],
                    "fgcn_allowed_purposes": ["service_collaboration"],
                },
            )
        )
        await repo.save_offering(
            ServiceOffering(
                service_offering_id=offering_id,
                tenant_id=tenant_id,
                provider_id=provider_id,
                service_offering_ref=offering_ref,
                title=title,
                admission_status="ADMITTED",
                source_ref="aifamily.mobile.master-data.v1",
                attributes={"service_type": title, "age_band": "学龄"},
                effective_from=now,
                created_at=now,
                created_by="system:dev-master-data",
                updated_at=now,
                updated_by="system:dev-master-data",
            )
        )
        starts = now + timedelta(days=index + 1, hours=10)
        await repo.save_slot(
            AvailabilitySlot(
                availability_slot_id=f"master-slot-{tenant_key}-{offering_ref.lower()}",
                tenant_id=tenant_id,
                provider_id=provider_id,
                service_offering_id=offering_id,
                availability_slot_ref=f"MASTER_SLOT_{index + 1:03d}",
                starts_at=starts,
                ends_at=starts + timedelta(hours=1),
                channel=channel,  # type: ignore[arg-type]
                capacity=1,
                reserved_count=0,
                created_at=now,
                updated_at=now,
            )
        )
    existing_activities = {item.activity_ref for item in await repo.list_activities()}
    for index, (activity_ref, title, kind, location) in enumerate(ACTIVITY_CATALOGUE):
        if activity_ref in existing_activities:
            continue
        starts = now + timedelta(days=index + 2, hours=19)
        await repo.save_activity(
            ActivityCatalogItem(
                activity_catalog_id=f"master-activity-{tenant_id.replace('-', '_')}-{index}",
                activity_ref=activity_ref,
                title=title,
                activity_kind=kind,
                starts_at=starts,
                source_ref="aifamily.mobile.master-data.v1",
                attributes={
                    "summary": "围绕家庭当前关注主题的可选活动资料。",
                    "age_hint": "适龄参考：学龄儿童家庭",
                    "location": location,
                    "detail_route": "activity-detail",
                },
            )
        )
    await repo.commit()
