"""Emotional-value-first block ordering.

Project owner ruling (2026-08-29):

    这个平台首先给用户带来情绪价值,然后再给用户带来经济价值。

This is an ordering rule, and it lands exactly where commerce code is most
likely to get it backwards — the default way to write a membership screen is
balance, quota, price, discount first. That is economic value first.

So the order is data shared by backend and frontend, not a layout decision made
independently on each screen. `blocks` in every `ScreenView` is an ordered dict
built in this order; the frontend renders in payload order rather than
re-sorting, which is what keeps UI-06 / UI-18 / UI-30 from each inventing a
different emphasis (the failure mode `FAMILY_MEMBERSHIP_OS_V2_BASELINE.md`
§UI Contract names).

Grounding: `FAMILY_COMMERCIAL_VALUE_STRATEGY_V2.md:27` ("家是港湾,孩子是希望"),
`[白皮书P5]` ("用户真正购买的不是 AI,而是孩子改变和家庭关系改善的确定性").
"""

from __future__ import annotations

from typing import Final

# Ordered from most emotional to most transactional. A block name not in this
# list sorts after everything listed (i.e. defaults to the transactional end),
# which is the safe direction: a new unclassified block cannot accidentally
# jump ahead of the relationship blocks.
EMOTIONAL_FIRST_BLOCK_ORDER: Final[tuple[str, ...]] = (
    # 1. 你们家走到哪了 / 被谁陪着 —— 关系与陪伴
    "当前方案",
    "会员状态",
    "年度计划",
    "陪伴关系",
    # 2. 你们家做到了什么 —— 不可撤销的事实,数字会花掉,事实不会
    "里程碑",
    "积分任务",
    "权益账本",
    "已领取",
    # 3. 你们家拥有什么 —— 价值兑现
    "成长权益",
    "会员权益",
    "可用权益",
    "已激活权益",
    "服务入口",
    "方案意向",
    "成长报告",
    "课程资产",
    "积分与邀请",
    # 4. 数字与期限 —— 最后
    "服务额度",
    "有效期",
    "规则说明",
    "续费意向",
)

_ORDER_INDEX: Final[dict[str, int]] = {
    name: i for i, name in enumerate(EMOTIONAL_FIRST_BLOCK_ORDER)
}


def order_blocks(blocks: dict) -> dict:
    """Return `blocks` re-inserted in emotional-first order.

    Python dicts preserve insertion order, so rebuilding the dict *is* the
    contract — the JSON body reaches the client already ordered and the client
    does not need to know the rule.
    """
    return {
        key: blocks[key]
        for key in sorted(blocks, key=lambda k: (_ORDER_INDEX.get(k, len(_ORDER_INDEX)), str(k)))
    }


# Points must never be expressed as money. Once a family sees "≈¥12.80", the
# points stop being evidence of what the family did and become a small-value
# coupon — emotional value gone, and `[宣发P9]`「价值优先,奖励辅助」inverted.
FORBIDDEN_CASH_EQUIVALENCE_TOKENS: Final[frozenset[str]] = frozenset(
    {"cash_value", "cash_equivalent", "money_value", "worth", "discount_amount", "deduction_amount"}
)

FORBIDDEN_CASH_EQUIVALENCE_COPY: Final[tuple[str, ...]] = (
    "≈¥",
    "约合",
    "抵扣",
    "可抵",
    "折现",
    "等值",
)


def assert_no_cash_equivalence(payload_keys: object, notices: object) -> None:
    """Raise `ValueError` if a points payload expresses points as currency.

    Used by the guardrail test, same pattern as
    `gamification.assert_gamification_safe`.
    """
    for key in payload_keys:  # type: ignore[union-attr]
        lowered = str(key).lower()
        for token in FORBIDDEN_CASH_EQUIVALENCE_TOKENS:
            if token in lowered:
                raise ValueError(f"forbidden_cash_equivalence_key:{lowered}")
    for notice in notices:  # type: ignore[union-attr]
        for phrase in FORBIDDEN_CASH_EQUIVALENCE_COPY:
            if phrase in str(notice):
                raise ValueError(f"forbidden_cash_equivalence_copy:{phrase}")
