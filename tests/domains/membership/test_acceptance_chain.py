"""End-to-end acceptance chain, run against both repositories.

    目录 → 订阅 → 建立会籍(M0) → 升档(M1) → 发放权益 → 占用 → 核销 → 台账 → 读模型

This is the "does the domain actually work" test. The invariant tests next to
it are the "does it refuse the wrong thing" tests; both are needed before
`membership` may move to `status: ACTIVE` in `governance/DOMAIN_REGISTRY.yaml`
(R4).
"""

from __future__ import annotations

from backend.domains.membership.application import commands, queries
from tests.domains.membership.helpers import FAMILY, TENANT, make_ctx, seed_catalogue


async def test_full_membership_chain(repo) -> None:
    plan, benefit_def = await seed_catalogue(repo)

    # 1. 订阅:记录商业关系。此时还没有任何会籍档位 —— 基线原文
    #    "An entitlement purchase alone does not necessarily change the tier".
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="sub-001"),
        plan_id=plan.plan_id,
        subscription_ref="SUB-2026-0001",
        consent_ref="consent-service-001",
    )
    assert subscription.status == "ACTIVE"
    assert await repo.load_active_period(TENANT, FAMILY) is None, "订阅本身不得创建会籍周期"

    # 2. 建立 M0:账户创建是唯一能产出 M0 的来源。
    t0, p0 = await commands.activate_membership_tier(
        repo,
        make_ctx(idempotency_key="tier-000"),
        to_tier="M0_FREE",
        activation_source_type="FAMILY_ACCOUNT_CREATED",
        activation_source_ref="account:family-001",
        decided_by="guardian:001",
    )
    assert (t0.direction, t0.from_tier_code, p0.seq_no) == ("INITIAL", None, 1)

    # 3. 升 M1:21/90 天成长产品激活。旧周期被关闭而不是被改写。
    t1, p1 = await commands.activate_membership_tier(
        repo,
        make_ctx(idempotency_key="tier-001"),
        to_tier="M1_GROWTH",
        activation_source_type="GROWTH_PRODUCT_ACTIVATED",
        activation_source_ref="program:90day-2026-03",
        decided_by="guardian:001",
        period_days=90,
        membership_subscription_id=subscription.membership_subscription_id,
    )
    assert (t1.direction, t1.from_tier_code, t1.to_tier_code) == ("UPGRADE", "M0_FREE", "M1_GROWTH")
    assert p1.seq_no == 2
    assert (await repo.load_period(p0.membership_period_id)).status == "CLOSED"

    # 4. 发放权益 + 台账 GRANT。
    grant = await commands.grant_membership_benefit(
        repo,
        make_ctx(idempotency_key="grant-001"),
        membership_subscription_id=subscription.membership_subscription_id,
        benefit_definition_id=benefit_def.benefit_definition_id,
        grant_ref="GRANT-EXPERT-001",
        source_page_id="UI-30",
    )
    assert (grant.status, grant.allocated_units, grant.remaining_units) == ("AVAILABLE", 2, 2)

    # 5. 占用:选了还没发生。占用不写台账 —— 它不是一次核销。
    reservation = await commands.reserve_membership_benefit(
        repo,
        make_ctx(idempotency_key="resv-001"),
        benefit_grant_id=grant.benefit_grant_id,
        reservation_ref="RESV-001",
        units=1,
    )
    assert reservation.status == "HELD"
    ledger_actions = [e.action for e in await repo.list_benefit_ledger(TENANT, FAMILY)]
    assert ledger_actions == ["GRANT"], "占用不得产生台账条目"

    # 6. 核销:占用转消耗,台账 CONSUME。
    consumed = await commands.consume_membership_benefit(
        repo,
        make_ctx(idempotency_key="consume-001"),
        benefit_grant_id=grant.benefit_grant_id,
        units=1,
        source_page_id="UI-31",
        benefit_reservation_id=reservation.benefit_reservation_id,
    )
    assert (consumed.remaining_units, consumed.status) == (1, "AVAILABLE")
    assert (await repo.load_reservation(reservation.benefit_reservation_id)).status == "CONSUMED"

    entries = sorted(await repo.list_benefit_ledger(TENANT, FAMILY), key=lambda e: e.occurred_at)
    assert [e.action for e in entries] == ["GRANT", "CONSUME"]
    assert [e.remaining_units_after for e in entries] == [2, 1]

    # 7. 读模型:档位、周期、权益、以及"为什么是这个档位"的可回溯历史。
    projection = await queries.get_membership_projection(
        repo, tenant_id=TENANT, family_id=FAMILY
    )
    assert projection.tier_code == "M1_GROWTH"
    assert projection.visibility == "FAMILY_PRIVATE"
    assert projection.current_period is not None and projection.current_period.seq_no == 2
    assert [p.seq_no for p in projection.period_history] == [1, 2]
    assert [t.activation_source_type for t in projection.tier_history] == [
        "FAMILY_ACCOUNT_CREATED",
        "GROWTH_PRODUCT_ACTIVATED",
    ]
    only_grant = projection.benefits[0]
    assert (only_grant.remaining_units, only_grant.reserved_units) == (1, 0)


async def test_annual_renewal_appends_a_new_period(repo) -> None:
    """基线不变量 8:续费创建新的 MembershipPeriod,不得改写历史周期。"""
    plan, _ = await seed_catalogue(repo)
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="sub-002"),
        plan_id=plan.plan_id,
        subscription_ref="SUB-2026-0002",
        consent_ref="consent-service-002",
    )
    await commands.activate_membership_tier(
        repo,
        make_ctx(idempotency_key="t-a"),
        to_tier="M2_ANNUAL",
        activation_source_type="ANNUAL_MEMBERSHIP_ACTIVATED",
        activation_source_ref="order:annual-2026",
        decided_by="guardian:001",
        period_days=365,
        membership_subscription_id=subscription.membership_subscription_id,
    )
    first = await repo.load_active_period(TENANT, FAMILY)
    assert first is not None
    first_snapshot = first.model_dump()

    transition, renewed = await commands.renew_membership_period(
        repo,
        make_ctx(idempotency_key="t-b"),
        activation_source_ref="order:annual-2027",
        decided_by="guardian:001",
    )
    assert transition.activation_source_type == "ANNUAL_MEMBERSHIP_RENEWED"
    assert (transition.direction, renewed.seq_no, renewed.tier_code) == ("LATERAL", 2, "M2_ANNUAL")

    reloaded_first = await repo.load_period(first.membership_period_id)
    # 历史周期只允许从 ACTIVE 变 CLOSED,起止时间与档位一个字节都不能被改写。
    assert reloaded_first.status == "CLOSED"
    assert reloaded_first.starts_at == first_snapshot["starts_at"]
    assert reloaded_first.ends_at == first_snapshot["ends_at"]
    assert reloaded_first.tier_code == first_snapshot["tier_code"]
    assert reloaded_first.seq_no == 1


async def test_expiry_downgrades_to_m0_and_stays_auditable(repo) -> None:
    """降档与升档同样可审计 —— 家庭保留账户与历史,只有付费关系结束。"""
    plan, _ = await seed_catalogue(repo)
    subscription = await commands.subscribe_membership(
        repo,
        make_ctx(idempotency_key="sub-003"),
        plan_id=plan.plan_id,
        subscription_ref="SUB-2026-0003",
        consent_ref="consent-service-003",
    )
    await commands.activate_membership_tier(
        repo,
        make_ctx(idempotency_key="t-c"),
        to_tier="M1_GROWTH",
        activation_source_type="GROWTH_PRODUCT_ACTIVATED",
        activation_source_ref="program:21day-2026-01",
        decided_by="guardian:001",
        period_days=21,
        membership_subscription_id=subscription.membership_subscription_id,
    )
    transition, period = await commands.expire_membership_period(
        repo,
        make_ctx(idempotency_key="t-d"),
        activation_source_ref="scheduler:period-end-2026-02",
        decided_by="ops:lifecycle",
    )
    assert (transition.direction, transition.to_tier_code) == ("DOWNGRADE", "M0_FREE")
    assert period.tier_code == "M0_FREE"
    projection = await queries.get_membership_projection(
        repo, tenant_id=TENANT, family_id=FAMILY
    )
    directions = [t.direction for t in projection.tier_history]
    # The first transition is INITIAL when the family had no prior period, and
    # UPGRADE when M0 was established first. Both are legitimate entry paths;
    # what matters is that the expiry is recorded as a DOWNGRADE rather than
    # silently rewriting history.
    assert directions in (["INITIAL", "DOWNGRADE"], ["UPGRADE", "DOWNGRADE"])
