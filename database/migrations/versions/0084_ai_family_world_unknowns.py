"""Durable Unknown store (AIFAMILY-WM-004C, B10).

`UnknownState` is the only canonical ignorance object in this kernel (see
`unknown_engine.py` module docstring) — this is its persistence, not a
second representation. `UNIQUE(unknown_key)` is what makes duplicate
generation (same cognitive gap, different wording, or a concurrent race)
collapse to one row at the database layer, not just in application code.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0084_ai_family_world_unknowns"
down_revision: str | None = "0083_ai_family_world_atoms_belief_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "ai_family_world_unknowns"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("unknown_id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("target_predicate", sa.String(length=256), nullable=False),
        sa.Column("decision_impact", sa.String(length=16), nullable=False),
        sa.Column("answerability", sa.String(length=16), nullable=False),
        sa.Column("urgency", sa.String(length=16), nullable=False),
        sa.Column("preferred_source", sa.String(length=256), nullable=True),
        sa.Column("blocking_refs", sa.Text(), nullable=False),
        sa.Column("unknown_key", sa.String(length=64), nullable=False),
        sa.Column("source_refs", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("resolution_refs", sa.Text(), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=64), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("unknown_key", name="uq_ai_family_world_unknowns_unknown_key"),
        sa.CheckConstraint(
            "status <> 'RESOLVED' OR resolution_refs <> '[]'",
            name="ck_ai_family_world_unknowns_resolved_requires_refs",
        ),
        sa.CheckConstraint(
            "decision_impact IN ('LOW','MEDIUM','HIGH')",
            name="ck_ai_family_world_unknowns_decision_impact_values",
        ),
        sa.CheckConstraint(
            "answerability IN ('LOW','MEDIUM','HIGH')",
            name="ck_ai_family_world_unknowns_answerability_values",
        ),
        sa.CheckConstraint(
            "urgency IN ('LOW','MEDIUM','HIGH')",
            name="ck_ai_family_world_unknowns_urgency_values",
        ),
        sa.CheckConstraint(
            "priority IN ('LOW','NORMAL','HIGH','CRITICAL')",
            name="ck_ai_family_world_unknowns_priority_values",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','RESOLVED','DISMISSED','STALE')",
            name="ck_ai_family_world_unknowns_status_values",
        ),
    )
    op.create_index(
        "ix_ai_family_world_unknowns_family_status",
        TABLE_NAME,
        ["tenant_id", "family_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_family_world_unknowns_family_status", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
