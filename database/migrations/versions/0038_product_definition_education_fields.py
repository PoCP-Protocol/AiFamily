"""Persist education-product design fields for ProductDefinition.

The legacy product-intelligence table predates the IPD education-product
contract.  These nullable/defaulted columns let existing definitions continue
to load while allowing the domain model to persist 21-day/90-day package
design, provenance and demand/market traceability.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_product_definition"
down_revision: str | None = "0037_ops_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("product_kind", sa.String(length=32), nullable=False, server_default="CUSTOM"),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("duration_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("zone", sa.String(length=32), nullable=False, server_default="HOMOGENEOUS"),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("primary_contradiction", sa.Text(), nullable=True),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("demand_ref", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("market_insight_refs", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("education_spec", sa.JSON(), nullable=True),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("generated_by", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("model_ref", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("prompt_use_case_version", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "product_intelligence_product_definitions",
        sa.Column("confidence", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    for column in (
        "confidence",
        "prompt_use_case_version",
        "model_ref",
        "generated_by",
        "education_spec",
        "market_insight_refs",
        "demand_ref",
        "primary_contradiction",
        "zone",
        "duration_days",
        "product_kind",
    ):
        op.drop_column("product_intelligence_product_definitions", column)
