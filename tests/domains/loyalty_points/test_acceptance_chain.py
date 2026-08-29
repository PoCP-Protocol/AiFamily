"""End-to-end acceptance chain for loyalty points, run against both repositories.

    开户 → 按规则发分(绑证据) → 兑换 → 过期 → 人工调整 → UI-17 读模型

The single most important assertion in this file is `test_balance_is_derived_not_stored`:
it pins the ledger sum to the last entry's `balance_after` snapshot. If those two
ever disagree, a family sees a number the ledger cannot explain — the worst
failure mode a points system has.
"""

from __future__ import annotations

from backend.domains.loyalty_points.application import commands, queries
from backend.domains.loyalty_points.domain.policies import compute_balance

from tests.domains.loyalty_points.helpers import (
    FAMILY,
    ITEM_CONSULTATION,
    RULE_CHECKIN,
    RULE_REFERRAL,
    RULE_REVIEW,
    TENANT,
    make_ctx,
    seed_catalogue,
)


async def test_full_points_chain(repo) -> None:
    await seed_catalogue(repo)

    account = await commands.open_points_account(
        repo, make_ctx(idempotency_key="acct-1"), account_ref="ACCT-FAMILY-001"
    )
    assert account.status == "ACTIVE"
    # 账户上没有余额字段可看 —— 余额只能从台账算出来。
    assert not hasattr(account, "balance")

    # 发分:调用方给的是规则 + 证据,不是金额。
    checkin = await commands.earn_points(
        repo,
        make_ctx(idempotency_key="earn-1"),
        rule_ref=RULE_CHECKIN,
        evidence_ref="growth_action:2026-08-29:completed",
        source_page_id="UI-17",
    )
    assert (checkin.points_delta, checkin.balance_after) == (20, 20)
    assert checkin.evidence_ref == "growth_action:2026-08-29:completed"

    review = await commands.earn_points(
        repo,
        make_ctx(idempotency_key="earn-2"),
        rule_ref=RULE_REVIEW,
        evidence_ref="growth_review:cycle-1:completed",
        source_page_id="UI-17",
    )
    assert (review.points_delta, review.balance_after) == (100, 120)

    referral = await commands.earn_points(
        repo,
        make_ctx(idempotency_key="earn-3"),
        rule_ref=RULE_REFERRAL,
        evidence_ref="referral:invite-77",
        qualification_ref="referral_qualification:invite-77:QUALIFIED",
        source_page_id="UI-15",
    )
    assert (referral.points_delta, referral.balance_after) == (200, 320)

    # 兑换:兑换单与扣分台账在同一个工作单元里落地。
    redemption, debit = await commands.redeem_points(
        repo,
        make_ctx(idempotency_key="redeem-1"),
        item_ref=ITEM_CONSULTATION,
        redemption_ref="REDEEM-001",
        source_page_id="UI-17",
    )
    assert (redemption.status, redemption.points_spent) == ("REQUESTED", 300)
    assert (debit.entry_type, debit.points_delta, debit.balance_after) == ("REDEEM", -300, 20)
    assert debit.redemption_id == redemption.redemption_id

    # 过期:是一条能解释自己的账,不是静默清零。
    expiry = await commands.expire_points(
        repo,
        make_ctx(idempotency_key="expire-1"),
        points=10,
        reason_code="POINTS_VALIDITY_ENDED_2026Q3",
        source_page_id="UI-17",
    )
    assert (expiry.entry_type, expiry.points_delta, expiry.balance_after) == ("EXPIRE", -10, 10)
    assert expiry.reason_code == "POINTS_VALIDITY_ENDED_2026Q3"

    # 人工调整:唯一允许任意符号的类型,代价是人类 actor + reason_code。
    adjust = await commands.adjust_points(
        repo,
        make_ctx(idempotency_key="adjust-1"),
        points_delta=5,
        reason_code="SUPPORT_TICKET_4821_COMPENSATION",
        source_page_id="UI-17",
        decided_by="ops:support.zhang",
    )
    assert (adjust.entry_type, adjust.points_delta, adjust.balance_after) == ("ADJUST", 5, 15)
    assert adjust.created_by == "ops:support.zhang"

    entries = await repo.list_ledger(TENANT, FAMILY)
    assert sorted(e.entry_type for e in entries) == [
        "ADJUST",
        "EARN",
        "EARN",
        "EARN",
        "EXPIRE",
        "REDEEM",
    ]
    assert compute_balance(entries) == 15


async def test_balance_is_derived_not_stored(repo) -> None:
    """余额 = SUM(points_delta),而每条 `balance_after` 只是写入瞬间的快照事实。
    这条测试把两者钉在一起:任何一侧漂移,家长看到的数字就解释不了。"""
    await seed_catalogue(repo)
    await commands.open_points_account(repo, make_ctx(), account_ref="ACCT-2")

    for i, (rule, evidence) in enumerate(
        [
            (RULE_CHECKIN, "growth_action:day-1"),
            (RULE_REVIEW, "growth_review:cycle-1"),
        ]
    ):
        await commands.earn_points(
            repo,
            make_ctx(idempotency_key=f"derive-{i}"),
            rule_ref=rule,
            evidence_ref=evidence,
            source_page_id="UI-17",
        )

    entries = sorted(await repo.list_ledger(TENANT, FAMILY), key=lambda e: e.occurred_at)
    assert compute_balance(entries) == entries[-1].balance_after

    # 逐条重放:每条快照都等于它之前所有 delta 的和。
    running = 0
    for entry in entries:
        running += entry.points_delta
        assert entry.balance_after == running


async def test_ui17_projection_shape_and_gamification_fields(repo) -> None:
    """UI-17 的四个块名必须与前端 featurePoints 一致,并带上游戏化所需字段。"""
    await seed_catalogue(repo)
    await commands.open_points_account(repo, make_ctx(), account_ref="ACCT-3")
    await commands.earn_points(
        repo,
        make_ctx(idempotency_key="ui17-1"),
        rule_ref=RULE_CHECKIN,
        evidence_ref="growth_action:day-1",
        source_page_id="UI-17",
    )

    screen = await queries.get_ui17_growth_points(repo, tenant_id=TENANT, family_id=FAMILY)
    assert screen.surface_id == "UI-17"
    assert screen.feature_points == ["积分任务", "权益账本", "已领取", "规则说明"]
    assert set(screen.blocks) == {"积分任务", "权益账本", "已领取", "规则说明"}

    # 情绪价值优先:"你们家做到了什么"在"数字与规则"之前。
    block_order = list(screen.blocks)
    assert block_order.index("积分任务") < block_order.index("规则说明")
    assert block_order.index("权益账本") < block_order.index("规则说明")

    tasks = screen.blocks["积分任务"]["tasks"]
    checkin_task = next(t for t in tasks if t["rule_ref"] == RULE_CHECKIN)
    # 上限对家庭可见,而不是让家庭撞上去才知道。
    assert (checkin_task["daily_cap"], checkin_task["earned_today"]) == (40, 20)
    assert checkin_task["remaining_today"] == 20
    assert checkin_task["explanation"]

    assert screen.blocks["积分任务"]["streak_days"] == 1
    ledger_block = screen.blocks["权益账本"]
    assert ledger_block["balance"] == 20
    assert ledger_block["entries"][0]["evidence_ref"] == "growth_action:day-1"
    # 里程碑绑定已发生的事实,带 evidence_ref。
    assert ledger_block["milestones"][0]["code"] == "FIRST_PARTICIPATION_RECORDED"
    assert ledger_block["milestones"][0]["evidence_ref"] == "growth_action:day-1"

    assert screen.blocks["规则说明"]["redeemable_for_membership_tier"] is False
    catalogue = screen.blocks["已领取"]["catalogue"]
    assert {c["item_ref"]: c["affordable"] for c in catalogue} == {
        ITEM_CONSULTATION: False,
        "GROWTH_STORY_PRINT": False,
    }


async def test_projection_is_family_private_and_empty_state_is_honest(repo) -> None:
    await seed_catalogue(repo)
    projection = await queries.get_points_projection(repo, tenant_id=TENANT, family_id=FAMILY)
    assert projection.visibility == "FAMILY_PRIVATE"
    assert projection.account_status is None
    assert projection.balance == 0
    assert projection.text_equivalent == "本家庭还没有成长积分记录。"
    assert projection.milestones == []
