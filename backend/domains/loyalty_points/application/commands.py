"""Named Actions for the loyalty points domain.

Five actions, each idempotent on `ctx.idempotency_key`, each appending its own
audit fact to the ledger, each committing once:

    open_points_account · earn_points · redeem_points · expire_points · adjust_points

There is no `set_balance`, no `add_points_directly`, and no generic update. The
only way a balance changes is by appending an entry that explains itself — that
is what makes the number on UI-17 reconcilable with the ledger beneath it.
"""

from __future__ import annotations

import uuid

from backend.packages.contracts.ui_surfaces import POINTS_LEDGER_SOURCE_SURFACES

from ..domain.entities import (
    PointsAccount,
    PointsLedgerEntry,
    PointsRedemption,
    utcnow,
)
from ..domain.errors import (
    LoyaltyPointsConflictError,
    LoyaltyPointsForbiddenError,
    LoyaltyPointsNotFoundError,
    LoyaltyPointsValidationError,
)
from ..domain.policies import (
    assert_human_actor,
    assert_qualification_present,
    assert_sufficient_balance,
    assert_within_caps,
    compute_balance,
    earned_on_day,
    earned_total_for_rule,
)
from .context import ActionContext
from .ports import LoyaltyPointsRepositoryPort


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _assert_ledger_surface(source_page_id: str) -> None:
    """Points may only move from the surfaces that actually show points:
    UI-17 成长积分, UI-15 邀请有礼, UI-30 年度陪伴的「积分与邀请」.
    Mirrors `POINTS_LEDGER_SOURCE_SURFACES`."""
    if source_page_id not in POINTS_LEDGER_SOURCE_SURFACES:
        raise LoyaltyPointsForbiddenError(f"ledger_source_surface_forbidden:{source_page_id}")


async def _require_active_account(
    repo: LoyaltyPointsRepositoryPort, ctx: ActionContext
) -> PointsAccount:
    account = await repo.find_account(ctx.tenant_id, ctx.family_id)
    if account is None:
        raise LoyaltyPointsNotFoundError("points_account_not_found")
    if account.status != "ACTIVE":
        raise LoyaltyPointsConflictError(f"points_account_not_active:{account.status}")
    return account


async def open_points_account(
    repo: LoyaltyPointsRepositoryPort,
    ctx: ActionContext,
    *,
    account_ref: str,
) -> PointsAccount:
    """One account per family. A second call returns the existing account rather
    than erroring: "open my account" is naturally idempotent from the client's
    point of view, and two accounts for one family would split its ledger."""
    existing = await repo.find_account(ctx.tenant_id, ctx.family_id)
    if existing is not None:
        return existing

    now = utcnow()
    account = PointsAccount(
        points_account_id=_new_id("pacct"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        account_ref=account_ref,
        status="ACTIVE",
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    )
    await repo.save_account(account)
    await repo.commit()
    return account


async def earn_points(
    repo: LoyaltyPointsRepositoryPort,
    ctx: ActionContext,
    *,
    rule_ref: str,
    evidence_ref: str,
    source_page_id: str,
    qualification_ref: str | None = None,
    subject_person_id: str | None = None,
) -> PointsLedgerEntry:
    """Award points for one participation event.

    Note the signature: the caller supplies a **rule** and an **evidence ref**,
    never an amount. The amount comes from the rule, so nobody can hand a family
    an arbitrary number of points, and every entry can answer "which checkin /
    review / completed service produced this".
    """
    _assert_ledger_surface(source_page_id)
    if ctx.idempotency_key:
        existing = await repo.find_ledger_entry_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            return existing

    account = await _require_active_account(repo, ctx)
    rule = await repo.find_earn_rule_by_ref(rule_ref)
    if rule is None:
        raise LoyaltyPointsNotFoundError(f"earn_rule_not_found:{rule_ref}")
    if rule.status != "ACTIVE":
        raise LoyaltyPointsConflictError(f"earn_rule_not_active:{rule.status}")

    assert_qualification_present(
        source_kind=rule.source_kind,
        requires_qualification=rule.requires_qualification,
        qualification_ref=qualification_ref,
    )

    entries = await repo.list_ledger(ctx.tenant_id, ctx.family_id)
    now = utcnow()
    assert_within_caps(
        rule_ref=rule.rule_ref,
        points_per_event=rule.points_per_event,
        daily_cap=rule.daily_cap,
        total_cap=rule.total_cap,
        earned_today=earned_on_day(entries, rule_ref=rule.rule_ref, day=now.date()),
        earned_total=earned_total_for_rule(entries, rule_ref=rule.rule_ref),
    )

    balance_after = assert_sufficient_balance(
        balance=compute_balance(entries), points_delta=rule.points_per_event
    )
    entry = PointsLedgerEntry(
        ledger_id=_new_id("pledger"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        points_account_id=account.points_account_id,
        actor_person_id=ctx.actor_person_id,
        subject_person_id=subject_person_id,
        ledger_ref=f"{rule.rule_ref}:{evidence_ref}",
        entry_type="EARN",
        points_delta=rule.points_per_event,
        balance_after=balance_after,
        rule_ref=rule.rule_ref,
        evidence_ref=evidence_ref,
        qualification_ref=qualification_ref,
        source_page_id=source_page_id,
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        occurred_at=now,
        created_at=now,
        created_by=ctx.actor,
    )
    await repo.append_ledger_entry(entry)
    await repo.commit()
    return entry


async def redeem_points(
    repo: LoyaltyPointsRepositoryPort,
    ctx: ActionContext,
    *,
    item_ref: str,
    redemption_ref: str,
    source_page_id: str,
) -> tuple[PointsRedemption, PointsLedgerEntry]:
    """Spend points on a catalogue item.

    The redemption record and the ledger row are written in one unit of work:
    a redemption without its debit, or a debit without its redemption, would
    both be a ledger that cannot explain itself.
    """
    _assert_ledger_surface(source_page_id)
    if ctx.idempotency_key:
        existing = await repo.find_redemption_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            entry = await repo.find_ledger_entry_by_idempotency_key(
                ctx.tenant_id, ctx.family_id, ctx.child_key("redeem")
            )
            if entry is None:  # pragma: no cover - defensive; the two are written together
                raise LoyaltyPointsConflictError("redemption_without_ledger_entry")
            return existing, entry

    account = await _require_active_account(repo, ctx)
    item = await repo.find_redemption_item_by_ref(item_ref)
    if item is None:
        raise LoyaltyPointsNotFoundError(f"redemption_item_not_found:{item_ref}")
    if item.status != "ACTIVE":
        raise LoyaltyPointsConflictError(f"redemption_item_not_active:{item.status}")

    entries = await repo.list_ledger(ctx.tenant_id, ctx.family_id)
    balance_after = assert_sufficient_balance(
        balance=compute_balance(entries), points_delta=-item.points_price
    )

    now = utcnow()
    redemption = PointsRedemption(
        redemption_id=_new_id("predeem"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        actor_person_id=ctx.actor_person_id,
        redemption_ref=redemption_ref,
        item_ref=item.item_ref,
        item_version=item.version_no,
        reward_kind=item.reward_kind,
        points_spent=item.points_price,
        status="REQUESTED",
        ledger_ref=f"{redemption_ref}:REDEEM",
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        created_at=now,
        created_by=ctx.actor,
        updated_at=now,
        updated_by=ctx.actor,
    )
    await repo.save_redemption(redemption)

    entry = PointsLedgerEntry(
        ledger_id=_new_id("pledger"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        points_account_id=account.points_account_id,
        actor_person_id=ctx.actor_person_id,
        ledger_ref=redemption.ledger_ref,
        entry_type="REDEEM",
        points_delta=-item.points_price,
        balance_after=balance_after,
        redemption_id=redemption.redemption_id,
        source_page_id=source_page_id,
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.child_key("redeem"),
        occurred_at=now,
        created_at=now,
        created_by=ctx.actor,
    )
    await repo.append_ledger_entry(entry)
    await repo.commit()
    return redemption, entry


async def expire_points(
    repo: LoyaltyPointsRepositoryPort,
    ctx: ActionContext,
    *,
    points: int,
    reason_code: str,
    source_page_id: str,
) -> PointsLedgerEntry:
    """Expiry is a ledger entry, not a silent reset.

    A family that loses points must be able to see, on UI-17「权益账本」, that it
    happened and why. Zeroing a balance behind the scenes is the single fastest
    way to destroy trust in a points system.
    """
    _assert_ledger_surface(source_page_id)
    if points <= 0:
        raise LoyaltyPointsValidationError("expire_points_must_be_positive")
    if ctx.idempotency_key:
        existing = await repo.find_ledger_entry_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            return existing

    account = await repo.find_account(ctx.tenant_id, ctx.family_id)
    if account is None:
        raise LoyaltyPointsNotFoundError("points_account_not_found")

    entries = await repo.list_ledger(ctx.tenant_id, ctx.family_id)
    balance_after = assert_sufficient_balance(
        balance=compute_balance(entries), points_delta=-points
    )
    now = utcnow()
    entry = PointsLedgerEntry(
        ledger_id=_new_id("pledger"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        points_account_id=account.points_account_id,
        actor_person_id=ctx.actor_person_id,
        ledger_ref=f"expire:{reason_code}:{now.isoformat()}",
        entry_type="EXPIRE",
        points_delta=-points,
        balance_after=balance_after,
        reason_code=reason_code,
        source_page_id=source_page_id,
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        occurred_at=now,
        created_at=now,
        created_by=ctx.actor,
    )
    await repo.append_ledger_entry(entry)
    await repo.commit()
    return entry


async def adjust_points(
    repo: LoyaltyPointsRepositoryPort,
    ctx: ActionContext,
    *,
    points_delta: int,
    reason_code: str,
    source_page_id: str,
    decided_by: str,
) -> PointsLedgerEntry:
    """Human-gated manual correction — the only action allowed either sign.

    `assert_human_actor` refuses an `ai:` actor: an AI may recommend a
    correction, never make one (宪章 R9). The caller must derive `decided_by`
    from the authenticated session, not from a request body — otherwise the
    check inspects a claim rather than a caller.
    """
    _assert_ledger_surface(source_page_id)
    assert_human_actor(decided_by, code="adjust_points")
    if not reason_code.strip():
        raise LoyaltyPointsValidationError("adjust_requires_reason_code")
    if ctx.idempotency_key:
        existing = await repo.find_ledger_entry_by_idempotency_key(
            ctx.tenant_id, ctx.family_id, ctx.idempotency_key
        )
        if existing is not None:
            return existing

    account = await _require_active_account(repo, ctx)
    entries = await repo.list_ledger(ctx.tenant_id, ctx.family_id)
    balance_after = assert_sufficient_balance(
        balance=compute_balance(entries), points_delta=points_delta
    )
    now = utcnow()
    entry = PointsLedgerEntry(
        ledger_id=_new_id("pledger"),
        tenant_id=ctx.tenant_id,
        family_id=ctx.family_id,
        points_account_id=account.points_account_id,
        actor_person_id=ctx.actor_person_id,
        ledger_ref=f"adjust:{reason_code}:{now.isoformat()}",
        entry_type="ADJUST",
        points_delta=points_delta,
        balance_after=balance_after,
        reason_code=reason_code,
        source_page_id=source_page_id,
        environment=ctx.environment,
        correlation_id=ctx.correlation_id,
        idempotency_key=ctx.idempotency_key,
        occurred_at=now,
        created_at=now,
        created_by=decided_by,
    )
    await repo.append_ledger_entry(entry)
    await repo.commit()
    return entry
