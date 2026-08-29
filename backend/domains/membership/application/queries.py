"""Family-scoped reads, one function per App UI surface that shows membership.

Surface ownership is declared in `backend/packages/contracts/ui_surfaces.py`
(`MEMBERSHIP_READ_SURFACES`). The point of building per-surface functions
rather than one fat projection is the problem `FAMILY_MEMBERSHIP_OS_V2_BASELINE.md`
§UI Contract names: "UI-06 / UI-18 / UI-30 must not each invent a different
membership meaning". They can't here — they all read the same projection and
only choose which blocks to show.

No function takes anything other than `(tenant_id, family_id)` as scope. There
is no cross-family read to build a leaderboard from.
"""

from __future__ import annotations

from backend.packages.contracts.ui_surfaces import MEMBERSHIP_READ_SURFACES, get_surface
from backend.packages.contracts.value_ordering import order_blocks

from ..domain.errors import MembershipForbiddenError
from .ports import MembershipRepositoryPort
from .read_models import (
    BenefitView,
    MembershipProjection,
    PeriodView,
    ScreenView,
    SubscriptionView,
    TierTransitionView,
)

# Tier display labels from the baseline. Note what is NOT here: no level
# number, no progress percentage, no "Lv.N" — the forbidden UI strings in
# `FAMILY_MEMBERSHIP_OS_V2_BASELINE.md` §UI Contract.
TIER_LABELS: dict[str, str] = {
    "M0_FREE": "家庭会员 M0",
    "M1_GROWTH": "成长会员 M1",
    "M2_ANNUAL": "年度会员 M2",
}


async def get_membership_projection(
    repo: MembershipRepositoryPort, *, tenant_id: str, family_id: str
) -> MembershipProjection:
    subscriptions = await repo.list_subscriptions(tenant_id, family_id)
    grants = await repo.list_benefit_grants(tenant_id, family_id)
    reservations = await repo.list_reservations(tenant_id, family_id)
    periods = await repo.list_periods(tenant_id, family_id)
    transitions = await repo.list_tier_transitions(tenant_id, family_id)

    active_period = next((p for p in periods if p.status == "ACTIVE"), None)
    held_by_grant: dict[str, int] = {}
    for r in reservations:
        if r.status == "HELD":
            held_by_grant[r.benefit_grant_id] = held_by_grant.get(r.benefit_grant_id, 0) + r.units

    tier_code = active_period.tier_code if active_period else None
    return MembershipProjection(
        family_id=family_id,
        tier_code=tier_code,
        current_period=_period_view(active_period) if active_period else None,
        period_history=[_period_view(p) for p in sorted(periods, key=lambda p: p.seq_no)],
        subscriptions=[
            SubscriptionView(
                membership_subscription_id=s.membership_subscription_id,
                plan_ref=s.plan_ref,
                plan_version=s.plan_version,
                status=s.status,
                effective_from=s.effective_from,
                effective_to=s.effective_to,
            )
            for s in subscriptions
        ],
        benefits=[
            BenefitView(
                benefit_grant_id=g.benefit_grant_id,
                benefit_ref=g.benefit_ref,
                status=g.status,
                allocated_units=g.allocated_units,
                remaining_units=g.remaining_units,
                reserved_units=held_by_grant.get(g.benefit_grant_id, 0),
                valid_from=g.valid_from,
                valid_to=g.valid_to,
            )
            for g in grants
        ],
        tier_history=[
            TierTransitionView(
                occurred_at=t.occurred_at,
                from_tier_code=t.from_tier_code,
                to_tier_code=t.to_tier_code,
                direction=t.direction,
                activation_source_type=t.activation_source_type,
                activation_source_ref=t.activation_source_ref,
                decided_by=t.decided_by,
            )
            for t in sorted(transitions, key=lambda t: t.occurred_at)
        ],
        text_equivalent=_text_equivalent(tier_code, grants),
    )


def _period_view(period) -> PeriodView:
    return PeriodView(
        membership_period_id=period.membership_period_id,
        tier_code=period.tier_code,
        seq_no=period.seq_no,
        status=period.status,
        starts_at=period.starts_at,
        ends_at=period.ends_at,
    )


def _text_equivalent(tier_code: str | None, grants) -> str:
    """Screen-reader / no-JS text equivalent, mirroring the existing
    `FamilyApiMembershipProjection.text_equivalent` contract. Says only what is
    true — no "Lv.", no score, no comparison with other families."""
    if tier_code is None:
        return "本家庭尚未建立会员关系。"
    available = sum(1 for g in grants if g.status == "AVAILABLE")
    return (
        f"当前会员:{TIER_LABELS[tier_code]};可用权益 {available} 项。"
        "会员档位不代表家庭或孩子的能力评价。"
    )


def _screen(surface_id: str, blocks: dict, notices: list[str]) -> ScreenView:
    if surface_id not in MEMBERSHIP_READ_SURFACES:
        raise MembershipForbiddenError(f"surface_not_owned_by_membership:{surface_id}")
    surface = get_surface(surface_id)
    return ScreenView(
        surface_id=surface.id,
        title=surface.title,
        feature_points=list(surface.feature_points),
        # Emotional value before economic value — relationship and what the
        # family achieved come before quota and expiry dates. The client renders
        # in payload order, so the rule lives in one place.
        blocks=order_blocks(blocks),
        notices=notices,
    )


def _milestones(projection: MembershipProjection) -> list[dict]:
    """Evidence-bound milestones for the gamification layer
    (`backend/packages/contracts/gamification.py` `evidence_bound_milestones`).

    Every entry points at a fact that already happened and cannot be taken
    away: a closed period, a first activation, a renewal. Nothing here is a
    score, and nothing is derived from a counter that could drift from the
    underlying records.
    """
    out: list[dict] = []
    closed = [p for p in projection.period_history if p.status == "CLOSED"]
    annual = [p for p in projection.period_history if p.tier_code == "M2_ANNUAL"]
    first = next((t for t in projection.tier_history if t.direction == "INITIAL"), None)
    if first is not None:
        out.append(
            {
                "code": "FIRST_MEMBERSHIP_ESTABLISHED",
                "label": "开始与 Family 同行",
                "occurred_at": first.occurred_at,
                "evidence_ref": first.activation_source_ref,
            }
        )
    for period in closed:
        out.append(
            {
                "code": "GROWTH_CYCLE_COMPLETED",
                "label": f"完成第 {period.seq_no} 段陪伴周期",
                "occurred_at": period.ends_at or period.starts_at,
                "evidence_ref": period.membership_period_id,
            }
        )
    if len(annual) > 1:
        out.append(
            {
                "code": "ANNUAL_COMPANIONSHIP_RENEWED",
                "label": f"年度陪伴续约 {len(annual) - 1} 次",
                "occurred_at": annual[-1].starts_at,
                "evidence_ref": annual[-1].membership_period_id,
            }
        )
    return out


async def get_ui06_my_membership(
    repo: MembershipRepositoryPort, *, tenant_id: str, family_id: str
) -> ScreenView:
    """UI-06 我的会员 — 当前方案 / 成长权益 / 服务额度 / 有效期."""
    p = await get_membership_projection(repo, tenant_id=tenant_id, family_id=family_id)
    available = [b for b in p.benefits if b.status == "AVAILABLE"]
    return _screen(
        "UI-06",
        {
            "当前方案": {
                "tier_code": p.tier_code,
                "tier_label": TIER_LABELS.get(p.tier_code or ""),
                "plans": [s.model_dump() for s in p.subscriptions if s.status == "ACTIVE"],
            },
            "里程碑": _milestones(p),
            "成长权益": [b.model_dump() for b in available],
            "服务额度": {
                "total_remaining_units": sum(b.remaining_units for b in available),
                "reserved_units": sum(b.reserved_units for b in available),
            },
            "有效期": {
                "current_period": p.current_period.model_dump() if p.current_period else None,
            },
        },
        ["会员档位表示服务关系深度,不是等级、分数或排名。"],
    )


async def get_ui18_membership_center(
    repo: MembershipRepositoryPort, *, tenant_id: str, family_id: str
) -> ScreenView:
    """UI-18 会员中心 — 会员状态 / 可用权益 / 服务入口 / 续费意向."""
    p = await get_membership_projection(repo, tenant_id=tenant_id, family_id=family_id)
    renewal_open = (
        p.current_period is not None
        and p.current_period.tier_code == "M2_ANNUAL"
        and p.current_period.status == "ACTIVE"
    )
    return _screen(
        "UI-18",
        {
            "会员状态": {
                "tier_code": p.tier_code,
                "tier_label": TIER_LABELS.get(p.tier_code or ""),
                "current_period": p.current_period.model_dump() if p.current_period else None,
                "history": [t.model_dump() for t in p.tier_history],
            },
            "可用权益": [b.model_dump() for b in p.benefits if b.status == "AVAILABLE"],
            # Service entry points live in the service domain; membership only
            # states which benefit refs unlock them.
            "服务入口": {
                "unlocked_benefit_refs": sorted(
                    {b.benefit_ref for b in p.benefits if b.status == "AVAILABLE"}
                )
            },
            # Intent only. Real renewal billing is HOLD — see
            # FAMILY_COMMERCE_MEMBERSHIP_POINTS_ARCHITECTURE_V1.md §9.2.
            "续费意向": {"renewal_window_open": renewal_open, "billing_enabled": False},
        },
        ["续费意向仅记录家庭意愿,不发生支付、不自动续费。"],
    )


async def get_ui30_annual_companion(
    repo: MembershipRepositoryPort, *, tenant_id: str, family_id: str
) -> ScreenView:
    """UI-30 年度陪伴方案 — 年度计划 / 会员权益 / 积分与邀请 / 续费意向.

    The 积分与邀请 block is deliberately returned as a *pointer*, not data:
    points live in `domains/loyalty_points` and this domain must not import
    it (four-axis separation). The client composes the two responses side by
    side — which is exactly the baseline's "may be displayed together, but must
    not be converted into one another".
    """
    p = await get_membership_projection(repo, tenant_id=tenant_id, family_id=family_id)
    annual = [pv for pv in p.period_history if pv.tier_code == "M2_ANNUAL"]
    return _screen(
        "UI-30",
        {
            "年度计划": {
                "current_period": p.current_period.model_dump() if p.current_period else None,
                "annual_periods": [pv.model_dump() for pv in annual],
                "renewal_count": max(len(annual) - 1, 0),
            },
            "里程碑": _milestones(p),
            "会员权益": [
                b.model_dump() for b in p.benefits if b.status in ("AVAILABLE", "CONSUMED")
            ],
            "积分与邀请": {
                "owned_by_domain": "loyalty_points",
                "compose_with": ["loyalty_points.queries.get_ui17_growth_points"],
                "conversion_allowed": False,
            },
            "续费意向": {"billing_enabled": False},
        },
        [
            "成长积分与会员档位是两条独立的轴,不能互相换算。",
            "本环境不发生真实支付与真实积分兑付。",
        ],
    )


async def get_ui32_orders_and_assets(
    repo: MembershipRepositoryPort, *, tenant_id: str, family_id: str
) -> ScreenView:
    """UI-32 订单与资产 — 方案意向 / 已激活权益 / 成长报告 / 课程资产.

    Only 已激活权益 belongs to this domain. 方案意向 is the existing
    `family_order_intents` slice (migration 0031, `COMMERCE_ENTITLEMENT`
    domain), 成长报告 is the growth domain, 课程资产 is content — each is
    returned as an explicit ownership pointer instead of a plausible-looking
    empty list, so a caller cannot mistake "not mine" for "none exist".
    """
    p = await get_membership_projection(repo, tenant_id=tenant_id, family_id=family_id)
    ledger = await repo.list_benefit_ledger(tenant_id, family_id)
    return _screen(
        "UI-32",
        {
            "方案意向": {
                "owned_by_domain": "commerce_entitlement",
                "source": "family_order_intents",
            },
            "已激活权益": {
                "grants": [b.model_dump() for b in p.benefits],
                "ledger": [
                    {
                        "action": e.action,
                        "units": e.units,
                        "remaining_units_after": e.remaining_units_after,
                        "occurred_at": e.occurred_at,
                        "source_page_id": e.source_page_id,
                    }
                    for e in sorted(ledger, key=lambda e: e.occurred_at)
                ],
            },
            "成长报告": {"owned_by_domain": "growth"},
            "课程资产": {"owned_by_domain": "content"},
        },
        ["权益账本为追加式记录,发放、核销与撤销都可回溯。"],
    )
