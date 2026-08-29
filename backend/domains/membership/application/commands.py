"""Named Actions for the membership domain.

One function per `specs/actions/*.action.yaml`. Every one of them is
idempotent on `ctx.idempotency_key`, appends its audit fact, and commits once
— `specs/policies/core-state-write.policy.yaml` ("core state may only change
through approved Named Actions ... all core writes require audit metadata").

There is no generic `update_membership()` here on purpose. The tier moves only
through `activate_membership_tier`, which is the only caller of
`policies.assert_tier_transition_legal`.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from backend.packages.contracts.ui_surfaces import MEMBERSHIP_LEDGER_SOURCE_SURFACES

from ..domain.entities import (
    BenefitDefinition,
    BenefitGrant,
    BenefitLedgerEntry,
    BenefitReservation,
    MembershipPeriod,
    MembershipSubscription,
    MembershipTierTransition,
    utcnow,
)
from ..domain.errors import (
    MembershipConflictError,
    MembershipForbiddenError,
    MembershipValidationError,
)
from ..domain.policies import assert_human_actor, assert_tier_transition_legal
from ..domain.value_objects import TierCode
from .context import ActionContext
from .ports import MembershipRepositoryPort


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _assert_ledger_surface(source_page_id: str) -> None:
    """Benefit units may only be spent from the surfaces the DDL allows
    (`family_membership_benefit_ledger.source_page_id` CHECK, mirrored in
    `backend/packages/contracts/ui_surfaces.py`)."""
    if source_page_id not in MEMBERSHIP_LEDGER_SOURCE_SURFACES:
        raise MembershipForbiddenError(f"ledger_source_surface_forbidden:{source_page_id}")


# --------------------------------------------------------------------------
# SubscribeMembership
# --------------------------------------------------------------------------


async def subscribe_membership(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    plan_id: str,
    subscription_ref: str,
    consent_ref: str,
    subject_person_id: str | None = None,
    effective_to: object = None,
) -> MembershipSubscription:
    """Records the commercial relationship. Deliberately does NOT touch the
    tier — baseline: "An entitlement purchase alone does not necessarily
    change the tier".升档要另外调 `activate_membership_tier`.
    """
    if ctx.idempotency_key:
        existing = await repo.find_subscription_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            return existing

    plan = await repo.load_plan(plan_id)
    if plan.status != "ACTIVE":
        raise MembershipConflictError(f"plan_not_active:{plan.status}")
    if not consent_ref.strip():
        raise MembershipValidationError("consent_ref_required")

    now = utcnow()
    subscription = MembershipSubscription(
        membership_subscription_id=_new_id("msub"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        actor_person_id=ctx.actor_person_id,
        subject_person_id=subject_person_id,
        subscription_ref=subscription_ref,
        plan_id=plan.plan_id,
        plan_ref=plan.plan_ref,
        plan_version=plan.version_no,
        status="PENDING",
        consent_ref=consent_ref,
        environment=ctx.environment,
        effective_from=now,
        effective_to=effective_to,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    ).activate(actor=ctx.actor)

    await repo.save_subscription(subscription)
    await repo.commit()
    return subscription


# --------------------------------------------------------------------------
# ActivateMembershipTier  /  RenewMembershipPeriod  /  ExpireMembershipPeriod
# --------------------------------------------------------------------------


async def activate_membership_tier(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    to_tier: TierCode,
    activation_source_type: str,
    activation_source_ref: str,
    decided_by: str,
    period_days: int | None = None,
    membership_subscription_id: str | None = None,
    decision_note: str | None = None,
) -> tuple[MembershipTierTransition, MembershipPeriod]:
    """The only path that moves a family's membership tier.

    Closes the current period (if any) and appends a new one — never rewrites
    it (baseline invariant 8). The transition fact carries the deterministic
    `(activation_source_type, activation_source_ref)` pair that invariant 1
    requires.
    """
    if ctx.idempotency_key:
        existing = await repo.find_tier_transition_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            period = await repo.load_period(existing.resulting_period_id)
            return existing, period

    current = await repo.load_active_period(ctx.tenant_id, ctx.family_id)
    from_tier = current.tier_code if current is not None else None

    # Single gate: human actor, allowed source, source↔target agreement.
    direction = assert_tier_transition_legal(
        from_tier=from_tier,
        to_tier=to_tier,
        activation_source_type=activation_source_type,
        activation_source_ref=activation_source_ref,
        decided_by=decided_by,
    )

    if membership_subscription_id is not None:
        await repo.load_subscription(membership_subscription_id)  # must exist

    now = utcnow()
    if current is not None:
        await repo.save_period(
            current.close(actor=ctx.actor, reason=f"superseded_by:{activation_source_type}")
        )

    periods = await repo.list_periods(ctx.tenant_id, ctx.family_id)
    next_seq = max((p.seq_no for p in periods), default=0) + 1
    period = MembershipPeriod(
        membership_period_id=_new_id("mperiod"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        membership_subscription_id=membership_subscription_id,
        period_ref=f"{ctx.family_id}:{to_tier}:{next_seq}",
        tier_code=to_tier,
        seq_no=next_seq,
        status="ACTIVE",
        starts_at=now,
        ends_at=now + timedelta(days=period_days) if period_days else None,
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.ledger_key("period"),
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    )
    await repo.save_period(period)

    transition = MembershipTierTransition(
        tier_transition_id=_new_id("mtrans"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        actor_person_id=ctx.actor_person_id,
        from_tier_code=from_tier,
        to_tier_code=to_tier,
        direction=direction,
        activation_source_type=activation_source_type,
        activation_source_ref=activation_source_ref,
        decided_by=decided_by,
        decision_note=decision_note,
        resulting_period_id=period.membership_period_id,
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        occurred_at=now,
        created_at=now,
        created_by=ctx.actor,
    )
    await repo.append_tier_transition(transition)
    await repo.commit()
    return transition, period


async def renew_membership_period(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    activation_source_ref: str,
    decided_by: str,
    period_days: int = 365,
    decision_note: str | None = None,
) -> tuple[MembershipTierTransition, MembershipPeriod]:
    """Baseline invariant 8. Renewal is an append, never an edit: the current
    period is closed and a new `seq_no` opens at the same tier.

    Only M2_ANNUAL renews — the 21/90-day growth products are activations, not
    renewals, and re-activating them goes through `activate_membership_tier`
    with `GROWTH_PRODUCT_ACTIVATED`.
    """
    current = await repo.load_active_period(ctx.tenant_id, ctx.family_id)
    if current is None:
        raise MembershipConflictError("no_active_period_to_renew")
    if current.tier_code != "M2_ANNUAL":
        raise MembershipConflictError(f"tier_not_renewable:{current.tier_code}")

    return await activate_membership_tier(
        repo,
        ctx,
        to_tier="M2_ANNUAL",
        activation_source_type="ANNUAL_MEMBERSHIP_RENEWED",
        activation_source_ref=activation_source_ref,
        decided_by=decided_by,
        period_days=period_days,
        membership_subscription_id=current.membership_subscription_id,
        decision_note=decision_note,
    )


async def expire_membership_period(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    activation_source_ref: str,
    decided_by: str,
) -> tuple[MembershipTierTransition, MembershipPeriod]:
    """Lapse back to M0_FREE. The family keeps its account and its history —
    only the paid relationship ends. Downgrade is as auditable as upgrade.
    """
    current = await repo.load_active_period(ctx.tenant_id, ctx.family_id)
    if current is None:
        raise MembershipConflictError("no_active_period_to_expire")
    if current.tier_code == "M0_FREE":
        raise MembershipConflictError("m0_period_does_not_expire")

    return await activate_membership_tier(
        repo,
        ctx,
        to_tier="M0_FREE",
        activation_source_type="MEMBERSHIP_PERIOD_EXPIRED",
        activation_source_ref=activation_source_ref,
        decided_by=decided_by,
    )


# --------------------------------------------------------------------------
# Benefit lifecycle: Grant → Reserve → Consume / Revoke
# --------------------------------------------------------------------------


async def grant_membership_benefit(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    membership_subscription_id: str,
    benefit_definition_id: str,
    grant_ref: str,
    source_page_id: str,
    subject_person_id: str | None = None,
    units: int | None = None,
) -> BenefitGrant:
    _assert_ledger_surface(source_page_id)
    if ctx.idempotency_key:
        existing_entry = await repo.find_benefit_ledger_entry_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.ledger_key("grant")
        )
        if existing_entry is not None:
            return await repo.load_benefit_grant(existing_entry.benefit_grant_id)

    subscription = await repo.load_subscription(membership_subscription_id)
    if subscription.status != "ACTIVE":
        raise MembershipConflictError(f"subscription_not_active:{subscription.status}")
    definition: BenefitDefinition = await repo.load_benefit_definition(benefit_definition_id)
    if definition.status != "ACTIVE":
        raise MembershipConflictError(f"benefit_definition_not_active:{definition.status}")

    allocated = definition.units_per_grant if units is None else units
    now = utcnow()
    grant = BenefitGrant(
        benefit_grant_id=_new_id("mgrant"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        actor_person_id=ctx.actor_person_id,
        subject_person_id=subject_person_id,
        membership_subscription_id=membership_subscription_id,
        benefit_definition_id=benefit_definition_id,
        benefit_ref=definition.benefit_ref,
        grant_ref=grant_ref,
        allocation_type=definition.allocation_type,
        allocated_units=allocated,
        remaining_units=allocated,
        status="PENDING",
        environment=ctx.environment,
        valid_from=now,
        valid_to=now + timedelta(days=definition.valid_days) if definition.valid_days else None,
        correlation_id=ctx.correlation_id,
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    ).make_available(actor=ctx.actor)

    await repo.save_benefit_grant(grant)
    await _append_ledger(
        repo,
        ctx,
        grant=grant,
        action="GRANT",
        units=allocated,
        source_page_id=source_page_id,
        subject_person_id=subject_person_id,
        key_suffix="grant",
    )
    await repo.commit()
    return grant


async def reserve_membership_benefit(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    benefit_grant_id: str,
    reservation_ref: str,
    units: int,
    expires_at: object = None,
) -> BenefitReservation:
    """Hold units while a service is being scheduled.

    Without this, two surfaces (UI-31 我的服务 and UI-30 年度陪伴) can both
    spend the same remaining unit between "family picked it" and "service
    happened". A reservation is not a consumption — no ledger entry is written
    until `consume_membership_benefit`.
    """
    if ctx.idempotency_key:
        existing = await repo.find_reservation_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            return existing

    grant = await repo.load_benefit_grant(benefit_grant_id)
    if grant.status != "AVAILABLE":
        raise MembershipConflictError(f"grant_not_available:{grant.status}")

    held = sum(
        r.units
        for r in await repo.list_reservations(ctx.tenant_id, ctx.family_id)
        if r.benefit_grant_id == benefit_grant_id and r.status == "HELD"
    )
    if units > grant.remaining_units - held:
        raise MembershipConflictError("grant_insufficient_unreserved_units")

    now = utcnow()
    reservation = BenefitReservation(
        benefit_reservation_id=_new_id("mresv"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        actor_person_id=ctx.actor_person_id,
        benefit_grant_id=benefit_grant_id,
        reservation_ref=reservation_ref,
        units=units,
        status="HELD",
        expires_at=expires_at,
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    )
    await repo.save_reservation(reservation)
    await repo.commit()
    return reservation


async def release_membership_benefit_reservation(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    benefit_reservation_id: str,
) -> BenefitReservation:
    reservation = (await repo.load_reservation(benefit_reservation_id)).release(actor=ctx.actor)
    await repo.save_reservation(reservation)
    await repo.commit()
    return reservation


async def consume_membership_benefit(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    benefit_grant_id: str,
    units: int,
    source_page_id: str,
    benefit_reservation_id: str | None = None,
    subject_person_id: str | None = None,
) -> BenefitGrant:
    _assert_ledger_surface(source_page_id)
    if ctx.idempotency_key:
        existing_entry = await repo.find_benefit_ledger_entry_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.ledger_key("consume")
        )
        if existing_entry is not None:
            return await repo.load_benefit_grant(existing_entry.benefit_grant_id)

    grant = await repo.load_benefit_grant(benefit_grant_id)
    if benefit_reservation_id is not None:
        reservation = await repo.load_reservation(benefit_reservation_id)
        if reservation.benefit_grant_id != benefit_grant_id:
            raise MembershipValidationError("reservation_grant_mismatch")
        if reservation.units != units:
            raise MembershipValidationError("reservation_units_mismatch")
        await repo.save_reservation(reservation.mark_consumed(actor=ctx.actor))

    consumed = grant.consume(units=units, actor=ctx.actor)
    await repo.save_benefit_grant(consumed)
    await _append_ledger(
        repo,
        ctx,
        grant=consumed,
        action="CONSUME",
        units=units,
        source_page_id=source_page_id,
        subject_person_id=subject_person_id,
        key_suffix="consume",
    )
    await repo.commit()
    return consumed


async def revoke_membership_benefit(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    benefit_grant_id: str,
    source_page_id: str,
    decided_by: str,
) -> BenefitGrant:
    """Revocation is a human decision (`assert_human_actor`) and leaves a
    ledger row for the units that were taken back — a family can always see
    what was removed and by whom."""
    _assert_ledger_surface(source_page_id)
    assert_human_actor(decided_by, code="benefit_revoke")
    if ctx.idempotency_key:
        existing_entry = await repo.find_benefit_ledger_entry_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.ledger_key("revoke")
        )
        if existing_entry is not None:
            return await repo.load_benefit_grant(existing_entry.benefit_grant_id)

    grant = await repo.load_benefit_grant(benefit_grant_id)
    forfeited = grant.remaining_units
    revoked = grant.revoke(actor=decided_by)
    await repo.save_benefit_grant(revoked)
    await _append_ledger(
        repo,
        ctx,
        grant=revoked,
        action="REVOKE",
        units=forfeited,
        source_page_id=source_page_id,
        subject_person_id=grant.subject_person_id,
        key_suffix="revoke",
    )
    await repo.commit()
    return revoked


async def _append_ledger(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    grant: BenefitGrant,
    action: str,
    units: int,
    source_page_id: str,
    subject_person_id: str | None,
    key_suffix: str,
) -> BenefitLedgerEntry:
    now = utcnow()
    entry = BenefitLedgerEntry(
        membership_benefit_ledger_id=_new_id("mledger"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        actor_person_id=ctx.actor_person_id,
        subject_person_id=subject_person_id,
        benefit_grant_id=grant.benefit_grant_id,
        ledger_ref=f"{grant.grant_ref}:{action}:{now.isoformat()}",
        action=action,
        units=units,
        remaining_units_after=grant.remaining_units,
        source_page_id=source_page_id,
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.ledger_key(key_suffix),
        occurred_at=now,
        created_at=now,
        created_by=ctx.actor,
    )
    await repo.append_benefit_ledger_entry(entry)
    return entry
