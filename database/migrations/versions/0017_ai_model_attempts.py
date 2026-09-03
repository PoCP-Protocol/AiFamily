"""Persist Model Gateway attempts before and after provider calls.

Revision ID: 0017_ai_model_attempts
Revises: 0016_growth_onboarding
Create Date: 2026-08-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_ai_model_attempts"
down_revision: str | None = "0016_growth_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_model_attempts",
        sa.Column("attempt_id", sa.String(length=128), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("use_case", sa.String(length=128), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("route_sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(length=256), nullable=True),
        sa.Column("session_id", sa.String(length=256), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("failure_kind", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=256), nullable=True),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index(
        "ix_ai_model_attempts_request",
        "ai_model_attempts",
        ["request_id", "started_at"],
    )
    op.create_index(
        "ix_ai_model_attempts_provider_status",
        "ai_model_attempts",
        ["provider_id", "status", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_model_attempts_provider_status", table_name="ai_model_attempts")
    op.drop_index("ix_ai_model_attempts_request", table_name="ai_model_attempts")
    op.drop_table("ai_model_attempts")
