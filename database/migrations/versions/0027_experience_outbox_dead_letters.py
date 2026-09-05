"""Persist metadata-only Experience Outbox dead letters.

Revision ID: 0027_experience_outbox_dead_letters
Revises: 0026_experience_outbox_delivery_attempts
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_experience_outbox_dead_letters"
down_revision: str | None = "0026_experience_outbox_delivery_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experience_outbox_dead_letters",
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 1", name="ck_experience_dead_letter_attempts"),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_experience_outbox_dead_letters_tenant_id",
        "experience_outbox_dead_letters",
        ["tenant_id"],
    )
    op.create_index(
        "ix_experience_outbox_dead_letters_family_id",
        "experience_outbox_dead_letters",
        ["family_id"],
    )
    op.create_index(
        "ix_experience_outbox_dead_letters_dead_lettered_at",
        "experience_outbox_dead_letters",
        ["dead_lettered_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_experience_outbox_dead_letters_dead_lettered_at",
        table_name="experience_outbox_dead_letters",
    )
    op.drop_index(
        "ix_experience_outbox_dead_letters_family_id",
        table_name="experience_outbox_dead_letters",
    )
    op.drop_index(
        "ix_experience_outbox_dead_letters_tenant_id",
        table_name="experience_outbox_dead_letters",
    )
    op.drop_table("experience_outbox_dead_letters")
