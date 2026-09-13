"""Add projection identity columns to ai_family_world_atoms (AIFAMILY-WM-003.6).

Fixes the P0 gap where the same authoritative source could be projected
twice under two different `atom_id`s with no mechanism to detect it.
`projection_key` gets a UNIQUE constraint — the database is the last line
of defence against a race between two concurrent workers replaying the same
source (application-level SELECT-then-INSERT dedup cannot close this race
by itself).

No backfill policy for pre-existing rows: this table was created in
migration 0080 within the same unreleased development cycle as this
migration (AIFAMILY-WM-001, this session) — there is no production data,
so the columns are added NOT NULL with no default. If a deployment somehow
already has rows in this table without a computable projection identity,
this migration intentionally fails rather than manufacturing a fake one
(see AIFAMILY-WM-003.6 task: "不得随便生成随机 projection_key 给历史行").
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0082_ai_family_world_atoms_projection_identity"
down_revision: str | None = "0081_ai_family_world_conflicts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "ai_family_world_atoms"


def upgrade() -> None:
    op.add_column(
        TABLE_NAME,
        sa.Column("projection_key", sa.String(length=64), nullable=False),
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("semantic_fingerprint", sa.String(length=64), nullable=False),
    )
    op.add_column(
        TABLE_NAME,
        sa.Column("projection_version", sa.String(length=128), nullable=False),
    )
    op.create_unique_constraint(
        "uq_ai_family_world_atoms_projection_key",
        TABLE_NAME,
        ["projection_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_ai_family_world_atoms_projection_key", TABLE_NAME, type_="unique")
    op.drop_column(TABLE_NAME, "projection_version")
    op.drop_column(TABLE_NAME, "semantic_fingerprint")
    op.drop_column(TABLE_NAME, "projection_key")
