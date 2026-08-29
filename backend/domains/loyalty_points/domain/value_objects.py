"""Loyalty points value objects.

积分定性:**积分是"可追溯的参与资产",不是能力评价、不是货币、不是会籍阶梯。**

三个封闭枚举是这个域的治理骨架,不是方便的常量:

1. `SourceKind` —— 积分只能由这几类**已发生的参与事件**产生。孩子测评分、家庭分、
   任何排名都不在枚举里,`FORBIDDEN_EARN_SOURCE_KINDS` 再显式点名拒绝一次,
   这样错误信息能说清"为什么不行",而不是给一个 "unknown enum value"。
   依据:宪章 R9「AiFamily 不计算、不存储、不暴露家庭总分与家庭排行」。
2. `RewardKind` —— 兑换目录里**没有** `TIER_UPGRADE`。积分买不到会籍档位。
3. `EntryType` —— 台账只有这四种动作,每种的符号约束写在 `policies` 里。

本模块不 import `backend.domains.membership` 的任何东西,反向亦然。会籍档位 /
成长阶段 / 积分 / 社区身份四轴"可同时展示、不可互相换算",拆成互不依赖的包让这条
约束成为**包依赖图的事实**,而不是 code review 的口头承诺。
"""

from __future__ import annotations

from typing import Final, Literal

# --------------------------------------------------------------------------
# 账户与规则
# --------------------------------------------------------------------------

PointsAccountStatus = Literal["ACTIVE", "FROZEN", "CLOSED"]

ScopeType = Literal["PLATFORM", "TENANT"]

CatalogueStatus = Literal["DRAFT", "ACTIVE", "SUSPENDED", "RETIRED"]

SourceKind = Literal[
    "GROWTH_TASK_CHECKIN",       # 今日成长任务打卡
    "GROWTH_REVIEW_COMPLETED",   # 阶段复盘完成
    "SERVICE_COMPLETED",         # 一次服务真实发生并完成
    "ACTIVITY_ATTENDED",         # 沙龙 / 城市活动到场
    "REFERRAL_QUALIFIED",        # 邀请已被判定为合格(不是"发出邀请")
    "ADMIN_MANUAL_ADJUST",       # 人工兜底,须 human actor + reason_code
]

SOURCE_KINDS: Final[tuple[str, ...]] = (
    "GROWTH_TASK_CHECKIN",
    "GROWTH_REVIEW_COMPLETED",
    "SERVICE_COMPLETED",
    "ACTIVITY_ATTENDED",
    "REFERRAL_QUALIFIED",
    "ADMIN_MANUAL_ADJUST",
)

# 显式拒绝清单。这些值本来就不在 `SOURCE_KINDS` 里,单独列出是为了让拒绝**可测、可 grep**,
# 并且错误码能指出撞了哪条红线 —— 一个后来者想加"按测评分发积分"时,会先撞上这行。
FORBIDDEN_EARN_SOURCE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "CHILD_ASSESSMENT_SCORE",  # 禁 Child Score
        "FAMILY_SCORE",            # 禁 Family Total Score
        "GROWTH_SCORE",            # 禁成长分
        "FAMILY_RANKING",          # 禁家庭排行
        "TIER_LEVEL",              # 四轴分离:会籍不得换算成积分
        "COMMUNITY_ROLE",          # 四轴分离:社区身份不得换算成积分
    }
)

# 需要"已判定合格"前置的来源。邀请必须由 referral 域判定 QUALIFIED 之后才发分 ——
# 否则积分会变成"拉人头"的即时现金激励,与「价值优先、奖励辅助」相反。
QUALIFICATION_REQUIRED_SOURCE_KINDS: Final[frozenset[str]] = frozenset({"REFERRAL_QUALIFIED"})

# --------------------------------------------------------------------------
# 台账
# --------------------------------------------------------------------------

EntryType = Literal["EARN", "REDEEM", "EXPIRE", "ADJUST"]

ENTRY_TYPES: Final[tuple[str, ...]] = ("EARN", "REDEEM", "EXPIRE", "ADJUST")

# 每种台账动作的符号约束。ADJUST 不在此表 —— 它是唯一允许任意符号的类型,
# 代价是必须有人类 actor 与 reason_code(见 policies.assert_entry_type_sign)。
ENTRY_TYPE_SIGN: Final[dict[str, int]] = {"EARN": +1, "REDEEM": -1, "EXPIRE": -1}

# --------------------------------------------------------------------------
# 兑换
# --------------------------------------------------------------------------

RewardKind = Literal[
    "BENEFIT_GRANT",      # 换成一份会籍权益额度(由 membership 域自行发放,本域不写它)
    "CONTENT_ACCESS",     # 换内容访问
    "EVENT_SEAT",         # 换活动席位
    "CONSULTATION_SLOT",  # 换一次咨询时段
    "PHYSICAL_GIFT",      # 换实物
]

REWARD_KINDS: Final[tuple[str, ...]] = (
    "BENEFIT_GRANT",
    "CONTENT_ACCESS",
    "EVENT_SEAT",
    "CONSULTATION_SLOT",
    "PHYSICAL_GIFT",
)

# 同上,显式拒绝比"不在枚举里"更可测。
FORBIDDEN_REWARD_KINDS: Final[frozenset[str]] = frozenset(
    {
        "TIER_UPGRADE",      # 积分买不到会籍档位
        "MEMBERSHIP_TIER",
        "CASH",              # 不建现金钱包
        "CASH_WITHDRAWAL",
        "LOTTERY_TICKET",    # 禁抽奖 / 盲盒
        "BLIND_BOX",
    }
)

RedemptionStatus = Literal["REQUESTED", "FULFILLED", "CANCELLED"]

# --------------------------------------------------------------------------
# 生产边界
# --------------------------------------------------------------------------

Environment = Literal["DEV", "TEST"]
SourceSystem = Literal["TEST_NOOP_ADAPTER"]

# 积分台账的写入来源屏:UI-17 成长积分本屏、UI-15 邀请有礼、UI-30 年度陪伴的"积分与邀请"。
# 与 `backend/packages/contracts/ui_surfaces.POINTS_LEDGER_SOURCE_SURFACES` 保持一致。
LedgerSourcePageId = Literal["UI-15", "UI-17", "UI-30"]

AI_ACTOR_PREFIX: Final[str] = "ai:"
