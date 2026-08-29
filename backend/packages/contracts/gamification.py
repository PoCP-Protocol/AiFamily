"""Gamification contract — machine-readable form of
`architecture/FAMILY_COMMERCE_MEMBERSHIP_POINTS_ARCHITECTURE_V1.md` §4.4.

Gamification is a positive requirement (`[合作方案P5]` "带游戏化、积分商城逻辑的
用户交互端口"; `[宣发P13]` "身份等级 → 强化身份认同"), and it is also the single
easiest place in this codebase to violate the platform's hard rules by accident:
one mis-drawn progress bar turns "participation feedback" into "a score for the
child".

So the line is drawn as data, not as a comment:

    可以量化"我们家做了什么",绝不量化"我们家(或孩子)有多好"。

`FORBIDDEN_GAMIFICATION_KEY_TOKENS` is asserted against every read-model key
and notice string by `tests/test_gamification_guardrail.py`, so a future
read-model field called `family_rank` or `tier_progress_pct` fails the build
rather than shipping.
"""

from __future__ import annotations

from typing import Final, NamedTuple


class GamificationPattern(NamedTuple):
    key: str
    label: str
    fact_source: str
    why_safe: str


# Each allowed pattern names the append-only fact it must be derived from.
# Nothing here is a standalone counter: if a number cannot be recomputed from a
# ledger row or a period record, it must not be shown. The failure mode being
# prevented is the worst one — a parent sees 1,280 points while the ledger can
# only account for 800.
ALLOWED_GAMIFICATION_PATTERNS: Final[tuple[GamificationPattern, ...]] = (
    GamificationPattern(
        "points_earn_feed",
        "积分获取事件流(可做 +20 飘字/领取动效)",
        "loyalty_points ledger, entry_type=EARN",
        "每条都是一次真实参与事件,带 evidence_ref",
    ),
    GamificationPattern(
        "points_task_remaining_today",
        "今日还可获得的积分(任务清单)",
        "PointsEarnRule.daily_cap − 今日已得",
        "表达规则透明度,[宣发P9]『信息透明』",
    ),
    GamificationPattern(
        "participation_streak_days",
        "连续参与天数 / 打卡日历",
        "ledger EARN 按天聚合",
        "计行为频次,不计能力",
    ),
    GamificationPattern(
        "cycle_completion_progress",
        "21天/90天周期完成进度环",
        "growth domain task facts(本域只并列展示)",
        "任务完成度,[白皮书P14] 完课率/打卡率即此物",
    ),
    GamificationPattern(
        "evidence_bound_milestones",
        "里程碑徽章(首次复盘、首个周期收官、首次合格邀请)",
        "ledger + MembershipPeriod 收官 + referral QUALIFIED",
        "每枚绑一个已发生事件,不可撤销地属于这个家庭",
    ),
    GamificationPattern(
        "benefit_three_state",
        "权益『可领取/已领取/已使用』三态",
        "BenefitGrant.status + remaining_units",
        "[宣发P15]『用户不知道自己拥有什么』正是要解决的痛点",
    ),
    GamificationPattern(
        "community_role_badge",
        "社区身份(成长伙伴/分享官/城市发起人)",
        "community domain(本域只并列展示,不换算)",
        "[宣发P13] 明确要;是贡献角色,不是能力等级",
    ),
    GamificationPattern(
        "self_comparison_timeline",
        "与自己的过去对比",
        "同家庭时间序列",
        "UI-11 原文『只和自己的过去比较』",
    ),
)

ALLOWED_GAMIFICATION_KEYS: Final[frozenset[str]] = frozenset(
    p.key for p in ALLOWED_GAMIFICATION_PATTERNS
)


class ForbiddenPattern(NamedTuple):
    key: str
    label: str
    violates: str


FORBIDDEN_GAMIFICATION_PATTERNS: Final[tuple[ForbiddenPattern, ...]] = (
    ForbiddenPattern(
        "cross_family_leaderboard",
        "跨家庭排行榜/榜单/百分位",
        "不做家庭 Ranking(根 CLAUDE.md);Port 亦查不出来",
    ),
    ForbiddenPattern(
        "tier_progress_bar",
        "会员等级进度条 / Lv.N / 再消费 X 元升级",
        "FAMILY_MEMBERSHIP_OS_V2_BASELINE.md §UI Contract 明文禁",
    ),
    ForbiddenPattern(
        "growth_score",
        "成长值 / 家庭总分 / 孩子分数驱动的等级",
        "不做 Family Total Score;禁 Child Score",
    ),
    ForbiddenPattern(
        "ability_implication", "用积分/徽章暗示孩子能力、安全等级、优秀程度", "基线转换不变量 7"
    ),
    ForbiddenPattern(
        "dark_pattern",
        "抽奖 / 盲盒 / 限时倒计时逼单 / 连胜中断惩罚",
        "[宣发P9]『用户自愿、信息透明』;与『家是港湾』定位冲突",
    ),
    ForbiddenPattern("points_buy_tier", "积分兑换会籍档位", "基线转换不变量 4"),
)

# Substrings that must never appear in a read-model key. Deliberately broader
# than the pattern list above — it is the cheap, mechanical net.
FORBIDDEN_GAMIFICATION_KEY_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "leaderboard",
        "ranking",
        "rank",
        "percentile",
        "total_score",
        "family_score",
        "child_score",
        "growth_score",
        "tier_level",
        "tier_progress",
        "member_level",
        "lottery",
        "raffle",
        "blindbox",
    }
)

# Copy that must never be emitted by a backend read model. The frontend has its
# own list (`apps/api/.../l0-l1-test-loop.policy.ts` TEST_LOOP_FORBIDDEN_COPY);
# this one guards the payloads, and is scoped to comparison/ability claims —
# the plain words 会员/积分 are legitimate here, unlike in the L0/L1 test loop.
FORBIDDEN_GAMIFICATION_COPY: Final[tuple[str, ...]] = (
    "排行",
    "排名",
    "榜单",
    "超过了",
    "击败",
    "成长分",
    "总分",
    "等级进度",
    "升级到 Lv",
    "抽奖",
    "盲盒",
    "仅剩",
    "错过",
)


# Negation markers. A forbidden word appearing inside a *disclaimer* is the
# opposite of a violation — it is the payload telling the reader we do not do
# that thing.
#
# This distinction is not a convenience: without it the guardrail failed on
# 「会员档位表示服务关系深度,不是等级、分数或排名。」 — a sentence whose whole
# purpose is to deny ranking. A checker that flags "we do not rank" as "we rank"
# teaches developers to dismiss R9 failures as noise, which is worse than having
# no checker, because the next real violation gets waved through too.
_NEGATION_MARKERS: Final[tuple[str, ...]] = (
    "不是",
    "不做",
    "没有",
    "并非",
    "而非",
    "不含",
    "不提供",
    "无关",
)


def _is_disclaimer(text: str, phrase: str) -> bool:
    """True when `phrase` occurs in a clause that denies it.

    Scoped to the clause, not the whole notice: a notice may legitimately deny
    one thing and assert another, and only the denied one is exempt.

    `、` is deliberately NOT a boundary. It is an enumeration comma, so
    「不是等级、分数或排名」 is a single denial covering three nouns; splitting on
    it strands 排名 in a clause without its 不是 and re-fails the exact sentence
    this exemption exists for. Only clause-level punctuation ends a clause.
    """
    separators = ("，", ",", "。", ".", "；", ";")
    clauses = [text]
    for separator in separators:
        clauses = [part for clause in clauses for part in clause.split(separator)]
    for clause in clauses:
        if phrase in clause and not any(m in clause for m in _NEGATION_MARKERS):
            return False  # asserted, not denied — a real violation
    return True


def assert_gamification_safe(payload_keys: object, notices: object) -> None:
    """Raise `ValueError` if a read model smuggles a forbidden shape.

    Called by the guardrail test rather than at runtime — the point is to fail
    the build when someone adds the field, not to add a hot-path check.

    Field names are matched literally: there is no legitimate reason for a
    read-model key to contain `rank`/`score`. Notice *copy* gets the negation
    exemption above, because prose can deny what it names and field names cannot.
    """
    for key in payload_keys:  # type: ignore[union-attr]
        lowered = str(key).lower()
        for token in FORBIDDEN_GAMIFICATION_KEY_TOKENS:
            if token in lowered:
                raise ValueError(f"forbidden_gamification_key:{lowered}")
    for notice in notices:  # type: ignore[union-attr]
        text = str(notice)
        for phrase in FORBIDDEN_GAMIFICATION_COPY:
            if phrase in text and not _is_disclaimer(text, phrase):
                raise ValueError(f"forbidden_gamification_copy:{phrase}")
