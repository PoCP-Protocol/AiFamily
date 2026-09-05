"""Persist scoped, evidence-bound Growth Graph read projections."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_ai_growth_graph_projection"
down_revision: str | None = "0022_ai_memory_store"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_growth_graph_edges",
        sa.Column("edge_id", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", sa.JSON(), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("scope_payload", sa.JSON(), nullable=False),
        sa.Column("source_node", sa.String(length=256), nullable=False),
        sa.Column("target_node", sa.String(length=256), nullable=False),
        sa.Column("relation", sa.String(length=128), nullable=False),
        sa.Column("event_ref", sa.String(length=256), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("provenance_payload", sa.JSON(), nullable=False),
        sa.Column("deletion_id", sa.String(length=256), nullable=False),
        sa.Column("retention_policy", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=256), nullable=False),
        sa.Column("causation_id", sa.String(length=256), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stable_fingerprint", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("edge_id"),
    )
    op.create_index(
        "ix_ai_growth_graph_scope_time",
        "ai_growth_graph_edges",
        ["tenant_id", "family_id", "observed_at"],
    )

    op.create_table(
        "ai_growth_graph_deletion_proofs",
        sa.Column("proof_id", sa.String(length=256), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("region_id", sa.String(length=16), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("deleted_edge_ids", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(length=256), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("proof_id"),
    )
    op.create_index(
        "ix_ai_growth_graph_deletion_proofs_tenant_id",
        "ai_growth_graph_deletion_proofs",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_growth_graph_deletion_proofs_tenant_id",
        table_name="ai_growth_graph_deletion_proofs",
    )
    op.drop_table("ai_growth_graph_deletion_proofs")
    op.drop_index("ix_ai_growth_graph_scope_time", table_name="ai_growth_graph_edges")
    op.drop_table("ai_growth_graph_edges")
