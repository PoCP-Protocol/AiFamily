"""Development product catalogue for UI-13/UI-14.

The records mirror the existing mobile presentation catalogue and the
``family_product_offerings`` baseline table.  They are fixture-only and do not
represent prices, payment, fulfilment, or a production entitlement.
"""

from datetime import UTC, datetime

from ..domain.entities import ProductOffering
from .ports import CommerceRepositoryPort

PRODUCT_CATALOGUE = (
    (
        "PRODUCT_PARENT_CHILD_CAMP",
        "21天亲子沟通挑战营",
        "COURSE",
        "改善亲子关系，从有效沟通开始",
        "希望改善日常亲子沟通节奏的家庭",
        ("视频课程", "每日打卡", "社群交流", "专家答疑"),
        "¥399",
    ),
    (
        "PRODUCT_FAMILY_ASSESSMENT_CARD",
        "家庭成长测评卡",
        "ASSESSMENT",
        "从真实家庭场景开始了解关注方向",
        "想从一个具体场景开始梳理的家庭",
        ("场景测评", "家庭说明", "关注方向", "下一步建议"),
        "¥39",
    ),
    (
        "PRODUCT_PARENT_CHILD_READING_TOOLKIT",
        "亲子阅读工具包",
        "TOOL",
        "把共读变成低负担的家庭时光",
        "希望建立轻松共读节奏的家庭",
        ("共读卡", "提问卡", "记录页", "家庭小结"),
        "¥69",
    ),
    (
        "PRODUCT_FAMILY_FOCUS_CAMP",
        "家庭专注力提升训练营",
        "COURSE",
        "从环境支持和家庭节奏开始练习",
        "希望减少催促、建立可持续日常节奏的家庭",
        ("家庭说明", "环境清单", "行动练习", "阶段回看"),
        "¥199",
    ),
)


async def ensure_mobile_product_master_data(repo: CommerceRepositoryPort) -> None:
    existing = {product.product_ref for product in await repo.list_products(tenant_id="")}
    now = datetime.now(UTC).replace(tzinfo=None)
    for index, (
        product_ref,
        title,
        category,
        subtitle,
        audience,
        delivery,
        family_price,
    ) in enumerate(PRODUCT_CATALOGUE):
        if product_ref in existing:
            continue
        await repo.save_product(
            ProductOffering(
                product_id=f"master-product-{index + 1}",
                product_ref=product_ref,
                title=title,
                source_ref="aifamily.mobile.master-data.v1",
                price_plan_ref=f"DEV_FAMILY_INTENT_{index + 1}",
                entitlement_policy_ref="DEV_NOOP_ENTITLEMENT",
                effective_from=now,
                attributes={
                    "category": category,
                    "subtitle": subtitle,
                    "audience": audience,
                    "delivery": list(delivery),
                    "family_price_label": family_price,
                    "member_price_label": "会员权益可查看",
                },
            )
        )
    await repo.commit()
