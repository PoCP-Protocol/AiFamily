"""Persist the provider-neutral experience outbox.

Revision ID: 0007_experience_outbox
Revises: 0006_ai_human_tasks
Create Date: 2026-08-30

The outbox contains only scoped, JSON-serialised experience records.  It has
no foreign keys into Family/Journey/Service/Commerce because projection and
replay must remain independent of domain ORM models.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_experience_outbox"
down_revision: str | None = "0006_ai_human_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experience_outbox_messages",
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", postgresql.JSONB(), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_experience_outbox_tenant_idempotency",
        ),
    )
    op.create_index(
        "ix_experience_outbox_pending",
        "experience_outbox_messages",
        ["enqueued_at", "message_id"],
        postgresql_where=sa.text("published_at IS NULL"),
        sqlite_where=sa.text("published_at IS NULL"),
    )
    op.create_index(
        "ix_experience_outbox_tenant_family",
        "experience_outbox_messages",
        ["tenant_id", "family_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_experience_outbox_tenant_family",
        table_name="experience_outbox_messages",
    )
    op.drop_index(
        "ix_experience_outbox_pending",
        table_name="experience_outbox_messages",
    )
    op.drop_table("experience_outbox_messages")
