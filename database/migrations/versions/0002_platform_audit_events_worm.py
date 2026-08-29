"""platform_audit_events — the durable, append-only table R6 requires

Revision ID: 0002_platform_audit_events_worm
Revises: 0001_legacy_schema_baseline
Create Date: 2026-08-29

Creates `platform_audit_events` (the table behind
`backend/platform/audit/store.py`) plus a trigger that makes it append-only at
the database level.

Why a new table and not a widening of legacy ``audit_logs``
-----------------------------------------------------------
`database/baseline/0002_platform_foundation.sql` already creates `audit_logs`,
and revision 0001 replays that file verbatim. `audit_logs` cannot hold an
`AuditEvent`: it has no `before`/`after` columns (R6 names both explicitly) and
none of 《未成年人网络保护条例》第36条's four read-access elements
(`subject_person_id` / `accessed_fields` / `access_purpose` / `approval_ref`).
Altering it would either mean editing a baseline whose whole value is being
checksum-identical to the legacy SQL (asserted by
`database/tests/test_baseline_linearisation.py`), or bolting an `ALTER TABLE`
onto a legacy shape whose `result`/`metadata` columns have no counterpart in
the value object. `audit_logs` is left untouched as legacy history; new writes
go here.

Why one table for both action kinds
-----------------------------------
`action_kind` is the discriminator, mirroring the single-type decision in
`backend/platform/audit/models.py`. Two tables would let a read access be
recorded in the mutation table with the 第36条 columns simply absent — the
exact degradation the discriminator exists to prevent. The CHECK constraints
below are what make the discriminator load-bearing *in the database* rather
than only in Python: a row written by any client, ORM or not, still cannot
claim to be a READ while omitting the subject, the purpose, or (for a minor)
the approval.

Append-only (WORM)
------------------
`platform_audit_events_worm()` is a `BEFORE UPDATE OR DELETE` trigger that
raises. Reasons for a trigger rather than a permission grant:

* A `REVOKE UPDATE, DELETE` on a role only binds that role. The application
  connects as the table owner in every deployment shape this project currently
  has, and an owner's own privileges are not what stops it.
* The trigger fires for the owner too. It does not fire for a superuser who
  first runs `ALTER TABLE ... DISABLE TRIGGER`, and nothing at this layer can:
  defending the trail against the database administrator requires immutability
  outside the database (object-lock WAL archival, or an external hash-chain
  anchor). That is not built, and this migration does not pretend otherwise.

`TRUNCATE` is covered by a separate statement-level trigger — a `BEFORE DELETE`
row trigger never fires for `TRUNCATE`, which would otherwise be a one-command
erasure of the whole trail.

Retention note: there is deliberately no expiry or archival mechanism here.
COMPLIANCE_HARD_CONSTRAINTS.md §11 item 4 tracks retention binding as an open
design item; a `DELETE`-based retention job would need this trigger relaxed,
which is a decision that belongs in an ADR, not in the table that the decision
would weaken.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_platform_audit_events_worm"
down_revision: str | None = "0001_legacy_schema_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "platform_audit_events"
WORM_FUNCTION = "platform_audit_events_worm"

# Mirrors AuditEvent.__post_init__. Stated in SQL as well as Python because a
# guarantee that only exists in the application is a guarantee that ends at the
# first psql session.
_READ_SHAPE_CHECK = """
    (action_kind = 'read' AND before IS NULL AND after IS NULL
        AND subject_person_id IS NOT NULL AND accessed_fields IS NOT NULL
        AND access_purpose IS NOT NULL)
    OR
    (action_kind = 'mutation' AND subject_person_id IS NULL
        AND accessed_fields IS NULL AND access_purpose IS NULL
        AND approval_ref IS NULL)
"""

# 第36条: staff access to a minor's information must be approved beforehand.
_MINOR_APPROVAL_CHECK = "NOT (subject_is_minor AND approval_ref IS NULL)"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # --- R6 required elements ---
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action_kind", sa.String(16), nullable=False),
        # --- MUTATION-only ---
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        # --- READ-only (第36条) ---
        sa.Column("subject_person_id", sa.String(128), nullable=True),
        sa.Column("subject_is_minor", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("accessed_fields", sa.JSON(), nullable=True),
        sa.Column("access_purpose", sa.String(64), nullable=True),
        sa.Column("approval_ref", sa.String(128), nullable=True),
        sa.CheckConstraint(
            "action_kind IN ('mutation', 'read')", name="ck_platform_audit_events_action_kind"
        ),
        sa.CheckConstraint(_READ_SHAPE_CHECK, name="ck_platform_audit_events_kind_shape"),
        sa.CheckConstraint(_MINOR_APPROVAL_CHECK, name="ck_platform_audit_events_minor_approval"),
    )
    # tenant + time: the 第37条 annual audit export, and every "what happened in
    # this tenant" question. correlation_id: tracing one request's writes.
    # subject_person_id (partial, reads only): the 第36条 subject-access report,
    # which is the only query that must stay fast as mutations dominate volume.
    op.create_index(
        "ix_platform_audit_events_tenant_time", TABLE_NAME, ["tenant_id", "occurred_at"]
    )
    op.create_index("ix_platform_audit_events_correlation", TABLE_NAME, ["correlation_id"])
    op.create_index(
        "ix_platform_audit_events_subject",
        TABLE_NAME,
        ["subject_person_id", "occurred_at"],
        postgresql_where=sa.text("action_kind = 'read'"),
    )

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {WORM_FUNCTION}() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                '{TABLE_NAME} is append-only (WORM): % is not permitted', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"CREATE TRIGGER {TABLE_NAME}_no_update_delete "
        f"BEFORE UPDATE OR DELETE ON {TABLE_NAME} "
        f"FOR EACH ROW EXECUTE FUNCTION {WORM_FUNCTION}()"
    )
    # A BEFORE DELETE row trigger does not fire for TRUNCATE; without this,
    # one command erases the entire trail.
    op.execute(
        f"CREATE TRIGGER {TABLE_NAME}_no_truncate "
        f"BEFORE TRUNCATE ON {TABLE_NAME} "
        f"FOR EACH STATEMENT EXECUTE FUNCTION {WORM_FUNCTION}()"
    )


def downgrade() -> None:
    """Drop the table and its trigger.

    Reversible on purpose, unlike revision 0001: this revision created its own
    objects rather than replaying legacy SQL, so the inverse is exact. Note the
    obvious asymmetry — the trigger prevents deleting *rows*, not dropping the
    *table*. DDL-level protection of an audit table against its own owner is
    not something a migration can grant itself; that is the storage-level gap
    documented in the module docstring.
    """
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE_NAME}_no_truncate ON {TABLE_NAME}")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE_NAME}_no_update_delete ON {TABLE_NAME}")
    op.execute(f"DROP FUNCTION IF EXISTS {WORM_FUNCTION}()")
    op.drop_index("ix_platform_audit_events_subject", table_name=TABLE_NAME)
    op.drop_index("ix_platform_audit_events_correlation", table_name=TABLE_NAME)
    op.drop_index("ix_platform_audit_events_tenant_time", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
