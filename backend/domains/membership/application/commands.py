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
from datetime import datetime, timedelta
from functools import wraps

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


async def _rollback(repo: MembershipRepositoryPort) -> None:
    rollback = getattr(repo, "rollback", None)
    if rollback is not None:
        await rollback()


async def _commit(repo: MembershipRepositoryPort) -> None:
    try:
        await repo.commit()
    except Exception:
        await _rollback(repo)
        raise


def _transactional(command):
    """Ensure every failed command abandons staged domain writes.

    SQLAlchemy rolls a failed database transaction back only after the caller
    explicitly asks it to. The Fake adapter mirrors that contract so a test
    cannot accidentally pass while a failed append leaves prior writes behind.
    """

    @wraps(command)
    async def wrapped(repo, *args, **kwargs):
        try:
            return await command(repo, *args, **kwargs)
        except Exception:
            await _rollback(repo)
            raise

    return wrapped


def _same(value: object, expected: object) -> bool:
    return value == expected


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


@_transactional
async def subscribe_membership(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    plan_id: str,
    subscription_ref: str,
    consent_ref: str,
    subject_person_id: str | None = None,
    effective_to: datetime | None = None,
) -> MembershipSubscription:
    """Records the commercial relationship. Deliberately does NOT touch the
    tier — baseline: "An entitlement purchase alone does not necessarily
    change the tier".升档要另外调 `activate_membership_tier`.
    """
    assert_human_actor(ctx.actor, code="subscription_create_actor")
    if ctx.idempotency_key:
        existing = await repo.find_subscription_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            if not (
                _same(existing.plan_id, plan_id)
                and _same(existing.subscription_ref, subscription_ref)
                and _same(existing.consent_ref, consent_ref)
                and _same(existing.subject_person_id, subject_person_id)
                and _same(existing.effective_to, effective_to)
            ):
                raise MembershipConflictError("idempotency_key_conflict")
            return existing

    plan = await repo.load_plan(plan_id, tenant_id=ctx.tenant_id)
    if plan.status != "ACTIVE":
        raise MembershipConflictError(f"plan_not_active:{plan.status}")
    if not consent_ref.strip():
        raise MembershipValidationError("consent_ref_required")
    if not subscription_ref.strip():
        raise MembershipValidationError("subscription_ref_required")

    now = utcnow()
    if not plan.is_effective_at(now):
        raise MembershipConflictError("plan_not_effective")
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
    await _commit(repo)
    return subscription


# --------------------------------------------------------------------------
# ActivateMembershipTier  /  RenewMembershipPeriod  /  ExpireMembershipPeriod
# --------------------------------------------------------------------------


@_transactional
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
    assert_human_actor(ctx.actor, code="tier_transition_actor")
    if period_days is not None and period_days <= 0:
        raise MembershipValidationError("period_days_must_be_positive")

    if ctx.idempotency_key:
        existing = await repo.find_tier_transition_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            if not (
                _same(existing.to_tier_code, to_tier)
                and _same(existing.activation_source_type, activation_source_type)
                and _same(existing.activation_source_ref, activation_source_ref)
                and _same(existing.decided_by, decided_by)
            ):
                raise MembershipConflictError("idempotency_key_conflict")
            if existing.resulting_period_id is None:
                raise MembershipConflictError("idempotency_result_missing_period")
            period = await repo.load_period(
                existing.resulting_period_id,
                tenant_id=ctx.tenant_id,
                family_id=ctx.family_id,
            )
            if not (
                _same(period.membership_subscription_id, membership_subscription_id)
                and _same(period_days is None, period.ends_at is None)
                and (
                    period_days is None
                    or _same(period.ends_at, period.starts_at + timedelta(days=period_days))
                )
                and _same(existing.decision_note, decision_note)
                and _same(existing.actor_person_id, ctx.actor_person_id)
            ):
                raise MembershipConflictError("idempotency_key_conflict")
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
        subscription = await repo.load_subscription(
            membership_subscription_id,
            tenant_id=ctx.tenant_id,
            family_id=ctx.family_id,
        )
        if not subscription.is_active_at(utcnow()):
            raise MembershipConflictError("subscription_not_active")

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
    await _commit(repo)
    return transition, period


@_transactional
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


@_transactional
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


@_transactional
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
    assert_human_actor(ctx.actor, code="benefit_grant_actor")
    if ctx.idempotency_key:
        existing_entry = await repo.find_benefit_ledger_entry_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.ledger_key("grant")
        )
        if existing_entry is not None:
            existing_grant = await repo.load_benefit_grant(
                existing_entry.benefit_grant_id,
                tenant_id=ctx.tenant_id,
                family_id=ctx.family_id,
            )
            if not (
                _same(existing_grant.membership_subscription_id, membership_subscription_id)
                and _same(existing_grant.benefit_definition_id, benefit_definition_id)
                and _same(existing_grant.grant_ref, grant_ref)
                and _same(existing_grant.subject_person_id, subject_person_id)
                and (units is None or _same(existing_grant.allocated_units, units))
                and _same(existing_entry.source_page_id, source_page_id)
            ):
                raise MembershipConflictError("idempotency_key_conflict")
            return existing_grant

    subscription = await repo.load_subscription(
        membership_subscription_id,
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
    )
    now = utcnow()
    if not subscription.is_active_at(now):
        raise MembershipConflictError(f"subscription_not_active:{subscription.status}")
    if subscription.subject_person_id is not None and (
        subject_person_id != subscription.subject_person_id
    ):
        raise MembershipForbiddenError("benefit_subject_not_authorized")
    definition: BenefitDefinition = await repo.load_benefit_definition(
        benefit_definition_id, tenant_id=ctx.tenant_id
    )
    if definition.plan_id != subscription.plan_id:
        raise MembershipForbiddenError("benefit_definition_plan_mismatch")
    if not definition.is_effective_at(now):
        raise MembershipConflictError("benefit_definition_not_effective")
    plan = await repo.load_plan(definition.plan_id, tenant_id=ctx.tenant_id)
    if not plan.is_effective_at(now):
        raise MembershipConflictError("plan_not_effective")

    allocated = definition.units_per_grant if units is None else units
    if not grant_ref.strip():
        raise MembershipValidationError("grant_ref_required")
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
    await _commit(repo)
    return grant


@_transactional
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
    assert_human_actor(ctx.actor, code="reservation_create_actor")
    if ctx.idempotency_key:
        existing = await repo.find_reservation_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            if not (
                _same(existing.benefit_grant_id, benefit_grant_id)
                and _same(existing.reservation_ref, reservation_ref)
                and _same(existing.units, units)
                and _same(existing.expires_at, expires_at)
            ):
                raise MembershipConflictError("idempotency_key_conflict")
            return existing

    grant = await repo.load_benefit_grant(
        benefit_grant_id,
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        for_update=True,
    )
    now = utcnow()
    if not grant.is_usable_at(now):
        raise MembershipConflictError(f"grant_not_available:{grant.status}")
    subscription = await repo.load_subscription(
        grant.membership_subscription_id,
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
    )
    if not subscription.is_active_at(now):
        raise MembershipConflictError("subscription_not_active")
    if not reservation_ref.strip():
        raise MembershipValidationError("reservation_ref_required")

    held = sum(
        r.units
        for r in await repo.list_reservations(ctx.tenant_id, ctx.family_id)
        if r.benefit_grant_id == benefit_grant_id and r.status == "HELD"
    )
    if units > grant.remaining_units - held:
        raise MembershipConflictError("grant_insufficient_unreserved_units")

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
    await _commit(repo)
    return reservation


@_transactional
async def release_membership_benefit_reservation(
    repo: MembershipRepositoryPort,
    ctx: ActionContext,
    *,
    benefit_reservation_id: str,
) -> BenefitReservation:
    assert_human_actor(ctx.actor, code="reservation_release_actor")
    reservation = await repo.load_reservation(
        benefit_reservation_id,
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
    )
    if reservation.is_expired_at(utcnow()):
        raise MembershipConflictError("reservation_expired")
    reservation = reservation.release(actor=ctx.actor)
    await repo.save_reservation(reservation)
    await _commit(repo)
    return reservation


@_transactional
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
    assert_human_actor(ctx.actor, code="benefit_consume_actor")
    if ctx.idempotency_key:
        existing_entry = await repo.find_benefit_ledger_entry_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.ledger_key("consume")
        )
        if existing_entry is not None:
            if not (
                _same(existing_entry.benefit_grant_id, benefit_grant_id)
                and _same(existing_entry.units, units)
                and _same(existing_entry.source_page_id, source_page_id)
                and _same(existing_entry.subject_person_id, subject_person_id)
            ):
                raise MembershipConflictError("idempotency_key_conflict")
            if benefit_reservation_id is not None:
                reservation = await repo.load_reservation(
                    benefit_reservation_id,
                    tenant_id=ctx.tenant_id,
                    family_id=ctx.family_id,
                )
                if reservation.status != "CONSUMED":
                    raise MembershipConflictError("idempotency_result_incomplete")
            return await repo.load_benefit_grant(
                existing_entry.benefit_grant_id,
                tenant_id=ctx.tenant_id,
                family_id=ctx.family_id,
            )

    grant = await repo.load_benefit_grant(
        benefit_grant_id,
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        for_update=True,
    )
    now = utcnow()
    if not grant.is_usable_at(now):
        raise MembershipConflictError(f"grant_not_available:{grant.status}")
    subscription = await repo.load_subscription(
        grant.membership_subscription_id,
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
    )
    if not subscription.is_active_at(now):
        raise MembershipConflictError("subscription_not_active")
    if grant.subject_person_id is not None and subject_person_id not in (
        None,
        grant.subject_person_id,
    ):
        raise MembershipForbiddenError("benefit_subject_not_authorized")
    if benefit_reservation_id is not None:
        reservation = await repo.load_reservation(
            benefit_reservation_id,
            tenant_id=ctx.tenant_id,
            family_id=ctx.family_id,
        )
        if reservation.benefit_grant_id != benefit_grant_id:
            raise MembershipValidationError("reservation_grant_mismatch")
        if reservation.units != units:
            raise MembershipValidationError("reservation_units_mismatch")
        if reservation.is_expired_at(now):
            raise MembershipConflictError("reservation_expired")
        if reservation.status != "HELD":
            raise MembershipConflictError(f"reservation_not_held:{reservation.status}")
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
    await _commit(repo)
    return consumed


@_transactional
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
    assert_human_actor(ctx.actor, code="benefit_revoke_actor")
    assert_human_actor(decided_by, code="benefit_revoke")
    if ctx.idempotency_key:
        existing_entry = await repo.find_benefit_ledger_entry_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.ledger_key("revoke")
        )
        if existing_entry is not None:
            if not (
                _same(existing_entry.benefit_grant_id, benefit_grant_id)
                and _same(existing_entry.source_page_id, source_page_id)
            ):
                raise MembershipConflictError("idempotency_key_conflict")
            return await repo.load_benefit_grant(
                existing_entry.benefit_grant_id,
                tenant_id=ctx.tenant_id,
                family_id=ctx.family_id,
            )

    grant = await repo.load_benefit_grant(
        benefit_grant_id,
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
    )
    forfeited = grant.remaining_units
    revoked = grant.revoke(actor=decided_by)
    await repo.save_benefit_grant(revoked)
    for reservation in await repo.list_reservations(ctx.tenant_id, ctx.family_id):
        if reservation.benefit_grant_id == benefit_grant_id and reservation.status == "HELD":
            await repo.save_reservation(reservation.release(actor=decided_by))
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
    await _commit(repo)
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
