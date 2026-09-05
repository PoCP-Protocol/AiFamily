"""每条台账不变量一个用例。

这些是"拒绝错误的事"的测试。上面的验收链证明域能跑通;这里证明它**跑不通**该拒绝的路径 ——
后者才是治理红线真正落地的地方。每个用例的 docstring 写清它防的是哪种失败。
"""

from __future__ import annotations

import pytest

from backend.domains.loyalty_points.application import commands
from backend.domains.loyalty_points.domain.entities import (
    PointsEarnRule,
    PointsLedgerEntry,
    RedemptionCatalogItem,
    utcnow,
)
from backend.domains.loyalty_points.domain.errors import (
    LoyaltyPointsConflictError,
    LoyaltyPointsForbiddenError,
    LoyaltyPointsValidationError,
)
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


async def _opened(repo):
    await seed_catalogue(repo)
    await commands.open_points_account(repo, make_ctx(), account_ref="ACCT-INV")


# --------------------------------------------------------------------------
# 发分侧
# --------------------------------------------------------------------------


async def test_earn_requires_evidence(repo) -> None:
    """无证据不发分。没有 evidence_ref 的积分,账本解释不了它为什么存在。"""
    await _opened(repo)
    with pytest.raises(LoyaltyPointsValidationError, match="earn_requires_evidence_ref"):
        await commands.earn_points(
            repo,
            make_ctx(idempotency_key="no-evidence"),
            rule_ref=RULE_CHECKIN,
            evidence_ref="",
            source_page_id="UI-17",
        )


async def test_daily_cap_is_enforced(repo) -> None:
    """刷分闸门。上限写在规则对象上,是可审计的数据,不是代码分支。"""
    await _opened(repo)
    for i in range(2):  # 2 × 20 = 40,正好打满 daily_cap
        await commands.earn_points(
            repo,
            make_ctx(idempotency_key=f"cap-{i}"),
            rule_ref=RULE_CHECKIN,
            evidence_ref=f"growth_action:day-1:{i}",
            source_page_id="UI-17",
        )
    with pytest.raises(LoyaltyPointsConflictError, match="daily_cap_exceeded"):
        await commands.earn_points(
            repo,
            make_ctx(idempotency_key="cap-3"),
            rule_ref=RULE_CHECKIN,
            evidence_ref="growth_action:day-1:3",
            source_page_id="UI-17",
        )


async def test_referral_points_need_a_qualification(repo) -> None:
    """仅"发出邀请"不计分,必须已被判定合格。

    否则积分就变成"拉人头"的即时现金激励 —— 与 `[宣发P9]`「价值优先,奖励辅助」相反,
    也正是解读裁决要求的反作弊闸门。
    """
    await _opened(repo)
    with pytest.raises(LoyaltyPointsForbiddenError, match="qualification_required"):
        await commands.earn_points(
            repo,
            make_ctx(idempotency_key="ref-noqual"),
            rule_ref=RULE_REFERRAL,
            evidence_ref="referral:invite-1",
            source_page_id="UI-15",
        )


FORBIDDEN_SOURCES = ("CHILD_ASSESSMENT_SCORE", "FAMILY_SCORE", "FAMILY_RANKING", "TIER_LEVEL")


@pytest.mark.parametrize("forbidden", FORBIDDEN_SOURCES)
def test_forbidden_earn_source_is_rejected_at_the_entity(forbidden: str) -> None:
    """积分不得由孩子测评分 / 家庭分 / 排名产生 —— 宪章 R9。

    第一道闸门是 Pydantic 的 `Literal[SourceKind]`:它在 `model_validator` 之前就
    拒掉了未登记的值,所以一条违宪的规则连内存对象都建不出来。
    """
    now = utcnow()
    with pytest.raises(ValueError):  # pydantic ValidationError 是 ValueError 子类
        PointsEarnRule(
            rule_id="rule-x",
            rule_ref="X",
            title="x",
            explanation="x",
            source_kind=forbidden,  # type: ignore[arg-type]
            points_per_event=10,
            effective_from=now,
            created_at=now,
            created_by="ops",
            updated_at=now,
            updated_by="ops",
        )


@pytest.mark.parametrize("forbidden", FORBIDDEN_SOURCES)
def test_forbidden_earn_source_deny_list_explains_itself(forbidden: str) -> None:
    """第二道闸门是显式拒绝清单,它才是**可解释**的那一道。

    `Literal` 只会说 "不是合法值";`assert_earn_source_allowed` 会说
    `earn_source_forbidden:family_score` —— 一个后来者想加"按测评分发积分"时,
    看到的是撞了哪条红线,而不是一个枚举拼写错误。
    这条路径在实践中并非无用:原始字符串会从数据库行、旧数据迁移和 API payload
    进来,那些地方走不到 Pydantic 的类型校验。
    """
    from backend.domains.loyalty_points.domain.policies import assert_earn_source_allowed

    with pytest.raises(LoyaltyPointsForbiddenError, match="earn_source_forbidden"):
        assert_earn_source_allowed(forbidden)


async def test_rule_without_explanation_is_rejected() -> None:
    """规则必须可解释。家庭无法知道自己为什么得分,积分就不是"可追溯的参与资产"。"""
    now = utcnow()
    with pytest.raises(LoyaltyPointsValidationError, match="rule_requires_explanation"):
        PointsEarnRule(
            rule_id="rule-y",
            rule_ref="Y",
            title="y",
            explanation="   ",
            source_kind="GROWTH_TASK_CHECKIN",
            points_per_event=10,
            effective_from=now,
            created_at=now,
            created_by="ops",
            updated_at=now,
            updated_by="ops",
        )


async def test_frozen_account_cannot_earn(repo) -> None:
    """冻结停止收发,但不销毁任何东西 —— 家庭做过什么的记录不是执法杠杆。"""
    await _opened(repo)
    account = await repo.find_account(TENANT, FAMILY)
    await repo.save_account(account.freeze(actor="ops:risk", reason="疑似异常刷分,待核查"))
    await repo.commit()

    with pytest.raises(LoyaltyPointsConflictError, match="points_account_not_active:FROZEN"):
        await commands.earn_points(
            repo,
            make_ctx(idempotency_key="frozen-1"),
            rule_ref=RULE_CHECKIN,
            evidence_ref="growth_action:day-2",
            source_page_id="UI-17",
        )
    # 台账仍然完整。
    assert await repo.list_ledger(TENANT, FAMILY) == []


async def test_ai_actor_cannot_freeze_an_account(repo) -> None:
    await _opened(repo)
    account = await repo.find_account(TENANT, FAMILY)
    with pytest.raises(LoyaltyPointsForbiddenError, match="requires_human_actor"):
        account.freeze(actor="ai:risk.model", reason="模型判定异常")


# --------------------------------------------------------------------------
# 花分侧
# --------------------------------------------------------------------------


async def test_balance_can_never_go_negative(repo) -> None:
    """不透支。余额是推导值,所以"透支"只能在写入前被拒,而不是事后修一列数字。"""
    await _opened(repo)
    with pytest.raises(LoyaltyPointsConflictError, match="insufficient_points_balance"):
        await commands.redeem_points(
            repo,
            make_ctx(idempotency_key="over-1"),
            item_ref=ITEM_CONSULTATION,  # 300 分,账上 0 分
            redemption_ref="REDEEM-OVER",
            source_page_id="UI-17",
        )
    assert await repo.list_ledger(TENANT, FAMILY) == []
    assert await repo.list_redemptions(TENANT, FAMILY) == []


async def test_expire_more_than_balance_is_refused(repo) -> None:
    await _opened(repo)
    await commands.earn_points(
        repo,
        make_ctx(idempotency_key="exp-earn"),
        rule_ref=RULE_CHECKIN,
        evidence_ref="growth_action:day-1",
        source_page_id="UI-17",
    )
    with pytest.raises(LoyaltyPointsConflictError, match="insufficient_points_balance"):
        await commands.expire_points(
            repo,
            make_ctx(idempotency_key="exp-1"),
            points=999,
            reason_code="VALIDITY_ENDED",
            source_page_id="UI-17",
        )


async def test_expire_requires_a_reason_code(repo) -> None:
    """过期必须能解释。静默清零是摧毁积分体系信任最快的方式。"""
    await _opened(repo)
    now = utcnow()
    with pytest.raises(LoyaltyPointsValidationError, match="expire_requires_reason_code"):
        PointsLedgerEntry(
            ledger_id="l-1",
            tenant_id=TENANT,
            family_id=FAMILY,
            points_account_id="pacct-1",
            actor_person_id="p-1",
            ledger_ref="expire:x",
            entry_type="EXPIRE",
            points_delta=-10,
            balance_after=0,
            source_page_id="UI-17",
            environment="TEST",
            correlation_id="c",
            occurred_at=now,
            created_at=now,
            created_by="ops",
        )


async def test_adjust_requires_a_human_actor(repo) -> None:
    """人工调整必须由人负责 —— AI 可以建议,不能改账(宪章 R9)。"""
    await _opened(repo)
    with pytest.raises(LoyaltyPointsForbiddenError, match="requires_human_actor"):
        await commands.adjust_points(
            repo,
            make_ctx(idempotency_key="adj-ai"),
            points_delta=100,
            reason_code="MODEL_SUGGESTED",
            source_page_id="UI-17",
            decided_by="ai:points.optimizer",
        )


FORBIDDEN_REWARDS = ("TIER_UPGRADE", "MEMBERSHIP_TIER", "CASH", "LOTTERY_TICKET", "BLIND_BOX")


@pytest.mark.parametrize("forbidden", FORBIDDEN_REWARDS)
def test_forbidden_reward_kind_is_rejected_at_the_entity(forbidden: str) -> None:
    """积分买不到会籍档位(基线转换不变量 4),也换不到现金、抽奖、盲盒。

    membership 侧独立拒绝 `POINTS_*` 作为激活来源 —— 两边各自成立、互不依赖,
    所以任一侧被改坏时另一侧仍然拦得住。
    """
    now = utcnow()
    with pytest.raises(ValueError):
        RedemptionCatalogItem(
            item_id="item-x",
            item_ref="X",
            title="x",
            reward_kind=forbidden,  # type: ignore[arg-type]
            points_price=100,
            effective_from=now,
            created_at=now,
            created_by="ops",
            updated_at=now,
            updated_by="ops",
        )


@pytest.mark.parametrize("forbidden", FORBIDDEN_REWARDS)
def test_forbidden_reward_kind_deny_list_explains_itself(forbidden: str) -> None:
    from backend.domains.loyalty_points.domain.policies import assert_reward_kind_allowed

    with pytest.raises(LoyaltyPointsForbiddenError, match="reward_kind_forbidden"):
        assert_reward_kind_allowed(forbidden)


# --------------------------------------------------------------------------
# 台账形状
# --------------------------------------------------------------------------


async def test_entry_type_sign_must_match(repo) -> None:
    """符号错位会让余额悄悄反向。ADJUST 是唯一允许任意符号的类型。"""
    now = utcnow()
    common = {
        "tenant_id": TENANT,
        "family_id": FAMILY,
        "points_account_id": "pacct-1",
        "actor_person_id": "p-1",
        "source_page_id": "UI-17",
        "environment": "TEST",
        "correlation_id": "c",
        "occurred_at": now,
        "created_at": now,
        "created_by": "guardian:001",
    }
    with pytest.raises(LoyaltyPointsValidationError, match="entry_type_sign_mismatch"):
        PointsLedgerEntry(
            ledger_id="l-2",
            ledger_ref="r",
            entry_type="EARN",
            points_delta=-10,
            balance_after=0,
            rule_ref=RULE_REVIEW,
            evidence_ref="e",
            **common,
        )
    with pytest.raises(LoyaltyPointsValidationError, match="points_delta_must_not_be_zero"):
        PointsLedgerEntry(
            ledger_id="l-3",
            ledger_ref="r",
            entry_type="ADJUST",
            points_delta=0,
            balance_after=0,
            reason_code="x",
            **common,
        )


async def test_redeem_entry_must_be_linked_to_a_redemption() -> None:
    """扣分必须有对价。"""
    now = utcnow()
    with pytest.raises(LoyaltyPointsValidationError, match="redeem_requires_redemption_id"):
        PointsLedgerEntry(
            ledger_id="l-4",
            tenant_id=TENANT,
            family_id=FAMILY,
            points_account_id="pacct-1",
            actor_person_id="p-1",
            ledger_ref="r",
            entry_type="REDEEM",
            points_delta=-10,
            balance_after=0,
            source_page_id="UI-17",
            environment="TEST",
            correlation_id="c",
            occurred_at=now,
            created_at=now,
            created_by="guardian:001",
        )


async def test_points_cannot_move_from_an_unrelated_surface(repo) -> None:
    """积分只能从真正展示积分的屏发生变动(UI-15 / UI-17 / UI-30)。"""
    await _opened(repo)
    with pytest.raises(LoyaltyPointsForbiddenError, match="ledger_source_surface_forbidden"):
        await commands.earn_points(
            repo,
            make_ctx(idempotency_key="surface-1"),
            rule_ref=RULE_CHECKIN,
            evidence_ref="growth_action:day-1",
            source_page_id="UI-02",  # 家庭测评屏不该能发积分
        )


async def test_fixture_boundary_refuses_production(repo) -> None:
    """生产边界:真实定价/支付/兑付属于另一次授权,本域跑不出真实副作用。

    两层都验:实体上的 `Literal["DEV","TEST"]` 让 `PRODUCTION` 建不出对象,
    而 `assert_fixture_boundary` 是那条**能解释自己**的闸门 —— 它同时守住
    `source_system` 与 `external_effect`,那两个字段的类型无法表达"必须是 false"。
    """
    from backend.domains.loyalty_points.application.context import ActionContext
    from backend.domains.loyalty_points.domain.policies import assert_fixture_boundary

    ctx = ActionContext(
        tenant_id=TENANT,
        family_id=FAMILY,
        actor_person_id="p-1",
        actor="guardian:001",
        correlation_id="c",
        environment="PRODUCTION",  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError):
        await commands.open_points_account(repo, ctx, account_ref="ACCT-PROD")

    with pytest.raises(LoyaltyPointsForbiddenError, match="environment_not_allowed"):
        assert_fixture_boundary(
            environment="PRODUCTION", source_system="TEST_NOOP_ADAPTER", external_effect=False
        )
    with pytest.raises(LoyaltyPointsForbiddenError, match="external_effect_not_allowed"):
        assert_fixture_boundary(
            environment="TEST", source_system="TEST_NOOP_ADAPTER", external_effect=True
        )
    with pytest.raises(LoyaltyPointsForbiddenError, match="source_system_not_allowed"):
        assert_fixture_boundary(
            environment="TEST", source_system="REAL_PAYMENT_GATEWAY", external_effect=False
        )


# --------------------------------------------------------------------------
# 幂等
# --------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["earn", "expire", "adjust"])
async def test_replaying_a_command_does_not_double_write(repo, action: str) -> None:
    """重放返回同一条账,而不是报错、也不是记两笔。"""
    await _opened(repo)
    await commands.earn_points(
        repo,
        make_ctx(idempotency_key="seed-earn"),
        rule_ref=RULE_REVIEW,
        evidence_ref="growth_review:cycle-1",
        source_page_id="UI-17",
    )
    before = len(await repo.list_ledger(TENANT, FAMILY))

    key = f"replay-{action}"
    if action == "earn":
        call = lambda: commands.earn_points(  # noqa: E731 - 三个签名不同,lambda 最直白
            repo,
            make_ctx(idempotency_key=key),
            rule_ref=RULE_CHECKIN,
            evidence_ref="growth_action:day-9",
            source_page_id="UI-17",
        )
    elif action == "expire":
        call = lambda: commands.expire_points(  # noqa: E731
            repo,
            make_ctx(idempotency_key=key),
            points=10,
            reason_code="VALIDITY_ENDED",
            source_page_id="UI-17",
        )
    else:
        call = lambda: commands.adjust_points(  # noqa: E731
            repo,
            make_ctx(idempotency_key=key),
            points_delta=7,
            reason_code="SUPPORT_TICKET_1",
            source_page_id="UI-17",
            decided_by="ops:support.zhang",
        )

    first = await call()
    second = await call()
    assert first.ledger_id == second.ledger_id
    assert len(await repo.list_ledger(TENANT, FAMILY)) == before + 1


async def test_replaying_a_redemption_returns_the_same_pair(repo) -> None:
    await _opened(repo)
    for i in range(3):
        await commands.earn_points(
            repo,
            make_ctx(idempotency_key=f"rr-{i}"),
            rule_ref=RULE_REVIEW,
            evidence_ref=f"growth_review:cycle-{i}",
            source_page_id="UI-17",
        )
    first_redemption, first_entry = await commands.redeem_points(
        repo,
        make_ctx(idempotency_key="rr-redeem"),
        item_ref=ITEM_CONSULTATION,
        redemption_ref="REDEEM-RR",
        source_page_id="UI-17",
    )
    second_redemption, second_entry = await commands.redeem_points(
        repo,
        make_ctx(idempotency_key="rr-redeem"),
        item_ref=ITEM_CONSULTATION,
        redemption_ref="REDEEM-RR",
        source_page_id="UI-17",
    )
    assert first_redemption.redemption_id == second_redemption.redemption_id
    assert first_entry.ledger_id == second_entry.ledger_id
    assert len(await repo.list_redemptions(TENANT, FAMILY)) == 1


async def test_opening_an_account_twice_returns_the_same_account(repo) -> None:
    """两个账户会把一个家庭的台账劈成两半。"""
    await seed_catalogue(repo)
    first = await commands.open_points_account(repo, make_ctx(), account_ref="ACCT-A")
    second = await commands.open_points_account(repo, make_ctx(), account_ref="ACCT-B")
    assert first.points_account_id == second.points_account_id
