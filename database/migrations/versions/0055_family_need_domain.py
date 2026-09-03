"""Persistence for the Family Need bounded context (N0-N3 aggregates).

Four tables, one per aggregate root in
``backend/domains/family_need/domain/entities.py``: need_signals (N0),
family_needs (N1-N8), need_profiles (N2) and solution_drafts (N3). Every row
carries the multi-tenant/family scope from ``NeedContext`` (tenant_id,
family_id, purpose, consent_version, data_class, locale, region) so a
PostgreSQL adapter can enforce the same visibility rule the in-memory fake
already enforces (`context.tenant_id == tenant_id and context.family_id ==
family_id`). Enums are stored as ``VARCHAR`` + ``CHECK`` constraints, matching
this repository's existing style (see e.g. 0054's ``status`` check) rather
than native ``CREATE TYPE ... AS ENUM``, so a future enum member is a
constraint-only migration and never a type-alteration migration.

Revision ID: 0055_family_need_domain
Revises: 0054_ai_engagement_draft_reviews
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055_family_need_domain"
down_revision: str | None = "0054_ai_engagement_draft_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DATA_CLASS_VALUES = (
    "PUBLIC",
    "INTERNAL",
    "FAMILY_PRIVATE",
    "SENSITIVE_PERSONAL_DATA",
    "MINOR_PERSONAL_DATA",
)
_ACTOR_TYPE_VALUES = (
    "FAMILY_MEMBER",
    "FAMILY_GUARDIAN",
    "OPERATOR",
    "PROVIDER",
    "SYSTEM",
    "AI",
)
_SIGNAL_SOURCE_VALUES = (
    "ASSESSMENT",
    "FAMILY_CONVERSATION",
    "FAMILY_SEARCH",
    "SERVICE_FEEDBACK",
    "FAMILY_EXPRESSED",
    "SUPPORT_REQUEST",
)
_SIGNAL_STATUS_VALUES = ("ACTIVE", "RETRACTED", "EXPIRED")
_NEED_STATUS_VALUES = (
    "CAPTURED",
    "CLARIFYING",
    "CONFIRMED",
    "REJECTED",
    "PAUSED",
    "PROFILED",
    "SOLUTIONING",
    "FULFILLING",
    "FULFILLED",
    "CLOSED",
)
_NEED_CATEGORY_VALUES = (
    "EDUCATION",
    "FAMILY_RELATIONSHIP",
    "GROWTH_COMPANIONSHIP",
    "LIFE_SUPPORT",
    "SERVICE_SUPPORT",
    "OTHER",
)
_EMOTIONAL_GATE_VALUES = (
    "E0_WELCOME",
    "E1_SEEN",
    "E2_SAFE_TO_ACT",
    "E3_VALUE_CONFIRMED",
    "E4_ECONOMIC_CHOICE",
)
_NEED_URGENCY_VALUES = ("NOW", "SOON", "WHEN_READY")
_NEED_COMPLEXITY_VALUES = ("SIMPLE", "COMPOUND", "CROSS_DOMAIN")
_RISK_LEVEL_VALUES = ("LOW", "MEDIUM", "HIGH", "HUMAN_REVIEW_REQUIRED")
_INTERVENTION_TIER_VALUES = (
    "UNIVERSAL",
    "LIGHT_GUIDANCE",
    "STANDARD_SELECTIVE",
    "INTENSIVE_SELECTIVE",
    "ENHANCED_SUPPORT",
)
_SUPPLY_SHAPE_VALUES = ("PRODUCT", "SERVICE", "SOLUTION")
_SOLUTION_DRAFT_STATUS_VALUES = (
    "DRAFT",
    "FAMILY_REVIEW",
    "APPROVED",
    "REJECTED",
    "PAUSED",
    "STALE",
)


def _check_in(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ",".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} in ({quoted})", name=name)


def upgrade() -> None:
    op.create_table(
        "need_signals",
        sa.Column("signal_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("data_class", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=8), nullable=False),
        sa.Column("subject_person_ids", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("causation_id", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        _check_in("data_class", _DATA_CLASS_VALUES, "ck_need_signals_data_class"),
        _check_in("actor_type", _ACTOR_TYPE_VALUES, "ck_need_signals_actor_type"),
        _check_in("source", _SIGNAL_SOURCE_VALUES, "ck_need_signals_source"),
        _check_in("status", _SIGNAL_STATUS_VALUES, "ck_need_signals_status"),
        sa.PrimaryKeyConstraint("tenant_id", "signal_id"),
    )
    op.create_index(
        "ix_need_signals_family_scope",
        "need_signals",
        ["tenant_id", "family_id", "captured_at"],
    )
    op.create_index(
        "uq_need_signals_idempotency",
        "need_signals",
        ["tenant_id", "family_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key is not null"),
    )

    op.create_table(
        "family_needs",
        sa.Column("need_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("data_class", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=8), nullable=False),
        sa.Column("subject_person_ids", sa.JSON(), nullable=False),
        sa.Column("context_subject_person_ids", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("causation_id", sa.String(length=128), nullable=True),
        sa.Column("source_signal_ids", sa.JSON(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("desired_outcome", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("emotional_gate", sa.String(length=24), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("confirmed_by_actor_id", sa.String(length=128), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("pause_reason", sa.Text(), nullable=True),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        _check_in("data_class", _DATA_CLASS_VALUES, "ck_family_needs_data_class"),
        _check_in("actor_type", _ACTOR_TYPE_VALUES, "ck_family_needs_actor_type"),
        _check_in("category", _NEED_CATEGORY_VALUES, "ck_family_needs_category"),
        _check_in("status", _NEED_STATUS_VALUES, "ck_family_needs_status"),
        _check_in("emotional_gate", _EMOTIONAL_GATE_VALUES, "ck_family_needs_emotional_gate"),
        sa.CheckConstraint("version >= 1", name="ck_family_needs_version_positive"),
        sa.PrimaryKeyConstraint("tenant_id", "need_id"),
    )
    op.create_index(
        "ix_family_needs_family_scope",
        "family_needs",
        ["tenant_id", "family_id", "status"],
    )
    op.create_index(
        "uq_family_needs_idempotency",
        "family_needs",
        ["tenant_id", "family_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key is not null"),
    )

    op.create_table(
        "need_profiles",
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("need_id", sa.String(length=64), nullable=False),
        sa.Column("need_version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("data_class", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=8), nullable=False),
        sa.Column("subject_person_ids", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("causation_id", sa.String(length=128), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("urgency", sa.String(length=16), nullable=False),
        sa.Column("complexity", sa.String(length=16), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("intervention_tier", sa.String(length=32), nullable=False),
        sa.Column("preferred_shapes", sa.JSON(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("required_capability_keys", sa.JSON(), nullable=False),
        sa.Column("profile_locale", sa.String(length=16), nullable=True),
        sa.Column("profile_region", sa.String(length=16), nullable=True),
        sa.Column("confirmed_by_actor_id", sa.String(length=128), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        _check_in("data_class", _DATA_CLASS_VALUES, "ck_need_profiles_data_class"),
        _check_in("actor_type", _ACTOR_TYPE_VALUES, "ck_need_profiles_actor_type"),
        _check_in("category", _NEED_CATEGORY_VALUES, "ck_need_profiles_category"),
        _check_in("urgency", _NEED_URGENCY_VALUES, "ck_need_profiles_urgency"),
        _check_in("complexity", _NEED_COMPLEXITY_VALUES, "ck_need_profiles_complexity"),
        _check_in("risk_level", _RISK_LEVEL_VALUES, "ck_need_profiles_risk_level"),
        _check_in(
            "intervention_tier", _INTERVENTION_TIER_VALUES, "ck_need_profiles_intervention_tier"
        ),
        sa.CheckConstraint("version >= 1", name="ck_need_profiles_version_positive"),
        sa.CheckConstraint("need_version >= 1", name="ck_need_profiles_need_version_positive"),
        sa.PrimaryKeyConstraint("tenant_id", "profile_id"),
    )
    op.create_index(
        "ix_need_profiles_family_scope",
        "need_profiles",
        ["tenant_id", "family_id", "need_id"],
    )
    op.create_index(
        "uq_need_profiles_idempotency",
        "need_profiles",
        ["tenant_id", "family_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key is not null"),
    )

    op.create_table(
        "solution_drafts",
        sa.Column("draft_id", sa.String(length=64), nullable=False),
        sa.Column("need_id", sa.String(length=64), nullable=False),
        sa.Column("need_profile_id", sa.String(length=64), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=False),
        sa.Column("data_class", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=8), nullable=False),
        sa.Column("subject_person_ids", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("causation_id", sa.String(length=128), nullable=True),
        sa.Column("shape", sa.String(length=16), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("emotional_gate", sa.String(length=24), nullable=False),
        sa.Column("commercial_intent", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("author_type", sa.String(length=32), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("estimated_cost_minor", sa.BigInteger(), nullable=True),
        sa.Column("sla_hours", sa.Integer(), nullable=True),
        sa.Column("can_pause", sa.Boolean(), nullable=False),
        sa.Column("can_exit", sa.Boolean(), nullable=False),
        sa.Column("respectful_language", sa.Boolean(), nullable=False),
        sa.Column("manipulative", sa.Boolean(), nullable=False),
        sa.Column("approved_by_actor_id", sa.String(length=128), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "requires_human_case_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("human_case_review_note", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        _check_in("data_class", _DATA_CLASS_VALUES, "ck_solution_drafts_data_class"),
        _check_in("actor_type", _ACTOR_TYPE_VALUES, "ck_solution_drafts_actor_type"),
        _check_in("shape", _SUPPLY_SHAPE_VALUES, "ck_solution_drafts_shape"),
        _check_in("emotional_gate", _EMOTIONAL_GATE_VALUES, "ck_solution_drafts_emotional_gate"),
        _check_in("status", _SOLUTION_DRAFT_STATUS_VALUES, "ck_solution_drafts_status"),
        _check_in("author_type", _ACTOR_TYPE_VALUES, "ck_solution_drafts_author_type"),
        sa.CheckConstraint(
            "estimated_cost_minor is null or estimated_cost_minor >= 0",
            name="ck_solution_drafts_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "sla_hours is null or sla_hours >= 0", name="ck_solution_drafts_sla_nonnegative"
        ),
        sa.CheckConstraint(
            "profile_version >= 1", name="ck_solution_drafts_profile_version_positive"
        ),
        sa.PrimaryKeyConstraint("tenant_id", "draft_id"),
    )
    op.create_index(
        "ix_solution_drafts_family_scope",
        "solution_drafts",
        ["tenant_id", "family_id", "need_id"],
    )
    op.create_index(
        "uq_solution_drafts_idempotency",
        "solution_drafts",
        ["tenant_id", "family_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key is not null"),
    )

    op.create_table(
        "family_need_events",
        sa.Column(
            "event_id",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("gen_random_uuid()::text"),
        ),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=160), nullable=True),
        sa.Column("data_class", sa.String(length=32), nullable=True),
        sa.Column("subject_person_ids", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_family_need_events_aggregate",
        "family_need_events",
        ["tenant_id", "aggregate_id", "version"],
    )
    op.create_index(
        "uq_family_need_events_idempotency",
        "family_need_events",
        ["aggregate_id", "version", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key is not null"),
    )


def downgrade() -> None:
    op.drop_index("uq_family_need_events_idempotency", table_name="family_need_events")
    op.drop_index("ix_family_need_events_aggregate", table_name="family_need_events")
    op.drop_table("family_need_events")

    op.drop_index("uq_solution_drafts_idempotency", table_name="solution_drafts")
    op.drop_index("ix_solution_drafts_family_scope", table_name="solution_drafts")
    op.drop_table("solution_drafts")

    op.drop_index("uq_need_profiles_idempotency", table_name="need_profiles")
    op.drop_index("ix_need_profiles_family_scope", table_name="need_profiles")
    op.drop_table("need_profiles")

    op.drop_index("uq_family_needs_idempotency", table_name="family_needs")
    op.drop_index("ix_family_needs_family_scope", table_name="family_needs")
    op.drop_table("family_needs")

    op.drop_index("uq_need_signals_idempotency", table_name="need_signals")
    op.drop_index("ix_need_signals_family_scope", table_name="need_signals")
    op.drop_table("need_signals")
