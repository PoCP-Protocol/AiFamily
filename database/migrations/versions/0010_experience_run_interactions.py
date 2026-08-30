"""Persist append-only Web experience interactions and deletion metadata.

Revision ID: 0010_experience_run_interactions
Revises: 0009_ai_model_drafts
Create Date: 2026-08-30

The interaction stream belongs to the AI runtime.  It records human
decisions, feedback, escalation and deletion requests without promoting a
model draft into a business fact.  Deletion is represented by an append-only
event; derived draft/artifact material is then scrubbed as a privacy erase.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_experience_run_interactions"
down_revision: str | None = "0009_ai_model_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INTERACTION_TYPES = "'decision', 'feedback', 'human_review', 'delete'"


def upgrade() -> None:
    # A create request is not a user interaction, so its idempotency material
    # lives on the run envelope.  It lets a process restart replay the exact
    # create response without inventing a synthetic interaction type.
    op.add_column(
        "experience_runs",
        sa.Column("create_idempotency_key", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "experience_runs",
        sa.Column("create_fingerprint", sa.Text(), nullable=True),
    )
    op.add_column(
        "experience_runs",
        sa.Column("create_status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "experience_runs",
        sa.Column("create_response_payload", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "experience_runs",
        sa.Column(
            "deletion_state",
            sa.String(length=16),
            nullable=False,
            server_default="active",
        ),
    )
    op.create_check_constraint(
        "ck_experience_runs_deletion_state",
        "experience_runs",
        "deletion_state IN ('active', 'deleted')",
    )
    op.create_check_constraint(
        "ck_experience_runs_create_status",
        "experience_runs",
        "create_status IS NULL OR create_status IN ('RESERVED', 'FINALIZED')",
    )

    op.create_table(
        "experience_run_interactions",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("interaction_id", sa.String(length=160), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", postgresql.JSONB(), nullable=False),
        sa.Column("interaction_type", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "interaction_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "idempotency_key",
            name="uq_experience_run_interaction_idempotency",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "event_sequence",
            name="uq_experience_run_interaction_sequence",
        ),
        sa.CheckConstraint(
            f"interaction_type IN ({_INTERACTION_TYPES})",
            name="ck_experience_run_interaction_type",
        ),
        sa.CheckConstraint(
            "event_sequence >= 1",
            name="ck_experience_run_interaction_sequence_positive",
        ),
    )
    op.create_index(
        "ix_experience_run_interactions_scope",
        "experience_run_interactions",
        ["tenant_id", "family_id", "run_id"],
    )
    op.create_index(
        "ix_experience_run_interactions_sequence",
        "experience_run_interactions",
        ["tenant_id", "run_id", "event_sequence"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_experience_run_interactions_sequence",
        table_name="experience_run_interactions",
    )
    op.drop_index(
        "ix_experience_run_interactions_scope",
        table_name="experience_run_interactions",
    )
    op.drop_table("experience_run_interactions")
    op.drop_constraint(
        "ck_experience_runs_create_status",
        "experience_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_experience_runs_deletion_state",
        "experience_runs",
        type_="check",
    )
    op.drop_column("experience_runs", "deletion_state")
    op.drop_column("experience_runs", "create_response_payload")
    op.drop_column("experience_runs", "create_status")
    op.drop_column("experience_runs", "create_fingerprint")
    op.drop_column("experience_runs", "create_idempotency_key")
