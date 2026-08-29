"""Loyalty points entities.

No framework dependency here (no FastAPI, no SQLAlchemy) — persistence mapping
lives in `infrastructure/sqlalchemy_models.py`.

The structurally important absence: **`PointsAccount` has no `balance` field.**
A balance column is a column someone can UPDATE, and then the number on the
screen no longer has to agree with the ledger that explains it. Balance is
`policies.compute_balance(entries)`, always.

Second absence: no field name anywhere contains `score` / `rank` / `level` /
`cash` / `worth` (see `policies.FORBIDDEN_POINTS_FIELD_TOKENS`, enforced by a
guardrail test that reflects over this module and over the ORM tables).
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, model_validator

from .errors import LoyaltyPointsConflictError, LoyaltyPointsValidationError
from .policies import (
    assert_earn_source_allowed,
    assert_entry_type_sign,
    assert_evidence_bound,
    assert_fixture_boundary,
    assert_human_actor,
    assert_no_score_semantics,
    assert_redemption_linked,
    assert_reward_kind_allowed,
)
from .value_objects import (
    CatalogueStatus,
    EntryType,
    Environment,
    LedgerSourcePageId,
    PointsAccountStatus,
    RedemptionStatus,
    RewardKind,
    ScopeType,
    SourceKind,
    SourceSystem,
)


def utcnow() -> datetime:
    """Naive UTC.

    Deliberately naive: the SQL columns are `timestamptz`, but the SQLite engine
    the tests run on drops tzinfo silently, so an aware value would compare
    unequal to its own round-trip. Same choice as the membership domain, spelled
    out rather than relying on the deprecated `datetime.utcnow()`.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class _Extensible(BaseModel):
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
# Catalogue masters — PLATFORM / TENANT scope, never hold family facts
# --------------------------------------------------------------------------


class PointsEarnRule(_Extensible, _Audited):
    """How points may be earned. Caps and the qualification requirement live
    here as **data**, not as code branches, so operations can change a cap
    without a deploy and an auditor can read the cap without reading code.
    """

    rule_id: str
    scope_type: ScopeType = "PLATFORM"
    tenant_id: str | None = None
    rule_ref: str
    version_no: int = 1
    title: str
    explanation: str
    source_kind: SourceKind
    points_per_event: int
    daily_cap: int | None = None
    total_cap: int | None = None
    requires_qualification: bool = False
    status: CatalogueStatus = "ACTIVE"
    fixture_only: bool = True
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def _check_rule(self):
        assert_earn_source_allowed(self.source_kind)
        if self.points_per_event <= 0:
            raise LoyaltyPointsValidationError("points_per_event_must_be_positive")
        for cap_name, cap in (("daily_cap", self.daily_cap), ("total_cap", self.total_cap)):
            if cap is not None and cap < self.points_per_event:
                raise LoyaltyPointsValidationError(f"{cap_name}_below_points_per_event")
        if self.scope_type == "PLATFORM" and self.tenant_id is not None:
            raise LoyaltyPointsValidationError("platform_rule_must_not_have_tenant")
        if self.scope_type == "TENANT" and self.tenant_id is None:
            raise LoyaltyPointsValidationError("tenant_rule_requires_tenant")
        if not self.fixture_only:
            raise LoyaltyPointsValidationError("rule_must_be_fixture_only")
        if not self.explanation.strip():
            # UI-17 的「规则说明」块必须有东西可显示。规则不可解释,等于家庭无法知道
            # 自己为什么得分 —— 那就不是可追溯的参与资产了。
            raise LoyaltyPointsValidationError("rule_requires_explanation")
        return self


class RedemptionCatalogItem(_Extensible, _Audited):
    """What points may be exchanged for. `reward_kind` cannot be a membership
    tier, cash, or a lottery ticket — validated on construction, so an
    unconstitutional catalogue row cannot even be built in memory."""

    item_id: str
    scope_type: ScopeType = "PLATFORM"
    tenant_id: str | None = None
    item_ref: str
    version_no: int = 1
    title: str
    reward_kind: RewardKind
    points_price: int
    status: CatalogueStatus = "ACTIVE"
    fixture_only: bool = True
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def _check_item(self):
        assert_reward_kind_allowed(self.reward_kind)
        if self.points_price <= 0:
            raise LoyaltyPointsValidationError("points_price_must_be_positive")
        if not self.fixture_only:
            raise LoyaltyPointsValidationError("item_must_be_fixture_only")
        return self


# --------------------------------------------------------------------------
# Family facts
# --------------------------------------------------------------------------


class PointsAccount(_Extensible, _Audited, _FixtureBoundary):
    """A family's points account. **No balance field** — see module docstring."""

    points_account_id: str
    tenant_id: str
    family_id: str
    account_ref: str
    status: PointsAccountStatus = "ACTIVE"
    correlation_id: str
    idempotency_key: str | None = None
    frozen_at: datetime | None = None
    closed_at: datetime | None = None

    def freeze(self, *, actor: str, reason: str) -> PointsAccount:
        """Freezing stops earning and spending but destroys nothing. A frozen
        account keeps its whole ledger — the family's record of what it did is
        not a lever for enforcement."""
        assert_human_actor(actor, code="account_freeze")
        if self.status != "ACTIVE":
            raise LoyaltyPointsConflictError(f"account_not_active:{self.status}")
        if not reason.strip():
            raise LoyaltyPointsValidationError("account_freeze_reason_required")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "FROZEN",
                "frozen_at": now,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def unfreeze(self, *, actor: str) -> PointsAccount:
        assert_human_actor(actor, code="account_unfreeze")
        if self.status != "FROZEN":
            raise LoyaltyPointsConflictError(f"account_not_frozen:{self.status}")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "ACTIVE",
                "frozen_at": None,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )


class PointsLedgerEntry(_Extensible, _FixtureBoundary):
    """Append-only. The single source of truth for a family's points.

    No `updated_at` / `updated_by` and no mutating method, by design: the entry
    *is* the audit trail. Correcting a wrong entry means appending a
    compensating `ADJUST` (with a human actor and a reason code), never editing
    this row.

    `balance_after` is a **snapshot fact** written at the moment of the entry,
    not a cached aggregate: queries always recompute the balance from
    `SUM(points_delta)`, and a test pins the last entry's `balance_after` to
    that sum so the two can never silently drift.
    """

    ledger_id: str
    tenant_id: str
    family_id: str
    points_account_id: str
    actor_person_id: str
    subject_person_id: str | None = None
    ledger_ref: str
    entry_type: EntryType
    points_delta: int
    balance_after: int
    rule_ref: str | None = None
    redemption_id: str | None = None
    evidence_ref: str | None = None
    reason_code: str | None = None
    qualification_ref: str | None = None
    source_page_id: LedgerSourcePageId
    correlation_id: str
    idempotency_key: str | None = None
    occurred_at: datetime
    created_at: datetime
    created_by: str

    @model_validator(mode="after")
    def _check_entry(self):
        assert_entry_type_sign(self.entry_type, self.points_delta)
        assert_evidence_bound(
            entry_type=self.entry_type,
            rule_ref=self.rule_ref,
            evidence_ref=self.evidence_ref,
            reason_code=self.reason_code,
        )
        assert_redemption_linked(self.entry_type, self.redemption_id)
        if self.balance_after < 0:
            raise LoyaltyPointsValidationError("balance_after_must_not_be_negative")
        if self.entry_type == "ADJUST":
            # 人工调整必须由人负责。这里再挡一次,即使调用方忘了在应用层挡。
            assert_human_actor(self.created_by, code="ledger_adjust")
        return self


class PointsRedemption(_Extensible, _Audited, _FixtureBoundary):
    """A redemption request. `FULFILLED` here means "recorded as fulfilled in
    DEV/TEST", not "a gift was shipped" — fulfilment is an external effect and
    the fixture boundary forbids it."""

    redemption_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    redemption_ref: str
    item_ref: str
    item_version: int
    reward_kind: RewardKind
    points_spent: int
    status: RedemptionStatus = "REQUESTED"
    ledger_ref: str | None = None
    correlation_id: str
    idempotency_key: str | None = None
    cancelled_at: datetime | None = None
    fulfilled_at: datetime | None = None

    @model_validator(mode="after")
    def _check_redemption(self):
        assert_reward_kind_allowed(self.reward_kind)
        if self.points_spent <= 0:
            raise LoyaltyPointsValidationError("points_spent_must_be_positive")
        return self

    def mark_fulfilled(self, *, actor: str) -> PointsRedemption:
        if self.status != "REQUESTED":
            raise LoyaltyPointsConflictError(f"redemption_not_requested:{self.status}")
        now = utcnow()
        return self.model_copy(
            update={
                "status": "FULFILLED",
                "fulfilled_at": now,
                "updated_at": now,
                "updated_by": actor,
                "row_version": self.row_version + 1,
            }
        )

    def cancel(self, *, actor: str) -> PointsRedemption:
        assert_human_actor(actor, code="redemption_cancel")
        if self.status != "REQUESTED":
            raise LoyaltyPointsConflictError(f"redemption_not_cancellable:{self.status}")
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
