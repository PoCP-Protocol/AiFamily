"""Persist Experience Outbox delivery attempts and terminal metadata.

Revision ID: 0026_experience_outbox_delivery_attempts
Revises: 0025_service_blueprint_proposals
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_experience_outbox_delivery_attempts"
down_revision: str | None = "0025_service_blueprint_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic creates ``alembic_version.version_num`` as VARCHAR(32).  This is
    # the first revision whose immutable id exceeds that limit, so PostgreSQL
    # must widen the bookkeeping column before Alembic records this revision.
    # Keep the wider type on downgrade: Alembic updates version_num only after
    # this function returns, while it still contains the long current id.
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=False,
    )
    op.create_table(
        "experience_outbox_delivery_attempts",
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(length=160), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="ck_experience_delivery_attempts_nonnegative"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PUBLISHED', 'DEAD_LETTERED')",
            name="ck_experience_delivery_attempt_status",
        ),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_experience_outbox_delivery_attempts_status",
        "experience_outbox_delivery_attempts",
        ["status"],
    )
    op.create_index(
        "ix_experience_outbox_delivery_attempts_updated_at",
        "experience_outbox_delivery_attempts",
        ["updated_at"],
    )
    op.create_index(
        "ix_experience_outbox_delivery_attempts_lease_until",
        "experience_outbox_delivery_attempts",
        ["lease_until"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_experience_outbox_delivery_attempts_lease_until",
        table_name="experience_outbox_delivery_attempts",
    )
    op.drop_index(
        "ix_experience_outbox_delivery_attempts_updated_at",
        table_name="experience_outbox_delivery_attempts",
    )
    op.drop_index(
        "ix_experience_outbox_delivery_attempts_status",
        table_name="experience_outbox_delivery_attempts",
    )
    op.drop_table("experience_outbox_delivery_attempts")
