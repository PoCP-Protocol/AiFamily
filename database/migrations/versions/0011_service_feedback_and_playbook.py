"""Persist bounded service feedback, quality decisions, named actions and outbox.

This revision extends the existing canonical service booking chain.  It does
not create a commerce ledger, an expert marketplace, or a second service
backend.  All tables are tenant/family scoped and the service outbox is an
append-only integration boundary; external consumers decide whether anything
else happens.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_service_feedback_playbook"
down_revision: str | None = "0010_experience_run_interactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _scoped_idempotency(table: str, name: str) -> None:
    op.create_index(
        name,
        table,
        ["tenant_id", "family_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )


def upgrade() -> None:
    common = [
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("external_effect", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attributes_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    ]

    op.create_table(
        "family_service_family_feedback",
        sa.Column("family_feedback_id", sa.String(length=128), primary_key=True),
        sa.Column("booking_request_id", sa.String(length=128), nullable=False),
        sa.Column("delivery_record_id", sa.String(length=128), nullable=False),
        sa.Column("author_person_id", sa.String(length=128), nullable=False),
        sa.Column("author_role", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("issue_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("consent_ref", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("retention_class", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        *common,
        sa.CheckConstraint(
            "outcome IN ('HELPFUL','SOMEWHAT_HELPFUL','NOT_HELPFUL_YET')",
            name="ck_family_service_feedback_outcome",
        ),
        sa.CheckConstraint(
            "environment IN ('DEV','TEST')", name="ck_family_service_feedback_environment"
        ),
        sa.CheckConstraint(
            "external_effect = false", name="ck_family_service_feedback_external_effect"
        ),
    )
    _scoped_idempotency("family_service_family_feedback", "uq_family_service_feedback_idempotency")

    op.create_table(
        "family_service_quality_decisions",
        sa.Column("quality_decision_id", sa.String(length=128), primary_key=True),
        sa.Column("booking_request_id", sa.String(length=128), nullable=False),
        sa.Column("delivery_record_id", sa.String(length=128), nullable=False),
        sa.Column("family_feedback_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decided_by", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("retention_class", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        *common,
        sa.CheckConstraint(
            "status IN ('ACCEPTED','REWORK_REQUIRED','REFUND_REQUIRED')",
            name="ck_family_service_quality_status",
        ),
        sa.CheckConstraint(
            "environment IN ('DEV','TEST')", name="ck_family_service_quality_environment"
        ),
        sa.CheckConstraint(
            "external_effect = false", name="ck_family_service_quality_external_effect"
        ),
    )
    _scoped_idempotency("family_service_quality_decisions", "uq_family_service_quality_idempotency")

    op.create_table(
        "family_service_actions",
        sa.Column("service_action_id", sa.String(length=128), primary_key=True),
        sa.Column("booking_request_id", sa.String(length=128), nullable=False),
        sa.Column("delivery_record_id", sa.String(length=128), nullable=True),
        sa.Column("family_feedback_id", sa.String(length=128), nullable=True),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_person_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("retention_class", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        *common,
        sa.CheckConstraint(
            "action_type IN ('WELCOME','NEEDS_IDENTIFIED','FIRST_RESPONSE','FOLLOW_UP',"
            "'REMEDY_REWORK','REMEDY_REASSIGN','REFUND_REQUESTED')",
            name="ck_family_service_action_type",
        ),
        sa.CheckConstraint(
            "environment IN ('DEV','TEST')", name="ck_family_service_action_environment"
        ),
        sa.CheckConstraint(
            "external_effect = false", name="ck_family_service_action_external_effect"
        ),
    )
    _scoped_idempotency("family_service_actions", "uq_family_service_action_idempotency")

    op.create_table(
        "family_service_outbox_events",
        sa.Column("service_event_id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("external_effect", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("attributes_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_family_service_event_tenant_idempotency"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PUBLISHED','DEAD_LETTER')",
            name="ck_family_service_event_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_family_service_event_attempts"),
        sa.CheckConstraint(
            "environment IN ('DEV','TEST')", name="ck_family_service_event_environment"
        ),
        sa.CheckConstraint(
            "external_effect = false", name="ck_family_service_event_external_effect"
        ),
    )
    op.create_index(
        "ix_family_service_outbox_pending",
        "family_service_outbox_events",
        ["tenant_id", "occurred_at", "service_event_id"],
        postgresql_where=sa.text("status = 'PENDING'"),
        sqlite_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index("ix_family_service_outbox_pending", table_name="family_service_outbox_events")
    op.drop_table("family_service_outbox_events")
    for table, index in (
        ("family_service_actions", "uq_family_service_action_idempotency"),
        ("family_service_quality_decisions", "uq_family_service_quality_idempotency"),
        ("family_service_family_feedback", "uq_family_service_feedback_idempotency"),
    ):
        op.drop_index(index, table_name=table)
        op.drop_table(table)
