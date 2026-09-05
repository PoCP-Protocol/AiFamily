"""Make accepted FGCN Named Action request ids durable replay keys.

Revision ID: 0005_fgcn_assignment_idempotency
Revises: 0004_fgcn_p0_persistence
Create Date: 2026-08-30

The application boundary uses ``NamedActionRequest.request_id`` as the
durable identity of the Human Gate result. A partial unique index preserves
that invariant for concurrent writers while leaving historical NULL values
untouched.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_fgcn_assignment_idempotency"
down_revision: str | None = "0004_fgcn_p0_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_task_assignments_source_request",
        "task_assignments",
        ["source_request_id"],
        unique=True,
        postgresql_where=sa.text("source_request_id IS NOT NULL"),
        sqlite_where=sa.text("source_request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_task_assignments_source_request", table_name="task_assignments")
