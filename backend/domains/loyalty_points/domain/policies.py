"""Loyalty points invariants — one function per rule, testable without a repository.

The whole point of this module is that the ledger cannot be made to lie. Every
rule here answers a specific way a points system normally goes wrong:

| 规则 | 防的是什么 |
|---|---|
| `assert_earn_source_allowed` | 积分由孩子测评分/家庭分/排名产生 → 积分变成能力评价 |
| `assert_evidence_bound` | 无来源地发分 → 账本解释不了余额,家长看到 1280 分而账只有 800 |
| `assert_entry_type_sign` | EARN 是负数、REDEEM 是正数这类符号错位 |
| `assert_sufficient_balance` | 透支 |
| `assert_within_caps` | 刷分 / 无上限套利 |
| `assert_reward_kind_allowed` | 积分买会籍档位、换现金、抽奖 |
| `assert_human_actor` | AI 或系统悄悄调整余额 |
| `assert_no_score_semantics` | 从 `attributes` 旁路塞进 `family_score` |
| `compute_balance` | 存一列可被 UPDATE 的余额 |

`compute_balance` 是这里最重要的一条:**余额是台账的推导值,不是一个字段。**
没有可变余额列,就不存在"改余额"这个操作 —— 任何变动都必须留下一条能解释自己的账。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from .errors import (
    LoyaltyPointsConflictError,
    LoyaltyPointsForbiddenError,
    LoyaltyPointsValidationError,
)
from .value_objects import (
    AI_ACTOR_PREFIX,
    ENTRY_TYPE_SIGN,
    ENTRY_TYPES,
    FORBIDDEN_EARN_SOURCE_KINDS,
    FORBIDDEN_REWARD_KINDS,
    QUALIFICATION_REQUIRED_SOURCE_KINDS,
    REWARD_KINDS,
    SOURCE_KINDS,
)

# 字段名黑名单。由护栏测试反射本域全部实体与 ORM 列强制执行 —— 与 membership 的
# `FORBIDDEN_TIER_FIELD_TOKENS` 同一手法:在语义走偏之前先守住字段名。
# 注意 `value`/`worth` 这类折现词也在内:积分一旦被显示成钱,就从"我们家参与的证明"
# 退化为小额代金券。
FORBIDDEN_POINTS_FIELD_TOKENS: frozenset[str] = frozenset(
    {
        "score",
        "rank",
        "ranking",
        "level",
        "percentile",
        "grade",
        "cash",
        "worth",
        "money",
        "discount",
    }
)


def assert_human_actor(actor: str, *, code: str) -> None:
    """人工闸门。`ADJUST` 与冻结/关户这类动作只能由人做。

    宪章 R9:AI 只能产出 Perspective / Recommendation,永不得直写权威事实。
    这里检查的是 actor ref;调用方必须保证它来自认证会话而不是请求体 ——
    检查一个客户端自己填的字符串等于没检查。
    """
    if not actor or not actor.strip():
        raise LoyaltyPointsValidationError(f"{code}_actor_required")
    if actor.startswith(AI_ACTOR_PREFIX):
        raise LoyaltyPointsForbiddenError(f"{code}_requires_human_actor")


def assert_fixture_boundary(
    *, environment: str, source_system: str, external_effect: bool
) -> None:
    """生产边界。真实定价 / 真实支付 / 真实积分兑付属于另一次授权,
    本域跑不出真实副作用。"""
    if environment not in ("DEV", "TEST"):
        raise LoyaltyPointsForbiddenError(f"environment_not_allowed:{environment}")
    if source_system != "TEST_NOOP_ADAPTER":
        raise LoyaltyPointsForbiddenError(f"source_system_not_allowed:{source_system}")
    if external_effect:
        raise LoyaltyPointsForbiddenError("external_effect_not_allowed")


def assert_no_score_semantics(attributes: dict) -> None:
    """`attributes` 是唯一能塞任意键的扩展口子,所以单独守住它。"""
    for key in attributes:
        lowered = str(key).lower()
        for token in FORBIDDEN_POINTS_FIELD_TOKENS:
            if token in lowered:
                raise LoyaltyPointsForbiddenError(f"forbidden_attribute_semantics:{lowered}")


def assert_earn_source_allowed(source_kind: str) -> None:
    """发分来源必须是一类**已发生的参与事件**。

    先查拒绝清单再查允许清单,这样错误码能说清是撞了红线(测评分/家庭分/排名/
    四轴换算)还是只是拼错了枚举值。
    """
    if source_kind in FORBIDDEN_EARN_SOURCE_KINDS:
        raise LoyaltyPointsForbiddenError(f"earn_source_forbidden:{source_kind.lower()}")
    if source_kind not in SOURCE_KINDS:
        raise LoyaltyPointsValidationError(f"earn_source_unknown:{source_kind}")


def assert_reward_kind_allowed(reward_kind: str) -> None:
    """兑换目录不得包含会籍档位、现金、抽奖。

    membership 侧独立拒绝 `POINTS_*` 作为激活来源 —— 两边各自成立,不依赖对方,
    所以任一侧被改坏时另一侧仍然拦得住。
    """
    if reward_kind in FORBIDDEN_REWARD_KINDS:
        raise LoyaltyPointsForbiddenError(f"reward_kind_forbidden:{reward_kind.lower()}")
    if reward_kind not in REWARD_KINDS:
        raise LoyaltyPointsValidationError(f"reward_kind_unknown:{reward_kind}")


def assert_evidence_bound(
    *, entry_type: str, rule_ref: str | None, evidence_ref: str | None, reason_code: str | None
) -> None:
    """每一条账都必须能解释自己。

    `EARN` 要能回指"哪次打卡 / 哪次复盘 / 哪次服务完成";`EXPIRE`/`ADJUST` 要有
    `reason_code`。这条是把「推算不算证据」用在钱账上:没有来源的积分不发。
    """
    if entry_type == "EARN":
        if not rule_ref:
            raise LoyaltyPointsValidationError("earn_requires_rule_ref")
        if not evidence_ref:
            raise LoyaltyPointsValidationError("earn_requires_evidence_ref")
    if entry_type in ("EXPIRE", "ADJUST") and not reason_code:
        raise LoyaltyPointsValidationError(f"{entry_type.lower()}_requires_reason_code")


def assert_entry_type_sign(entry_type: str, points_delta: int) -> None:
    """符号约束。`ADJUST` 是唯一允许任意符号的类型,代价是它必须有人类 actor
    与 reason_code(由 `assert_human_actor` / `assert_evidence_bound` 分别把关)。"""
    if entry_type not in ENTRY_TYPES:
        raise LoyaltyPointsValidationError(f"entry_type_unknown:{entry_type}")
    if points_delta == 0:
        raise LoyaltyPointsValidationError("points_delta_must_not_be_zero")
    expected = ENTRY_TYPE_SIGN.get(entry_type)
    if expected is None:
        return  # ADJUST
    if (points_delta > 0) is not (expected > 0):
        raise LoyaltyPointsValidationError(
            f"entry_type_sign_mismatch:{entry_type}:{points_delta}"
        )


def assert_redemption_linked(entry_type: str, redemption_id: str | None) -> None:
    """`REDEEM` 必须挂在一张兑换单上,否则扣分没有对价。"""
    if entry_type == "REDEEM" and not redemption_id:
        raise LoyaltyPointsValidationError("redeem_requires_redemption_id")


def compute_balance(entries: Iterable) -> int:
    """余额 = SUM(points_delta)。

    这是本域唯一的余额来源。不存可变余额列,所以不存在"改余额"这个操作;
    每一分的来去都必须有一条账。
    """
    return sum(entry.points_delta for entry in entries)


def assert_sufficient_balance(*, balance: int, points_delta: int) -> int:
    """不透支。返回变动后余额,供调用方写入 `balance_after` 快照。"""
    after = balance + points_delta
    if after < 0:
        raise LoyaltyPointsConflictError(f"insufficient_points_balance:{balance}{points_delta:+d}")
    return after


def assert_within_caps(
    *,
    rule_ref: str,
    points_per_event: int,
    daily_cap: int | None,
    total_cap: int | None,
    earned_today: int,
    earned_total: int,
) -> None:
    """上限与反作弊写在规则对象上,不写成代码分支。

    这样"这条规则每天最多给多少分"是一条**可审计的数据**,运营改上限不需要改代码,
    而审计者不必读代码才能知道上限是多少。
    """
    if points_per_event <= 0:
        raise LoyaltyPointsValidationError(f"points_per_event_must_be_positive:{rule_ref}")
    if daily_cap is not None and earned_today + points_per_event > daily_cap:
        raise LoyaltyPointsConflictError(f"daily_cap_exceeded:{rule_ref}:{daily_cap}")
    if total_cap is not None and earned_total + points_per_event > total_cap:
        raise LoyaltyPointsConflictError(f"total_cap_exceeded:{rule_ref}:{total_cap}")


def assert_qualification_present(
    *, source_kind: str, requires_qualification: bool, qualification_ref: str | None
) -> None:
    """合格前置。邀请必须先被判定合格才发分 —— 否则积分退化成"拉人头"的即时奖励,
    与「价值优先、奖励辅助」相反,也正是解读裁决要求的反作弊闸门。
    """
    needs = requires_qualification or source_kind in QUALIFICATION_REQUIRED_SOURCE_KINDS
    if needs and not qualification_ref:
        raise LoyaltyPointsForbiddenError(f"qualification_required:{source_kind.lower()}")


def earned_on_day(entries: Iterable, *, rule_ref: str, day: date) -> int:
    """某条规则在某一天已发放的分数。

    已知缺口(明说而不藏):`occurred_at` 是 naive UTC,所以"今日"按 UTC 日聚合,
    与家庭所在时区的自然日可能错开几小时。时区归属应由 Family Account 决定,
    不该由积分域猜一个 —— 等 Account 域能提供家庭时区后再改这里。
    """
    return sum(
        e.points_delta
        for e in entries
        if e.entry_type == "EARN" and e.rule_ref == rule_ref and e.occurred_at.date() == day
    )


def earned_total_for_rule(entries: Iterable, *, rule_ref: str) -> int:
    return sum(e.points_delta for e in entries if e.entry_type == "EARN" and e.rule_ref == rule_ref)
