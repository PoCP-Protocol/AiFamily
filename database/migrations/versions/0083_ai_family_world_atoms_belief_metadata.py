"""Persist HYPOTHESIS belief metadata on ai_family_world_atoms (AIFAMILY-WM-004B.1).

Closes the gap where `WorldStateProposal.support_level`/`contradiction_level`
/`uncertainty` (AIFAMILY-WM-004B) existed only in-memory and were dropped on
promotion — a HYPOTHESIS atom persisted without them is indistinguishable
from a FACT to anything reading the Atom Store back. Nullable: only
HYPOTHESIS atoms are required (by `WorldStateAtom.__post_init__`) to carry
all three; every other epistemic kind leaves them NULL ("not applicable"),
never a fabricated NONE/LOW default.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0083_ai_family_world_atoms_belief_metadata"
down_revision: str | None = "0082_ai_family_world_atoms_projection_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "ai_family_world_atoms"


def upgrade() -> None:
    op.add_column(TABLE_NAME, sa.Column("support_level", sa.String(length=32), nullable=True))
    op.add_column(TABLE_NAME, sa.Column("contradiction_level", sa.String(length=32), nullable=True))
    op.add_column(TABLE_NAME, sa.Column("uncertainty", sa.String(length=32), nullable=True))
    op.create_check_constraint(
        "ck_ai_family_world_atoms_hypothesis_requires_belief_metadata",
        TABLE_NAME,
        "epistemic_kind <> 'HYPOTHESIS' OR "
        "(support_level IS NOT NULL AND contradiction_level IS NOT NULL "
        "AND uncertainty IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_ai_family_world_atoms_support_level_values",
        TABLE_NAME,
        "support_level IS NULL OR support_level IN ('NONE','WEAK','MODERATE','STRONG')",
    )
    op.create_check_constraint(
        "ck_ai_family_world_atoms_contradiction_level_values",
        TABLE_NAME,
        "contradiction_level IS NULL OR contradiction_level IN ('NONE','WEAK','MODERATE','STRONG')",
    )
    op.create_check_constraint(
        "ck_ai_family_world_atoms_uncertainty_values",
        TABLE_NAME,
        "uncertainty IS NULL OR uncertainty IN ('LOW','MEDIUM','HIGH')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_family_world_atoms_uncertainty_values", TABLE_NAME, type_="check")
    op.drop_constraint(
        "ck_ai_family_world_atoms_contradiction_level_values", TABLE_NAME, type_="check"
    )
    op.drop_constraint("ck_ai_family_world_atoms_support_level_values", TABLE_NAME, type_="check")
    op.drop_constraint(
        "ck_ai_family_world_atoms_hypothesis_requires_belief_metadata",
        TABLE_NAME,
        type_="check",
    )
    op.drop_column(TABLE_NAME, "uncertainty")
    op.drop_column(TABLE_NAME, "contradiction_level")
    op.drop_column(TABLE_NAME, "support_level")
