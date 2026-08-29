"""SQLAlchemy ORM models for the loyalty points domain.

New tables — there is no predecessor schema to map onto. The source repository's
only "points" artefact was a hard-coded fixture
(`dev_points: { balance: 1280, source: 'DEV_FIXTURE', redeemable: false }`), so
this is a first schema rather than a migration of one.

Two shapes worth noticing:

* `family_loyalty_points_accounts` has **no balance column.** Balance is
  `SUM(points_delta)` over the ledger. A guardrail test asserts no column named
  like a balance/score/cash value exists on any table here.
* `family_loyalty_points_ledger` is append-only. It carries `balance_after` as a
  *snapshot at write time* (so each row explains itself), while every query
  recomputes the balance from the deltas — a test pins the last row's
  `balance_after` to that sum so the two cannot drift.

`String` for uuid columns and `JSON` for `jsonb` so the same models run against
both real Postgres and the in-memory SQLite engine the tests use. No shared
`packages/persistence` declarative Base exists repo-wide yet, so this module
declares its own, to be merged when one lands.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON

Base = declarative_base()


class PointsEarnRuleRow(Base):
    __tablename__ = "family_loyalty_points_earn_rules"
    rule_id = Column(String, primary_key=True)
    scope_type = Column(String, nullable=False)
    tenant_id = Column(String, nullable=True)
    rule_ref = Column(String, nullable=False)
    version_no = Column(Integer, nullable=False, default=1)
    title = Column(String, nullable=False)
    explanation = Column(Text, nullable=False)
    source_kind = Column(String, nullable=False)
    points_per_event = Column(Integer, nullable=False)
    daily_cap = Column(Integer, nullable=True)
    total_cap = Column(Integer, nullable=True)
    requires_qualification = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False)
    fixture_only = Column(Boolean, nullable=False, default=True)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime, nullable=True)
    row_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)


class RedemptionCatalogItemRow(Base):
    __tablename__ = "family_loyalty_points_redemption_items"
    item_id = Column(String, primary_key=True)
    scope_type = Column(String, nullable=False)
    tenant_id = Column(String, nullable=True)
    item_ref = Column(String, nullable=False)
    version_no = Column(Integer, nullable=False, default=1)
    title = Column(String, nullable=False)
    reward_kind = Column(String, nullable=False)
    points_price = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    fixture_only = Column(Boolean, nullable=False, default=True)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime, nullable=True)
    row_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)


class PointsAccountRow(Base):
    """No balance column, deliberately — see module docstring."""

    __tablename__ = "family_loyalty_points_accounts"
    points_account_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    account_ref = Column(String, nullable=False)
    status = Column(String, nullable=False)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    row_version = Column(Integer, nullable=False, default=1)
    correlation_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    frozen_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)


class PointsLedgerEntryRow(Base):
    """Append-only. No `updated_at`/`updated_by` columns exist, because the row
    cannot be edited — a correction is a new compensating ADJUST entry."""

    __tablename__ = "family_loyalty_points_ledger"
    ledger_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    points_account_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    subject_person_id = Column(String, nullable=True)
    ledger_ref = Column(String, nullable=False)
    entry_type = Column(String, nullable=False)
    points_delta = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    rule_ref = Column(String, nullable=True)
    redemption_id = Column(String, nullable=True)
    evidence_ref = Column(String, nullable=True)
    reason_code = Column(String, nullable=True)
    qualification_ref = Column(String, nullable=True)
    source_page_id = Column(String, nullable=False)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    correlation_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    occurred_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)


class PointsRedemptionRow(Base):
    __tablename__ = "family_loyalty_points_redemptions"
    redemption_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    redemption_ref = Column(String, nullable=False)
    item_ref = Column(String, nullable=False)
    item_version = Column(Integer, nullable=False)
    reward_kind = Column(String, nullable=False)
    points_spent = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    ledger_ref = Column(String, nullable=True)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    row_version = Column(Integer, nullable=False, default=1)
    correlation_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    fulfilled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)
