"""Add active ReleaseSet projection and pre-I/O invocation fence claims."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_ai_release_projection_invocation_fence"
down_revision: str | None = "0049_ai_release_set_signed_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_model_attempts",
        sa.Column("deployment_sequence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_model_attempts",
        sa.Column("runtime_config_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ai_model_attempts",
        sa.Column("control_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "ai_model_budget_reservations",
        sa.Column("deployment_sequence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_model_budget_reservations",
        sa.Column("control_id", sa.String(length=128), nullable=True),
    )
    op.create_table(
        "ai_family_experience_active_release_bindings",
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("release_set_id", sa.String(length=64), nullable=False),
        sa.Column("deployment_receipt_id", sa.String(length=64), nullable=False),
        sa.Column("deployment_sequence", sa.Integer(), nullable=False),
        sa.Column("runtime_config_digest", sa.String(length=64), nullable=False),
        sa.Column("control_id", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "deployment_sequence > 0",
            name="ck_ai_active_release_binding_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["release_set_id"],
            ["ai_family_experience_release_sets.release_set_id"],
        ),
        sa.ForeignKeyConstraint(
            ["deployment_receipt_id"],
            ["ai_family_experience_release_set_deployments.receipt_id"],
        ),
        sa.ForeignKeyConstraint(
            ["control_id"],
            ["ai_family_experience_release_set_controls.control_id"],
        ),
        sa.PrimaryKeyConstraint("environment", "use_case", "data_class"),
    )
    op.create_table(
        "ai_model_invocation_fence_claims",
        sa.Column("claim_id", sa.String(length=64), nullable=False),
        sa.Column("claim_key", sa.String(length=64), nullable=False),
        sa.Column("request_ref", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("use_case", sa.String(length=256), nullable=False),
        sa.Column("data_class", sa.String(length=64), nullable=False),
        sa.Column("release_set_id", sa.String(length=64), nullable=False),
        sa.Column("deployment_receipt_id", sa.String(length=64), nullable=False),
        sa.Column("deployment_sequence", sa.Integer(), nullable=False),
        sa.Column("runtime_config_digest", sa.String(length=64), nullable=False),
        sa.Column("control_id", sa.String(length=128), nullable=False),
        sa.Column("provider_id", sa.String(length=128), nullable=False),
        sa.Column("bundle_id", sa.String(length=64), nullable=False),
        sa.Column("route_sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "deployment_sequence > 0 AND route_sequence >= 0",
            name="ck_ai_invocation_fence_claim_sequences",
        ),
        sa.ForeignKeyConstraint(
            ["release_set_id"],
            ["ai_family_experience_release_sets.release_set_id"],
        ),
        sa.ForeignKeyConstraint(
            ["deployment_receipt_id"],
            ["ai_family_experience_release_set_deployments.receipt_id"],
        ),
        sa.ForeignKeyConstraint(
            ["control_id"],
            ["ai_family_experience_release_set_controls.control_id"],
        ),
        sa.PrimaryKeyConstraint("claim_id"),
        sa.UniqueConstraint("claim_key", name="uq_ai_invocation_fence_claim_key"),
    )
    op.create_index(
        "ix_ai_model_invocation_fence_request_ref",
        "ai_model_invocation_fence_claims",
        ["request_ref"],
    )
    with op.batch_alter_table("ai_model_budget_reservations") as batch:
        batch.drop_constraint(
            "ck_ai_model_budget_reservation_status",
            type_="check",
        )
        batch.create_check_constraint(
            "ck_ai_model_budget_reservation_status",
            "status IN ('RESERVED', 'SETTLED', 'CONSUMED_UNCERTAIN', 'RELEASED')",
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_model_budget_reservations") as batch:
        batch.drop_constraint(
            "ck_ai_model_budget_reservation_status",
            type_="check",
        )
        batch.create_check_constraint(
            "ck_ai_model_budget_reservation_status",
            "status IN ('RESERVED', 'SETTLED', 'CONSUMED_UNCERTAIN')",
        )
    op.drop_index(
        "ix_ai_model_invocation_fence_request_ref",
        table_name="ai_model_invocation_fence_claims",
    )
    op.drop_table("ai_model_invocation_fence_claims")
    op.drop_table("ai_family_experience_active_release_bindings")
    op.drop_column("ai_model_budget_reservations", "control_id")
    op.drop_column("ai_model_budget_reservations", "deployment_sequence")
    op.drop_column("ai_model_attempts", "control_id")
    op.drop_column("ai_model_attempts", "runtime_config_digest")
    op.drop_column("ai_model_attempts", "deployment_sequence")
