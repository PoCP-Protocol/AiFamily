"""Shared constants, context builder and catalogue seeder for points tests.

Plain importable module, not `conftest.py`: conftest holds pytest fixtures, this
holds helpers test modules import by real module path (resolved as an implicit
namespace package via `pythonpath = ["."]`, so no cwd tricks — R12).
"""

from __future__ import annotations

from backend.domains.loyalty_points.application.context import ActionContext
from backend.domains.loyalty_points.domain.entities import (
    PointsEarnRule,
    RedemptionCatalogItem,
    utcnow,
)

TENANT = "tenant-001"
FAMILY = "family-001"
GUARDIAN = "person-guardian-001"
CHILD = "person-child-001"

# Rule refs used across the tests.
RULE_CHECKIN = "GROWTH_TASK_CHECKIN_DAILY"
RULE_REVIEW = "GROWTH_REVIEW_COMPLETED"
RULE_REFERRAL = "REFERRAL_QUALIFIED"

ITEM_CONSULTATION = "EXPERT_CONSULTATION_SLOT"
ITEM_GIFT = "GROWTH_STORY_PRINT"


def make_ctx(
    *,
    idempotency_key: str | None = None,
    actor: str = "guardian:001",
    tenant_id: str = TENANT,
    family_id: str = FAMILY,
) -> ActionContext:
    """A human-actor context.

    `actor` defaults to a `guardian:` prefix on purpose — `assert_human_actor`
    rejects `ai:`-prefixed actors, so a test proving that rejection must pass
    `actor` explicitly instead of relying on this default.
    """
    return ActionContext(
        tenant_id=tenant_id,
        family_id=family_id,
        actor_person_id=GUARDIAN,
        actor=actor,
        correlation_id="corr-001",
        environment="TEST",
        idempotency_key=idempotency_key,
    )


async def seed_catalogue(repo) -> None:
    """Three earn rules and two redemption items, all PLATFORM scope.

    The rules are chosen to exercise the three interesting shapes: a capped
    daily rule, an uncapped one, and one that needs a qualification ref before
    it may pay out.
    """
    now = utcnow()
    audit = {
        "created_at": now,
        "created_by": "ops:seed",
        "updated_at": now,
        "updated_by": "ops:seed",
        "effective_from": now,
    }

    await repo.save_earn_rule(
        PointsEarnRule(
            rule_id="rule-checkin",
            rule_ref=RULE_CHECKIN,
            title="完成今日成长任务",
            explanation="每完成一次今日成长任务记录 20 分,每天最多 40 分。",
            source_kind="GROWTH_TASK_CHECKIN",
            points_per_event=20,
            daily_cap=40,
            **audit,
        )
    )
    await repo.save_earn_rule(
        PointsEarnRule(
            rule_id="rule-review",
            rule_ref=RULE_REVIEW,
            title="完成阶段复盘",
            explanation="每完成一次阶段复盘记录 100 分,不设每日上限。",
            source_kind="GROWTH_REVIEW_COMPLETED",
            points_per_event=100,
            **audit,
        )
    )
    await repo.save_earn_rule(
        PointsEarnRule(
            rule_id="rule-referral",
            rule_ref=RULE_REFERRAL,
            title="邀请的家庭已开始成长",
            explanation="被邀请的家庭真正开始成长后记录 200 分;仅发出邀请不计分。",
            source_kind="REFERRAL_QUALIFIED",
            points_per_event=200,
            requires_qualification=True,
            **audit,
        )
    )

    await repo.save_redemption_item(
        RedemptionCatalogItem(
            item_id="item-consult",
            item_ref=ITEM_CONSULTATION,
            title="一次专家咨询时段",
            reward_kind="CONSULTATION_SLOT",
            points_price=300,
            **audit,
        )
    )
    await repo.save_redemption_item(
        RedemptionCatalogItem(
            item_id="item-gift",
            item_ref=ITEM_GIFT,
            title="成长故事实体印本",
            reward_kind="PHYSICAL_GIFT",
            points_price=5000,
            **audit,
        )
    )
    await repo.commit()
