"""Persist Multi-Perspective Conflict Engine detections (AIFAMILY-WM-004A).

Creates `ai_family_world_conflicts`. Detection itself
(`backend/intelligence/context_engine/conflict_engine.py`) is pure and
in-memory; this table is where a detected conflict becomes durable so it
survives a restart and is never silently dropped once found.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0081_ai_family_world_conflicts"
down_revision: str | None = "0080_ai_family_world_atoms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "ai_family_world_conflicts"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("conflict_id", sa.String(length=256), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("predicate", sa.String(length=256), nullable=False),
        sa.Column("atom_id_a", sa.String(length=256), nullable=False),
        sa.Column("atom_id_b", sa.String(length=256), nullable=False),
        sa.Column("conflict_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "conflict_type IN ("
            "'SOURCE_DISAGREEMENT','TEMPORAL_CONFLICT','FACT_CONFLICT','PERSPECTIVE_CONFLICT')",
            name="ck_ai_family_world_conflicts_type",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','RESOLVED','ACCEPTED_AMBIGUITY','STALE')",
            name="ck_ai_family_world_conflicts_status",
        ),
        sa.CheckConstraint(
            "atom_id_a <> atom_id_b",
            name="ck_ai_family_world_conflicts_distinct_atoms",
        ),
        sa.CheckConstraint(
            "status <> 'RESOLVED' OR resolution_note IS NOT NULL",
            name="ck_ai_family_world_conflicts_resolution_note_required",
        ),
    )
    op.create_index(
        "idx_ai_family_world_conflicts_family_predicate",
        TABLE_NAME,
        ["tenant_id", "family_id", "predicate", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_family_world_conflicts_family_predicate", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
