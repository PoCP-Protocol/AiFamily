"""Persist metadata-only multimodal benchmark reports."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_ai_benchmark_report_archive"
down_revision: str | None = "0033_ai_release_deployment_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_benchmark_reports",
        sa.Column("archive_id", sa.String(length=64), nullable=False),
        sa.Column("report_ref", sa.Text(), nullable=False),
        sa.Column("case_version", sa.String(length=128), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("archive_id"),
        sa.UniqueConstraint("report_ref", name="uq_ai_benchmark_reports_report_ref"),
    )
    op.create_index(
        "ix_ai_benchmark_reports_dataset_version",
        "ai_benchmark_reports",
        ["dataset_fingerprint", "case_version", "archived_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_benchmark_reports_dataset_version",
        table_name="ai_benchmark_reports",
    )
    op.drop_table("ai_benchmark_reports")
