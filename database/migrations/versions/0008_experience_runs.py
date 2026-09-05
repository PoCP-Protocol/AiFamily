"""Persist append-only multimodal experience runs and draft checkpoints.

Revision ID: 0008_experience_runs
Revises: 0007_experience_outbox
Create Date: 2026-08-30

These tables belong to the AI runtime only.  They intentionally contain no
foreign keys into Family, Growth, Service or Commerce: a run can be replayed
without loading a business aggregate, and a model result remains a DRAFT until
an explicit human-gated named action promotes it elsewhere.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_experience_runs"
down_revision: str | None = "0007_experience_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN_STATES = "'QUEUED', 'RUNNING', 'WAITING', 'SUCCEEDED', 'FAILED', 'CANCELLED'"
_EVENT_TYPES = "'started', 'waiting', 'resumed', 'succeeded', 'failed', 'cancelled', 'checkpointed'"


def upgrade() -> None:
    op.create_table(
        "experience_runs",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", postgresql.JSONB(), nullable=False),
        sa.Column("request_ref", sa.String(length=256), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("latest_checkpoint_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.PrimaryKeyConstraint("tenant_id", "run_id"),
        sa.CheckConstraint(
            f"state IN ({_RUN_STATES})",
            name="ck_experience_runs_state",
        ),
        sa.CheckConstraint("version >= 0", name="ck_experience_runs_version_nonnegative"),
        sa.CheckConstraint("status = 'DRAFT'", name="ck_experience_runs_draft_only"),
    )
    op.create_index(
        "ix_experience_runs_tenant_family",
        "experience_runs",
        ["tenant_id", "family_id"],
    )

    op.create_table(
        "experience_run_events",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("target_state", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "event_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "idempotency_key",
            name="uq_experience_run_event_idempotency",
        ),
        sa.CheckConstraint(
            "event_sequence >= 1",
            name="ck_experience_run_event_sequence_positive",
        ),
        sa.CheckConstraint(
            f"event_type IN ({_EVENT_TYPES})",
            name="ck_experience_run_event_type",
        ),
        sa.CheckConstraint(
            f"target_state IN ({_RUN_STATES})",
            name="ck_experience_run_event_target_state",
        ),
    )
    op.create_index(
        "ix_experience_run_events_sequence",
        "experience_run_events",
        ["tenant_id", "run_id", "event_sequence"],
    )

    op.create_table(
        "experience_run_checkpoints",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=128), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("artifact_refs", postgresql.JSONB(), nullable=False),
        sa.Column("draft_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "checkpoint_id"),
        sa.CheckConstraint(
            "event_sequence >= 0",
            name="ck_experience_run_checkpoint_sequence_nonnegative",
        ),
        sa.CheckConstraint(
            f"state IN ({_RUN_STATES})",
            name="ck_experience_run_checkpoint_state",
        ),
        sa.CheckConstraint("status = 'DRAFT'", name="ck_experience_run_checkpoint_draft_only"),
    )
    op.create_index(
        "ix_experience_run_checkpoints_sequence",
        "experience_run_checkpoints",
        ["tenant_id", "run_id", "event_sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_experience_run_checkpoints_sequence",
        table_name="experience_run_checkpoints",
    )
    op.drop_table("experience_run_checkpoints")
    op.drop_index("ix_experience_run_events_sequence", table_name="experience_run_events")
    op.drop_table("experience_run_events")
    op.drop_index("ix_experience_runs_tenant_family", table_name="experience_runs")
    op.drop_table("experience_runs")
