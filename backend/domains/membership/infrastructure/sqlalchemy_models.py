"""SQLAlchemy ORM models for the membership domain.

Column names mirror the SQL SSOT exactly:

* migration `0033_family_membership_entitlement_objects.sql` — plans,
  benefit_definitions, subscriptions, benefit_grants, benefit_ledger. This
  Python side maps onto the **existing** tables rather than creating a parallel
  set, so there is one schema per concept. Types are widened to `String` for
  uuid columns and `JSON` for `jsonb` so the same models run against both real
  Postgres and the in-memory SQLite engine used by the tests (same approach and
  same accepted gap as `product_intelligence`, Override #6 item 4).
* migration `0059_membership_lifecycle_v2.sql` — tier_definitions, periods,
  tier_transitions, benefit_reservations (new in V2).

No shared `packages/persistence` Base exists repo-wide yet, so this module
declares its own `declarative_base()`, to be merged once one exists.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON

Base = declarative_base()


class MembershipPlanRow(Base):
    __tablename__ = "family_membership_plans"
    plan_id = Column(String, primary_key=True)
    scope_type = Column(String, nullable=False)
    tenant_id = Column(String, nullable=True)
    plan_ref = Column(String, nullable=False)
    version_no = Column(Integer, nullable=False, default=1)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False)
    source_ref = Column(String, nullable=False)
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


class MembershipTierDefinitionRow(Base):
    """New in 0059. Note the absence of any numeric level column — see
    `domain/value_objects.py` for why that absence is deliberate."""

    __tablename__ = "family_membership_tier_definitions"
    tier_definition_id = Column(String, primary_key=True)
    scope_type = Column(String, nullable=False)
    tenant_id = Column(String, nullable=True)
    tier_code = Column(String, nullable=False)
    version_no = Column(Integer, nullable=False, default=1)
    title = Column(String, nullable=False)
    entry_rule_text = Column(Text, nullable=False)
    value_summary = Column(Text, nullable=False)
    benefit_refs = Column(JSON, nullable=False, default=list)
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


class BenefitDefinitionRow(Base):
    __tablename__ = "family_membership_benefit_definitions"
    benefit_definition_id = Column(String, primary_key=True)
    plan_id = Column(String, nullable=False)
    tenant_id = Column(String, nullable=True)
    benefit_ref = Column(String, nullable=False)
    version_no = Column(Integer, nullable=False, default=1)
    title = Column(String, nullable=False)
    allocation_type = Column(String, nullable=False)
    units_per_grant = Column(Integer, nullable=False, default=1)
    valid_days = Column(Integer, nullable=True)
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


class MembershipSubscriptionRow(Base):
    __tablename__ = "family_membership_subscriptions"
    membership_subscription_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    subject_person_id = Column(String, nullable=True)
    subscription_ref = Column(String, nullable=False)
    plan_id = Column(String, nullable=False)
    plan_ref = Column(String, nullable=False)
    plan_version = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    consent_ref = Column(String, nullable=False)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime, nullable=True)
    row_version = Column(Integer, nullable=False, default=1)
    correlation_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)
    cancelled_at = Column(DateTime, nullable=True)


class MembershipPeriodRow(Base):
    __tablename__ = "family_membership_periods"
    membership_period_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    membership_subscription_id = Column(String, nullable=True)
    period_ref = Column(String, nullable=False)
    tier_code = Column(String, nullable=False)
    seq_no = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    closed_reason = Column(String, nullable=True)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    row_version = Column(Integer, nullable=False, default=1)
    correlation_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)


class MembershipTierTransitionRow(Base):
    """Append-only. No `updated_at` / `updated_by` columns exist on purpose —
    the row cannot be edited, so there is nothing to record about an edit."""

    __tablename__ = "family_membership_tier_transitions"
    tier_transition_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    from_tier_code = Column(String, nullable=True)
    to_tier_code = Column(String, nullable=False)
    direction = Column(String, nullable=False)
    activation_source_type = Column(String, nullable=False)
    activation_source_ref = Column(String, nullable=False)
    decided_by = Column(String, nullable=False)
    decision_note = Column(Text, nullable=True)
    resulting_period_id = Column(String, nullable=True)
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


class BenefitGrantRow(Base):
    __tablename__ = "family_membership_benefit_grants"
    benefit_grant_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    subject_person_id = Column(String, nullable=True)
    membership_subscription_id = Column(String, nullable=False)
    benefit_definition_id = Column(String, nullable=False)
    benefit_ref = Column(String, nullable=False)
    grant_ref = Column(String, nullable=False)
    allocation_type = Column(String, nullable=False)
    allocated_units = Column(Integer, nullable=False)
    remaining_units = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    valid_from = Column(DateTime, nullable=False)
    valid_to = Column(DateTime, nullable=True)
    row_version = Column(Integer, nullable=False, default=1)
    correlation_id = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class BenefitReservationRow(Base):
    __tablename__ = "family_membership_benefit_reservations"
    benefit_reservation_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    benefit_grant_id = Column(String, nullable=False)
    reservation_ref = Column(String, nullable=False)
    units = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    released_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)
    environment = Column(String, nullable=False)
    source_system = Column(String, nullable=False)
    external_effect = Column(Boolean, nullable=False, default=False)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    row_version = Column(Integer, nullable=False, default=1)
    correlation_id = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False)


class BenefitLedgerEntryRow(Base):
    """Append-only, never a client write target (0033 table comment)."""

    __tablename__ = "family_membership_benefit_ledger"
    membership_benefit_ledger_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    subject_person_id = Column(String, nullable=True)
    benefit_grant_id = Column(String, nullable=False)
    ledger_ref = Column(String, nullable=False)
    action = Column(String, nullable=False)
    units = Column(Integer, nullable=False)
    remaining_units_after = Column(Integer, nullable=False)
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
