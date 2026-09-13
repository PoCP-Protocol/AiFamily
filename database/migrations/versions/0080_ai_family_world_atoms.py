"""Persist Family World State Kernel atoms (AIFAMILY-WM-001).

Creates `ai_family_world_atoms`, the durable Atom Store behind
`backend/intelligence/context_engine/world_state.py`. This is a projection
table, not a second authoritative business database: every row is written
through `promote_proposal_to_atom` or an equivalent construction path that
already enforces the epistemic invariants (AI cannot assert FACT, derived
kinds require evidence) before a row ever reaches this table. Bitemporal by
design: `valid_from`/`valid_until` is when the claim was true in the real
world, `recorded_at` is when AiFamily learned it — the two are allowed to
diverge, and neither column is ever UPDATEd after insert (append + supersede,
never mutate; see `world_state.py` module docstring).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0080_ai_family_world_atoms"
down_revision: str | None = "0079_platform_notification_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "ai_family_world_atoms"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("atom_id", sa.String(length=256), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("family_id", sa.String(length=128), nullable=False),
        sa.Column("subject_ids", sa.JSON(), nullable=False),
        sa.Column("epistemic_kind", sa.String(length=32), nullable=False),
        sa.Column("predicate", sa.String(length=256), nullable=False),
        sa.Column("value_ref", sa.Text(), nullable=False),
        sa.Column("asserted_by", sa.String(length=256), nullable=False),
        sa.Column("attributed_actor_type", sa.String(length=32), nullable=False),
        sa.Column("provenance", sa.String(length=512), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("supersedes", sa.String(length=256), nullable=True),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("consent_version", sa.String(length=128), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "epistemic_kind IN ("
            "'FACT','OBSERVATION','SELF_REPORT','OTHER_REPORT',"
            "'PERSPECTIVE','HYPOTHESIS','UNKNOWN')",
            name="ck_ai_family_world_atoms_epistemic_kind",
        ),
        sa.CheckConstraint(
            "attributed_actor_type IN ("
            "'FAMILY_MEMBER','FAMILY_GUARDIAN','PROFESSIONAL','SYSTEM','AI')",
            name="ck_ai_family_world_atoms_actor_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','SUPERSEDED','RETRACTED')",
            name="ck_ai_family_world_atoms_status",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_ai_family_world_atoms_valid_range",
        ),
        sa.CheckConstraint(
            "NOT (attributed_actor_type = 'AI' AND epistemic_kind IN "
            "('FACT','OBSERVATION','SELF_REPORT','OTHER_REPORT'))",
            name="ck_ai_family_world_atoms_ai_cannot_assert_fact",
        ),
    )
    op.create_index(
        "idx_ai_family_world_atoms_family_predicate",
        TABLE_NAME,
        ["tenant_id", "family_id", "predicate", "status"],
    )
    op.create_index(
        "idx_ai_family_world_atoms_temporal",
        TABLE_NAME,
        ["family_id", "valid_from", "valid_until"],
    )
    op.create_index(
        "idx_ai_family_world_atoms_recorded_at",
        TABLE_NAME,
        ["family_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_ai_family_world_atoms_recorded_at", table_name=TABLE_NAME)
    op.drop_index("idx_ai_family_world_atoms_temporal", table_name=TABLE_NAME)
    op.drop_index("idx_ai_family_world_atoms_family_predicate", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
