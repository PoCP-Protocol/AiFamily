"""family_service_providers: add qualification_type/qualification_expires_at.

FGCN's provider-admission adapters (`backend/domains/service/fgcn/admission.py`'s
`ProviderAdmissionSnapshot`, and the durable
`SqlAlchemyProviderAdmissionQuery`) currently have no way to reject a provider
whose qualification has lapsed — `family_service_providers` only records
`qualification_ref`/`qualification_status`, neither of which is a date. This
adds two real columns (not JSONB `attributes`, because expiry needs to be
queried/compared, not just stored) so a future admission check can fail
closed on an expired credential rather than trusting a status string that
was never automatically revisited.

This migration only adds columns; it does not change any admission adapter's
behaviour, and does not swap which adapter the composition root uses — see
`governance/DOMAIN_REGISTRY.yaml`'s `family_need_orchestration` known_gaps
for why the sync in-memory path and this async Postgres-backed adapter are
not drop-in interchangeable.

Revision ID: 0066_fgcn_provider_qualification_fields
Revises: 0065_experience_feedback_resolution
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066_fgcn_provider_qualification_fields"
down_revision: str | None = "0065_experience_feedback_resolution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "family_service_providers",
        sa.Column("qualification_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "family_service_providers",
        sa.Column("qualification_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("family_service_providers", "qualification_expires_at")
    op.drop_column("family_service_providers", "qualification_type")
