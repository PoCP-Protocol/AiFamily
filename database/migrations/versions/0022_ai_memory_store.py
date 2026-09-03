"""Persist scoped AI memory references and deletion proofs."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_ai_memory_store"
down_revision: str | None = "0021_ai_telemetry_spans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_memories",
        sa.Column("memory_id", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", sa.JSON(), nullable=False),
        sa.Column("memory_ref", sa.String(length=512), nullable=False),
        sa.Column("memory_scope", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("consent_granted", sa.Boolean(), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("provenance_payload", sa.JSON(), nullable=False),
        sa.Column("deletion_id", sa.String(length=256), nullable=False),
        sa.Column("retention_policy", sa.String(length=128), nullable=False),
        sa.Column("source_ref", sa.String(length=512), nullable=False),
        sa.Column("correlation_id", sa.String(length=256), nullable=False),
        sa.Column("causation_id", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("derived_memory_ids", sa.JSON(), nullable=False),
        sa.Column("stable_fingerprint", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("memory_id"),
    )
    op.create_index(
        "ix_ai_memories_scope_expiry", "ai_memories", ["tenant_id", "family_id", "expires_at"]
    )
    op.create_index("ix_ai_memories_deletion", "ai_memories", ["tenant_id", "deletion_id"])

    op.create_table(
        "ai_memory_deletion_proofs",
        sa.Column("proof_id", sa.String(length=256), nullable=False),
        sa.Column("deletion_id", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", sa.JSON(), nullable=False),
        sa.Column("deleted_memory_ids", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(length=256), nullable=False),
        sa.Column("provenance_ref", sa.String(length=256), nullable=False),
        sa.Column("correlation_id", sa.String(length=256), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("proof_id"),
        sa.UniqueConstraint("deletion_id"),
    )
    op.create_index(
        "ix_ai_memory_deletion_proofs_tenant_id",
        "ai_memory_deletion_proofs",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_memory_deletion_proofs_tenant_id", table_name="ai_memory_deletion_proofs")
    op.drop_table("ai_memory_deletion_proofs")
    op.drop_index("ix_ai_memories_deletion", table_name="ai_memories")
    op.drop_index("ix_ai_memories_scope_expiry", table_name="ai_memories")
    op.drop_table("ai_memories")
