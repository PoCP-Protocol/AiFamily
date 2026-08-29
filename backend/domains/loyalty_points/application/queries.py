"""Family-scoped reads for the loyalty points domain.

`get_ui17_growth_points` serves UI-17 成长积分, whose declared featurePoints are
`积分任务 / 权益账本 / 已领取 / 规则说明`. The blocks are named exactly that, and
their order comes from `order_blocks()` so that **emotional value precedes
economic value**: what the family did (tasks, ledger, milestones) before what the
family has (catalogue, balance) before the rules and numbers.

Every read takes only `(tenant_id, family_id)`. There is no argument that would
let a caller read across families, which is how 不做家庭排行 is enforced here —
by absence of capability rather than by policy.
"""

from __future__ import annotations

from datetime import timedelta

from backend.packages.contracts.ui_surfaces import POINTS_READ_SURFACES, get_surface
from backend.packages.contracts.value_ordering import order_blocks

from ..domain.entities import utcnow
from ..domain.errors import LoyaltyPointsForbiddenError
from ..domain.policies import compute_balance, earned_on_day
from .ports import LoyaltyPointsRepositoryPort
from .read_models import (
    EarnTaskView,
    LedgerEntryView,
    MilestoneView,
    PointsProjection,
    RedemptionItemView,
    RedemptionView,
    ScreenView,
)


async def get_points_projection(
    repo: LoyaltyPointsRepositoryPort, *, tenant_id: str, family_id: str
) -> PointsProjection:
    account = await repo.find_account(tenant_id, family_id)
    entries = sorted(await repo.list_ledger(tenant_id, family_id), key=lambda e: e.occurred_at)
    redemptions = await repo.list_redemptions(tenant_id, family_id)
    rules = [r for r in await repo.list_earn_rules() if r.status == "ACTIVE"]
    items = [i for i in await repo.list_redemption_items() if i.status == "ACTIVE"]

    balance = compute_balance(entries)
    # "今日" is the real current day, not the day of the last entry — a family
    # opening UI-17 after a week away must see a full quota, not last week's
    # leftover. Known gap, same as `policies.earned_on_day`: the day boundary is
    # UTC, because family-local timezone belongs to the Account domain and this
    # domain should not invent one.
    today = utcnow().date()

    tasks: list[EarnTaskView] = []
    for rule in rules:
        earned_today = earned_on_day(entries, rule_ref=rule.rule_ref, day=today)
        tasks.append(
            EarnTaskView(
                rule_ref=rule.rule_ref,
                title=rule.title,
                explanation=rule.explanation,
                source_kind=rule.source_kind,
                points_per_event=rule.points_per_event,
                daily_cap=rule.daily_cap,
                earned_today=earned_today,
                remaining_today=(
                    max(rule.daily_cap - earned_today, 0) if rule.daily_cap is not None else None
                ),
                requires_qualification=rule.requires_qualification,
            )
        )

    return PointsProjection(
        family_id=family_id,
        account_status=account.status if account else None,
        balance=balance,
        ledger=[
            LedgerEntryView(
                occurred_at=e.occurred_at,
                entry_type=e.entry_type,
                points_delta=e.points_delta,
                balance_after=e.balance_after,
                rule_ref=e.rule_ref,
                evidence_ref=e.evidence_ref,
                reason_code=e.reason_code,
                source_page_id=e.source_page_id,
            )
            for e in entries
        ],
        earn_tasks=tasks,
        redemptions=[
            RedemptionView(
                redemption_ref=r.redemption_ref,
                item_ref=r.item_ref,
                reward_kind=r.reward_kind,
                points_spent=r.points_spent,
                status=r.status,
                created_at=r.created_at,
            )
            for r in sorted(redemptions, key=lambda r: r.created_at)
        ],
        catalogue=[
            RedemptionItemView(
                item_ref=i.item_ref,
                title=i.title,
                reward_kind=i.reward_kind,
                points_price=i.points_price,
                affordable=balance >= i.points_price,
            )
            for i in items
        ],
        streak_days=_streak_days(entries),
        milestones=_milestones(entries, redemptions),
        text_equivalent=_text_equivalent(balance, entries),
    )


def _streak_days(entries) -> int:
    """Consecutive days with at least one EARN entry, counted back from the most
    recent one.

    Counts behaviour frequency, never ability — and note there is no penalty for
    breaking a streak anywhere in this domain: 连胜中断惩罚 is on the forbidden
    gamification list, because punishing a family for a missed day trades their
    emotional value for our engagement metric.
    """
    earn_days = sorted({e.occurred_at.date() for e in entries if e.entry_type == "EARN"})
    if not earn_days:
        return 0
    streak, cursor = 1, earn_days[-1]
    for day in reversed(earn_days[:-1]):
        if day == cursor - timedelta(days=1):
            streak += 1
            cursor = day
        else:
            break
    return streak


def _milestones(entries, redemptions) -> list[MilestoneView]:
    """Milestones are derived, never stored, and each carries the ref of the fact
    that produced it — so a badge can always be traced to something that really
    happened."""
    out: list[MilestoneView] = []
    earns = [e for e in entries if e.entry_type == "EARN"]
    if earns:
        first = earns[0]
        out.append(
            MilestoneView(
                code="FIRST_PARTICIPATION_RECORDED",
                label="第一次被记录下来的参与",
                occurred_at=first.occurred_at,
                evidence_ref=first.evidence_ref or first.ledger_ref,
            )
        )
    qualified = [e for e in earns if e.qualification_ref]
    if qualified:
        out.append(
            MilestoneView(
                code="FIRST_QUALIFIED_REFERRAL",
                label="第一次把成长内容分享给了合适的家庭",
                occurred_at=qualified[0].occurred_at,
                evidence_ref=qualified[0].qualification_ref or "",
            )
        )
    fulfilled = [r for r in redemptions if r.status in ("REQUESTED", "FULFILLED")]
    if fulfilled:
        earliest = min(fulfilled, key=lambda r: r.created_at)
        out.append(
            MilestoneView(
                code="FIRST_REDEMPTION",
                label="第一次把参与换成了实际的帮助",
                occurred_at=earliest.created_at,
                evidence_ref=earliest.redemption_ref,
            )
        )
    return out


def _text_equivalent(balance: int, entries) -> str:
    """Screen-reader / no-JS equivalent. States what is true and nothing more —
    no comparison with other families, no money equivalence, no ability claim."""
    if not entries:
        return "本家庭还没有成长积分记录。"
    return (
        f"成长积分:{balance:,};共 {len(entries)} 条记录,每一条都可以回看来源。"
        "成长积分记录的是参与,不代表孩子或家庭的能力评价。"
    )


def _screen(surface_id: str, blocks: dict, notices: list[str]) -> ScreenView:
    if surface_id not in POINTS_READ_SURFACES:
        raise LoyaltyPointsForbiddenError(f"surface_not_owned_by_loyalty_points:{surface_id}")
    surface = get_surface(surface_id)
    return ScreenView(
        surface_id=surface.id,
        title=surface.title,
        feature_points=list(surface.feature_points),
        # 情绪价值优先:先"你们家做到了什么",最后才是数字与规则。
        blocks=order_blocks(blocks),
        notices=notices,
    )


async def get_ui17_growth_points(
    repo: LoyaltyPointsRepositoryPort, *, tenant_id: str, family_id: str
) -> ScreenView:
    """UI-17 成长积分 — 积分任务 / 权益账本 / 已领取 / 规则说明."""
    p = await get_points_projection(repo, tenant_id=tenant_id, family_id=family_id)
    return _screen(
        "UI-17",
        {
            "积分任务": {
                "tasks": [t.model_dump() for t in p.earn_tasks],
                "streak_days": p.streak_days,
            },
            "权益账本": {
                "entries": [e.model_dump() for e in p.ledger],
                "balance": p.balance,
                "milestones": [m.model_dump() for m in p.milestones],
            },
            "已领取": {
                "redemptions": [r.model_dump() for r in p.redemptions],
                "catalogue": [c.model_dump() for c in p.catalogue],
            },
            "规则说明": {
                "account_status": p.account_status,
                "rules": [
                    {
                        "rule_ref": t.rule_ref,
                        "explanation": t.explanation,
                        "points_per_event": t.points_per_event,
                        "daily_cap": t.daily_cap,
                        "requires_qualification": t.requires_qualification,
                    }
                    for t in p.earn_tasks
                ],
                "redeemable_for_membership_tier": False,
            },
        },
        [
            "成长积分记录的是参与,不代表孩子或家庭的能力评价。",
            "成长积分与会员档位是两条独立的轴,不能互相换算,积分也不能用于升级会员。",
            "本环境不发生真实兑付。",
        ],
    )
