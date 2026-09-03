"""Persist metadata-only benchmark evaluation slices."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_ai_benchmark_report_slices"
down_revision: str | None = "0034_ai_benchmark_report_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_benchmark_report_slices",
        sa.Column("slice_id", sa.String(length=64), nullable=False),
        sa.Column("report_ref", sa.Text(), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=128), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("slice_report_ref", sa.Text(), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("slice_id"),
        sa.UniqueConstraint(
            "report_ref",
            "dimension",
            "value",
            name="uq_ai_benchmark_report_slices_identity",
        ),
    )
    op.create_index(
        "ix_ai_benchmark_report_slices_dataset_dimension",
        "ai_benchmark_report_slices",
        ["dataset_fingerprint", "dimension", "value"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_benchmark_report_slices_dataset_dimension",
        table_name="ai_benchmark_report_slices",
    )
    op.drop_table("ai_benchmark_report_slices")
