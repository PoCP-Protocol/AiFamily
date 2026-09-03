"""Durable GrowthIntent to Journey binding for the onboarding slice.

Revision ID: 0016_growth_onboarding
Revises: 0015_ai_achievement_projections

``growth_journeys`` is a historical shared table and cannot be altered in the
legacy baseline.  This additive table is the authoritative, queryable link
between a confirmed intent and its onboarding journey.  The binding carries
the exact tenant-family binding used by the command, while the application
checks that that binding is active at write time.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_growth_onboarding"
down_revision: str | None = "0015_ai_achievement_projections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "growth_onboarding_intent_bindings"


def upgrade() -> None:
    # Composite foreign keys make a row from family A impossible to bind to a
    # journey or intent from family B.  The referenced primary keys remain the
    # historical single-column identifiers; these constraints are additive.
    op.create_unique_constraint(
        "uq_growth_intents_family_intent",
        "growth_intents",
        ["family_id", "intent_id"],
    )
    op.create_unique_constraint(
        "uq_growth_journeys_family_journey",
        "growth_journeys",
        ["family_id", "journey_id"],
    )
    op.create_unique_constraint(
        "uq_tenant_family_binding_identity",
        "tenant_family_bindings",
        ["tenant_family_binding_id", "tenant_id", "family_id"],
    )
    op.create_table(
        TABLE_NAME,
        sa.Column(
            "binding_id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_family_binding_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("intent_id", sa.UUID(), nullable=False),
        sa.Column("onboarding_id", sa.UUID(), nullable=False),
        sa.Column("subject_person_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("binding_id"),
        sa.ForeignKeyConstraint(
            ["tenant_family_binding_id", "tenant_id", "family_id"],
            [
                "tenant_family_bindings.tenant_family_binding_id",
                "tenant_family_bindings.tenant_id",
                "tenant_family_bindings.family_id",
            ],
            name="fk_growth_binding_tenant_family_binding",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "intent_id"],
            ["growth_intents.family_id", "growth_intents.intent_id"],
            name="fk_growth_binding_intent",
        ),
        sa.ForeignKeyConstraint(
            ["family_id", "onboarding_id"],
            ["growth_journeys.family_id", "growth_journeys.journey_id"],
            name="fk_growth_binding_onboarding",
        ),
        sa.ForeignKeyConstraint(
            ["subject_person_id"],
            ["persons.person_id"],
            name="fk_growth_binding_subject",
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
        "ix_growth_binding_intent_lookup",
        TABLE_NAME,
        ["tenant_id", "family_id", "intent_id"],
    )
    op.create_index(
        "ix_growth_binding_onboarding_lookup",
        TABLE_NAME,
        ["tenant_id", "family_id", "onboarding_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_growth_binding_onboarding_lookup", table_name=TABLE_NAME)
    op.drop_index("ix_growth_binding_intent_lookup", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
    op.drop_constraint(
        "uq_tenant_family_binding_identity", "tenant_family_bindings", type_="unique"
    )
    op.drop_constraint("uq_growth_journeys_family_journey", "growth_journeys", type_="unique")
    op.drop_constraint("uq_growth_intents_family_intent", "growth_intents", type_="unique")
