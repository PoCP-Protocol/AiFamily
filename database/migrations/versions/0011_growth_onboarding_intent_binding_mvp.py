"""Persist the tenant-scoped GrowthIntent to GrowthOnboarding binding.

Revision ID: 0011_growth_onboarding_intent_binding_mvp
Revises: 0010_experience_run_interactions
Create Date: 2026-08-30

The binding is a Journey-owned compatibility relation.  The legacy
``growth_journeys`` row remains unchanged while this table makes the intent,
onboarding, subject, and tenant/family scope queryable in one durable record.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# `alembic_version.version_num` is varchar(32) in the immutable baseline.
# Keep the revision identifier within that limit while the filename retains
# the full capability name.
revision: str = "0011_growth_onboarding_intent"
down_revision: str | None = "0010_experience_run_interactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "growth_onboarding_intent_bindings",
        sa.Column(
            "binding_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_family_binding_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("intent_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("onboarding_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("subject_person_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("binding_id"),
        sa.ForeignKeyConstraint(
            ["tenant_family_binding_id"],
            ["tenant_family_bindings.tenant_family_binding_id"],
            name="fk_growth_binding_tenant_family_binding",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.tenant_id"],
            name="fk_growth_binding_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["families.family_id"],
            name="fk_growth_binding_family",
        ),
        sa.ForeignKeyConstraint(
            ["intent_id"],
            ["growth_intents.intent_id"],
            name="fk_growth_binding_intent",
        ),
        sa.ForeignKeyConstraint(
            ["onboarding_id"],
            ["growth_journeys.journey_id"],
            name="fk_growth_binding_onboarding",
        ),
        sa.ForeignKeyConstraint(
            ["subject_person_id"],
            ["persons.person_id"],
            name="fk_growth_binding_subject_person",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "family_id",
            "intent_id",
            name="uq_growth_binding_tenant_family_intent",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "family_id",
            "onboarding_id",
            name="uq_growth_binding_tenant_family_onboarding",
        ),
    )
    op.create_index(
        "ix_growth_onboarding_intent_bindings_scope",
        "growth_onboarding_intent_bindings",
        ["tenant_id", "family_id", "subject_person_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_growth_onboarding_intent_bindings_scope",
        table_name="growth_onboarding_intent_bindings",
    )
    op.drop_table("growth_onboarding_intent_bindings")
