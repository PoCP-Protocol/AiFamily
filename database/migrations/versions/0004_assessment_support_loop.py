"""Persist the first-value family support-card action loop.

The assessment result is useful only when a family can respond to it, choose
one bounded step, and return with a reflection. This revision owns those
three append-oriented records. They stay in the existing PostgreSQL database,
reuse the existing assessment session and platform event tables, and carry
tenant/family scope on every row so a repository query cannot accidentally
turn a family projection into a global feed.

The application still writes the business row, idempotency receipt, audit row,
and outbox row on the caller's single transaction. The tables here provide
durability; they are not a second event ledger or an AI fact store.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_assessment_support_loop"
down_revision: str | None = "0003_service_booking_additions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FEEDBACK_TABLE = "family_assessment_support_card_feedback"
SMALL_STEP_TABLE = "family_assessment_small_steps"
CHECKIN_TABLE = "family_assessment_checkins"
OPERATIONS_TABLE = "family_assessment_operations"
OPERATIONS_CONSTRAINT = "family_assessment_operations_action_name_check"

_PREVIOUS_ACTIONS = (
    "'START_ASSESSMENT', 'SAVE_ASSESSMENT_RESPONSE', 'SUBMIT_ASSESSMENT', "
    "'GENERATE_GROWTH_HYPOTHESIS', 'EXIT_ASSESSMENT'"
)
_SUPPORT_ACTIONS = (
    "'START_ASSESSMENT', 'SAVE_ASSESSMENT_RESPONSE', 'SUBMIT_ASSESSMENT', "
    "'GENERATE_GROWTH_HYPOTHESIS', 'EXIT_ASSESSMENT', "
    "'SUBMIT_SUPPORT_CARD_FEEDBACK', 'START_ASSESSMENT_SMALL_STEP', "
    "'RECORD_ASSESSMENT_CHECKIN'"
)


def upgrade() -> None:
    op.create_table(
        FEEDBACK_TABLE,
        sa.Column(
            "feedback_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_session_id", sa.Uuid(), nullable=False),
        sa.Column("actor_person_id", sa.Uuid(), nullable=False),
        sa.Column("feedback_type", sa.String(24), nullable=False),
        sa.Column("supplement_text", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(32), nullable=False, server_default="FAMILY_PRIVATE"),
        sa.Column(
            "boundary",
            sa.String(96),
            nullable=False,
            server_default="FEEDBACK_REFINES_PERSPECTIVE_NOT_FACT",
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["family_id"], ["families.family_id"]),
        sa.ForeignKeyConstraint(
            ["assessment_session_id"],
            ["family_assessment_sessions.assessment_session_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_person_id"], ["persons.person_id"]),
        sa.CheckConstraint(
            "feedback_type IN ('LIKE', 'NOT_LIKE', 'ADD_CONTEXT')",
            name="ck_assessment_support_feedback_type",
        ),
        sa.CheckConstraint(
            "feedback_type <> 'ADD_CONTEXT' OR supplement_text IS NOT NULL",
            name="ck_assessment_support_feedback_context",
        ),
        sa.CheckConstraint(
            "supplement_text IS NULL OR char_length(supplement_text) <= 1000",
            name="ck_assessment_support_feedback_text_length",
        ),
    )
    op.create_index(
        "ix_assessment_support_feedback_scope",
        FEEDBACK_TABLE,
        ["tenant_id", "family_id", "assessment_session_id", "recorded_at"],
    )

    op.create_table(
        SMALL_STEP_TABLE,
        sa.Column(
            "small_step_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_session_id", sa.Uuid(), nullable=False),
        sa.Column("actor_person_id", sa.Uuid(), nullable=False),
        sa.Column("action_ref", sa.String(64), nullable=False),
        sa.Column("action_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="STARTED"),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("available_for_checkin_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False, server_default="FAMILY_PRIVATE"),
        sa.Column(
            "boundary",
            sa.String(96),
            nullable=False,
            server_default="FAMILY_CHOSEN_ACTION_NOT_OUTCOME",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["family_id"], ["families.family_id"]),
        sa.ForeignKeyConstraint(
            ["assessment_session_id"],
            ["family_assessment_sessions.assessment_session_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["actor_person_id"], ["persons.person_id"]),
        sa.CheckConstraint("action_ref = 'TRY_TONIGHT'", name="ck_assessment_small_step_action"),
        sa.CheckConstraint(
            "status IN ('STARTED', 'COMPLETED')", name="ck_assessment_small_step_status"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "family_id",
            "assessment_session_id",
            "action_ref",
            name="uq_assessment_small_step_scope",
        ),
    )
    op.create_index(
        "ix_assessment_small_step_scope",
        SMALL_STEP_TABLE,
        ["tenant_id", "family_id", "assessment_session_id", "action_ref", "started_at"],
    )

    op.create_table(
        CHECKIN_TABLE,
        sa.Column(
            "checkin_id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_session_id", sa.Uuid(), nullable=False),
        sa.Column("small_step_id", sa.Uuid(), nullable=False),
        sa.Column("actor_person_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(32), nullable=False, server_default="FAMILY_PRIVATE"),
        sa.Column(
            "boundary",
            sa.String(96),
            nullable=False,
            server_default="FAMILY_FEEDBACK_NOT_OUTCOME_PROOF",
        ),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"]),
        sa.ForeignKeyConstraint(["family_id"], ["families.family_id"]),
        sa.ForeignKeyConstraint(
            ["assessment_session_id"],
            ["family_assessment_sessions.assessment_session_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["small_step_id"], [f"{SMALL_STEP_TABLE}.small_step_id"]),
        sa.ForeignKeyConstraint(["actor_person_id"], ["persons.person_id"]),
        sa.CheckConstraint(
            "outcome IN ('HELPED', 'NO_CHANGE', 'NOT_TRIED')",
            name="ck_assessment_checkin_outcome",
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) <= 1000",
            name="ck_assessment_checkin_note_length",
        ),
    )
    op.create_index(
        "ix_assessment_checkin_scope",
        CHECKIN_TABLE,
        ["tenant_id", "family_id", "assessment_session_id", "recorded_at"],
    )

    op.drop_constraint(OPERATIONS_CONSTRAINT, OPERATIONS_TABLE, type_="check")
    op.create_check_constraint(
        OPERATIONS_CONSTRAINT,
        OPERATIONS_TABLE,
        f"action_name IN ({_SUPPORT_ACTIONS})",
    )


def downgrade() -> None:
    op.drop_constraint(OPERATIONS_CONSTRAINT, OPERATIONS_TABLE, type_="check")
    op.create_check_constraint(
        OPERATIONS_CONSTRAINT,
        OPERATIONS_TABLE,
        f"action_name IN ({_PREVIOUS_ACTIONS})",
    )

    op.drop_index("ix_assessment_checkin_scope", table_name=CHECKIN_TABLE)
    op.drop_table(CHECKIN_TABLE)
    op.drop_index("ix_assessment_small_step_scope", table_name=SMALL_STEP_TABLE)
    op.drop_table(SMALL_STEP_TABLE)
    op.drop_index("ix_assessment_support_feedback_scope", table_name=FEEDBACK_TABLE)
    op.drop_table(FEEDBACK_TABLE)
