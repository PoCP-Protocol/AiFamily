"""Persist tenant-scoped competitor evidence DRAFT cards.

Competitor evidence is an evidence card, not a ranking or a business fact.
The table stores the immutable DRAFT envelope and explicit scope metadata so
it can be reviewed and traced before any product lifecycle transition.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_competitor_evidence"
down_revision: str | None = "0038_product_definition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_intelligence_competitor_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("tenant_scope", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="DRAFT"),
        sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("assumptions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("unknowns", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("next_validation", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance_ref", sa.String(), nullable=True),
        sa.Column("model_ref", sa.String(), nullable=True),
        sa.Column("prompt_use_case_version", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("competitor_ref", sa.String(), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_status", sa.String(length=32), nullable=False),
        sa.Column("demand_ref", sa.String(), nullable=True),
        sa.Column("market_insight_ref", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("product_intelligence_competitor_evidence")
