"""Membership domain entities.

Object set is the "Required Future Domain Objects" list from
`docs/FAMILY_MEMBERSHIP_OS_V2_BASELINE.md`. The existing
`Plan → BenefitDefinition → Subscription → BenefitGrant → BenefitLedger`
kernel (migration 0033) is retained verbatim — field names mirror that DDL
column-for-column so the Python side and the SQL SSOT cannot drift. The V2
lifecycle objects (`MembershipTierDefinition`, `MembershipPeriod`,
`MembershipTierTransition`, `BenefitReservation`) are new and land in
migration 0059.

No FastAPI / SQLAlchemy import here, per the four-layer rule in
`architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 3.

Two structural notes:

* There is **no `tier_level` / `tier_score` / `member_rank` field anywhere**,
  and no field whose name contains one of `policies.FORBIDDEN_TIER_FIELD_TOKENS`
  — a guardrail test reflects over this module to keep it that way.
* This domain does not import `domains.loyalty_points` and never will. The
  four axes (tier / growth stage / points / community role) are separate
  domains precisely so "must not be converted into one another" is a fact of
  the package graph rather than a code review promise.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, model_validator

from .errors import MembershipConflictError, MembershipValidationError
from .policies import (
    assert_fixture_boundary,
    assert_human_actor,
    assert_no_score_semantics,
)
from .value_objects import (
    AllocationType,
    BenefitAction,
    BenefitStatus,
    Environment,
    LedgerSourcePageId,
    PeriodStatus,
    PlanStatus,
    ReservationStatus,
    ScopeType,
    SourceSystem,
    SubscriptionStatus,
    TierCode,
    TransitionDirection,
)


def utcnow() -> datetime:
    """Naive UTC.

    Deliberately naive rather than tz-aware: the SQL columns are `timestamptz`
    but the SQLite engine the tests run on drops tzinfo silently, so an aware
    value would compare unequal to its own round-trip. `product_intelligence`
    made the same choice via `datetime.utcnow()`; this spells it out instead of
    relying on the deprecated call.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _as_naive_utc(moment: datetime) -> datetime:
    """Normalize a caller's timestamp to the domain's naive UTC convention."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


def _is_in_window(*, starts_at: datetime, ends_at: datetime | None, at: datetime) -> bool:
    moment = _as_naive_utc(at)
    start = _as_naive_utc(starts_at)
    end = _as_naive_utc(ends_at) if ends_at is not None else None
    return start <= moment and (end is None or moment < end)


class _Extensible(BaseModel):
    """Schema-controlled extensibility, same shape as the 0033 DDL
    (`attributes_schema_version` + `attributes jsonb`)."""

    attributes_schema_version: int = 1
    attributes: dict = {}

    @model_validator(mode="after")
    def _check_attributes(self):
        assert_no_score_semantics(self.attributes)
        return self


class _Audited(BaseModel):
    row_version: int = 1
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str


class _FixtureBoundary(BaseModel):
    """Production boundary as a domain invariant, not only a DB CHECK."""

    environment: Environment
    source_system: SourceSystem = "TEST_NOOP_ADAPTER"
    external_effect: bool = False

    @model_validator(mode="after")
    def _check_boundary(self):
        assert_fixture_boundary(
            environment=self.environment,
            source_system=self.source_system,
            external_effect=self.external_effect,
        )
        return self


# --------------------------------------------------------------------------
# Catalogue masters (PLATFORM / TENANT scope — never hold Family facts)
# --------------------------------------------------------------------------


class MembershipPlan(_Extensible, _Audited):
    """`family_membership_plans` (0033)."""

    plan_id: str
    scope_type: ScopeType = "PLATFORM"
    tenant_id: str | None = None
    plan_ref: str
    version_no: int = 1
    title: str
    status: PlanStatus = "ACTIVE"
    source_ref: str
    fixture_only: bool = True
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def _check_scope(self):
        if self.scope_type == "PLATFORM" and self.tenant_id is not None:
            raise MembershipValidationError("platform_plan_must_not_have_tenant")
        if self.scope_type == "TENANT" and self.tenant_id is None:
            raise MembershipValidationError("tenant_plan_requires_tenant")
        if not self.fixture_only:
            raise MembershipValidationError("plan_must_be_fixture_only")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise MembershipValidationError("plan_effective_window_invalid")
        return self

    def is_effective_at(self, moment: datetime) -> bool:
        return self.status == "ACTIVE" and _is_in_window(
            starts_at=self.effective_from, ends_at=self.effective_to, at=moment
        )


class MembershipTierDefinition(_Extensible, _Audited):
    """New in V2 (0059). Describes a *relationship depth*, not a rank.

    `entry_rule_text` is deliberately prose: entry conditions are decided by
    the Commerce/Growth waves, and encoding them as an executable rule here
    would let this domain silently become the activation authority.
    """

    tier_definition_id: str
    scope_type: ScopeType = "PLATFORM"
    tenant_id: str | None = None
    tier_code: TierCode
    version_no: int = 1
    title: str
    entry_rule_text: str
    value_summary: str
    benefit_refs: list[str] = []
    status: PlanStatus = "ACTIVE"
    fixture_only: bool = True
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def _check_window(self):
        if self.scope_type == "PLATFORM" and self.tenant_id is not None:
            raise MembershipValidationError("platform_tier_definition_must_not_have_tenant")
        if self.scope_type == "TENANT" and self.tenant_id is None:
            raise MembershipValidationError("tenant_tier_definition_requires_tenant")
        if not self.fixture_only:
            raise MembershipValidationError("tier_definition_must_be_fixture_only")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise MembershipValidationError("tier_definition_effective_window_invalid")
        return self

    def is_effective_at(self, moment: datetime) -> bool:
        return self.status == "ACTIVE" and _is_in_window(
            starts_at=self.effective_from, ends_at=self.effective_to, at=moment
        )


class BenefitDefinition(_Extensible, _Audited):
    """`family_membership_benefit_definitions` (0033)."""

    benefit_definition_id: str
    plan_id: str
    tenant_id: str | None = None
    benefit_ref: str
    version_no: int = 1
    title: str
    allocation_type: AllocationType = "COUNT"
    units_per_grant: int = 1
    valid_days: int | None = None
    status: PlanStatus = "ACTIVE"
    fixture_only: bool = True
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def _check_units(self):
        if self.units_per_grant < 0:
            raise MembershipValidationError("units_per_grant_negative")
        if self.valid_days is not None and self.valid_days <= 0:
            raise MembershipValidationError("valid_days_not_positive")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise MembershipValidationError("benefit_definition_effective_window_invalid")
        return self

    def is_effective_at(self, moment: datetime) -> bool:
        return self.status == "ACTIVE" and _is_in_window(
            starts_at=self.effective_from, ends_at=self.effective_to, at=moment
        )


# --------------------------------------------------------------------------
# Family transaction facts
# --------------------------------------------------------------------------


class MembershipSubscription(_Extensible, _Audited, _FixtureBoundary):
    """`family_membership_subscriptions` (0033).

    A subscription is the *commercial relationship record*. It does not by
    itself set a tier — baseline "An entitlement purchase alone does not
    necessarily change the tier". The tier only moves through
    `MembershipTierTransition`.
    """

    membership_subscription_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    subject_person_id: str | None = None
    subscription_ref: str
    plan_id: str
    plan_ref: str
    plan_version: int
    status: SubscriptionStatus = "PENDING"
    consent_ref: str
    effective_from: datetime
    effective_to: datetime | None = None
    correlation_id: str
    idempotency_key: str | None = None
    cancelled_at: datetime | None = None

    @model_validator(mode="after")
    def _check_window(self):
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise MembershipValidationError("subscription_effective_window_invalid")
        if self.status == "CANCELLED" and self.cancelled_at is None:
            raise MembershipValidationError("cancelled_subscription_requires_cancelled_at")
        return self

    def is_active_at(self, moment: datetime) -> bool:
        return self.status == "ACTIVE" and self.is_within_window_at(moment)

    def is_within_window_at(self, moment: datetime) -> bool:
        return _is_in_window(
            starts_at=self.effective_from, ends_at=self.effective_to, at=moment
        )

    def activate(self, *, actor: str) -> MembershipSubscription:
        assert_human_actor(actor, code="subscription_activate")
        if self.status not in ("PENDING", "PAUSED"):
            raise MembershipConflictError(f"subscription_not_activatable:{self.status}")
        return self.model_copy(
            update={
                "status": "ACTIVE",
                "updated_at": utcnow(),
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def cancel(self, *, actor: str) -> MembershipSubscription:
        assert_human_actor(actor, code="subscription_cancel")
        if self.status not in ("PENDING", "ACTIVE", "PAUSED"):
            raise MembershipConflictError(f"subscription_not_cancellable:{self.status}")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "CANCELLED",
                "cancelled_at": now,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def pause(self, *, actor: str) -> MembershipSubscription:
        assert_human_actor(actor, code="subscription_pause")
        if self.status != "ACTIVE":
            raise MembershipConflictError(f"subscription_not_paused:{self.status}")
        return self.model_copy(
            update={
                "status": "PAUSED",
                "updated_at": utcnow(),
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def resume(self, *, actor: str) -> MembershipSubscription:
        assert_human_actor(actor, code="subscription_resume")
        if self.status != "PAUSED":
            raise MembershipConflictError(f"subscription_not_resumable:{self.status}")
        if not self.is_within_window_at(utcnow()):
            raise MembershipConflictError("subscription_window_closed")
        return self.model_copy(
            update={
                "status": "ACTIVE",
                "updated_at": utcnow(),
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def expire(self, *, actor: str) -> MembershipSubscription:
        assert_human_actor(actor, code="subscription_expire")
        if self.status not in ("ACTIVE", "PAUSED"):
            raise MembershipConflictError(f"subscription_not_expirable:{self.status}")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "EXPIRED",
                "effective_to": self.effective_to or now,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )


class MembershipPeriod(_Extensible, _Audited, _FixtureBoundary):
    """New in V2 (0059). One bounded stretch of one tier.

    Baseline invariant 8: renewal creates a NEW period and must not rewrite
    historical ones. `close()` is the only mutation a period ever accepts, and
    a CLOSED period rejects it — see `MembershipConflictError`.
    """

    membership_period_id: str
    tenant_id: str
    family_id: str
    membership_subscription_id: str | None = None
    period_ref: str
    tier_code: TierCode
    seq_no: int
    status: PeriodStatus = "ACTIVE"
    starts_at: datetime
    ends_at: datetime | None = None
    closed_at: datetime | None = None
    closed_reason: str | None = None
    correlation_id: str
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def _check_window(self):
        if self.seq_no < 1:
            raise MembershipValidationError("period_seq_no_must_be_positive")
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise MembershipValidationError("period_window_invalid")
        if self.status == "CLOSED" and self.closed_at is None:
            raise MembershipValidationError("closed_period_requires_closed_at")
        return self

    def is_active_at(self, moment: datetime) -> bool:
        return self.status == "ACTIVE" and _is_in_window(
            starts_at=self.starts_at, ends_at=self.ends_at, at=moment
        )

    def close(self, *, actor: str, reason: str) -> MembershipPeriod:
        assert_human_actor(actor, code="period_close")
        if self.status == "CLOSED":
            raise MembershipConflictError("period_already_closed")
        if not reason.strip():
            raise MembershipValidationError("period_close_reason_required")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "CLOSED",
                "closed_at": now,
                "closed_reason": reason,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )


class MembershipTierTransition(_Extensible, _FixtureBoundary):
    """New in V2 (0059). The append-only audit fact for every tier change.

    Deliberately has no update method and no `updated_at`/`updated_by`: the
    transition record IS the audit trail (baseline invariant 2). Correcting a
    wrong transition means appending a compensating one, never editing this
    row.
    """

    tier_transition_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    from_tier_code: TierCode | None = None
    to_tier_code: TierCode
    direction: TransitionDirection
    activation_source_type: str
    activation_source_ref: str
    decided_by: str
    decision_note: str | None = None
    resulting_period_id: str | None = None
    correlation_id: str
    idempotency_key: str | None = None
    occurred_at: datetime
    created_at: datetime
    created_by: str


class BenefitGrant(_Extensible, _Audited, _FixtureBoundary):
    """`family_membership_benefit_grants` (0033)."""

    benefit_grant_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    subject_person_id: str | None = None
    membership_subscription_id: str
    benefit_definition_id: str
    benefit_ref: str
    grant_ref: str
    allocation_type: AllocationType
    allocated_units: int
    remaining_units: int
    status: BenefitStatus = "PENDING"
    valid_from: datetime
    valid_to: datetime | None = None
    correlation_id: str
    revoked_at: datetime | None = None

    @model_validator(mode="after")
    def _check_units(self):
        if self.allocated_units < 0:
            raise MembershipValidationError("allocated_units_negative")
        if not 0 <= self.remaining_units <= self.allocated_units:
            raise MembershipValidationError("remaining_units_out_of_range")
        if self.status == "REVOKED" and self.revoked_at is None:
            raise MembershipValidationError("revoked_grant_requires_revoked_at")
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise MembershipValidationError("grant_validity_window_invalid")
        return self

    def is_usable_at(self, moment: datetime) -> bool:
        return self.status == "AVAILABLE" and _is_in_window(
            starts_at=self.valid_from, ends_at=self.valid_to, at=moment
        )

    def make_available(self, *, actor: str) -> BenefitGrant:
        assert_human_actor(actor, code="benefit_grant")
        if self.status != "PENDING":
            raise MembershipConflictError(f"grant_not_pending:{self.status}")
        return self.model_copy(
            update={
                "status": "AVAILABLE",
                "updated_at": utcnow(),
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def consume(self, *, units: int, actor: str) -> BenefitGrant:
        assert_human_actor(actor, code="benefit_consume")
        if units <= 0:
            raise MembershipValidationError("consume_units_must_be_positive")
        if self.status != "AVAILABLE":
            raise MembershipConflictError(f"grant_not_available:{self.status}")
        if units > self.remaining_units:
            raise MembershipConflictError("grant_insufficient_units")
        remaining = self.remaining_units - units
        return self.model_copy(
            update={
                "remaining_units": remaining,
                "status": "CONSUMED" if remaining == 0 else "AVAILABLE",
                "updated_at": utcnow(),
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def revoke(self, *, actor: str) -> BenefitGrant:
        assert_human_actor(actor, code="benefit_revoke")
        if self.status in ("REVOKED", "CONSUMED"):
            raise MembershipConflictError(f"grant_not_revocable:{self.status}")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "REVOKED",
                "remaining_units": 0,
                "revoked_at": now,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )


class BenefitReservation(_Extensible, _Audited, _FixtureBoundary):
    """New in V2 (0059). Holds units while a service is being scheduled, so a
    grant cannot be double-spent between "family picked it" and "service
    happened". Release is always possible; a reservation is not a consumption.
    """

    benefit_reservation_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    benefit_grant_id: str
    reservation_ref: str
    units: int
    status: ReservationStatus = "HELD"
    expires_at: datetime | None = None
    released_at: datetime | None = None
    consumed_at: datetime | None = None
    correlation_id: str
    idempotency_key: str | None = None

    @model_validator(mode="after")
    def _check_units(self):
        if self.units <= 0:
            raise MembershipValidationError("reservation_units_must_be_positive")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise MembershipValidationError("reservation_expiry_invalid")
        return self

    def is_expired_at(self, moment: datetime) -> bool:
        return self.expires_at is not None and _as_naive_utc(moment) >= _as_naive_utc(
            self.expires_at
        )

    def release(self, *, actor: str) -> BenefitReservation:
        assert_human_actor(actor, code="reservation_release")
        if self.status != "HELD":
            raise MembershipConflictError(f"reservation_not_held:{self.status}")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "RELEASED",
                "released_at": now,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def mark_consumed(self, *, actor: str) -> BenefitReservation:
        assert_human_actor(actor, code="reservation_consume")
        if self.status != "HELD":
            raise MembershipConflictError(f"reservation_not_held:{self.status}")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "CONSUMED",
                "consumed_at": now,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )


class BenefitLedgerEntry(_Extensible, _FixtureBoundary):
    """`family_membership_benefit_ledger` (0033). Append-only, never a client
    write target, no update method by design."""

    membership_benefit_ledger_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    subject_person_id: str | None = None
    benefit_grant_id: str
    ledger_ref: str
    action: BenefitAction
    units: int
    remaining_units_after: int
    source_page_id: LedgerSourcePageId
    correlation_id: str
    idempotency_key: str | None = None
    occurred_at: datetime
    created_at: datetime
    created_by: str

    @model_validator(mode="after")
    def _check_units(self):
        if self.units < 0 or self.remaining_units_after < 0:
            raise MembershipValidationError("ledger_units_negative")
        return self
