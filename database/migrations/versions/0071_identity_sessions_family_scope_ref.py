"""Add `identity_sessions.family_scope_ref` and the `identity_receipts` table.

Per ADR-0011 (`governance/ADR/ADR-0011-platform-identity-versus-business-identity-boundary.md`)
§4, the 4 `/auth/*` endpoints migrate out of `backend/domains/assessment` into
`backend/domains/identity`, which becomes the first real application-layer
writer for the legacy baseline's `accounts` / `identity_sessions` tables
(`database/baseline/0015_identity_sessions.sql`, `0018_account_family_membership.sql`,
`0019_account_scoped_session.sql`) — `MIGRATION_MANIFEST.yaml`'s own evidence
line for `auth_identity` names these tables explicitly, and disposition is
`MIGRATE`, not `REIMPLEMENT`: the schema already exists and is not this
slice's to reinvent (see `sqlalchemy_models.py`'s module docstring for the
full reasoning).

Reusing that schema as-is is not quite possible, though: `identity_sessions`
carries family scope only through the real `family_id uuid` FK to `families`,
which `0019_account_scoped_session.sql` made nullable specifically to allow
"account-scoped (no family chosen yet)" sessions. `dev_auth.py`'s (and this
migration's own domain's) convention is different — a session's family scope
is an *opaque string* (`external_ref`'s `"<account>:<family>"` convention),
never a row inserted into `families`. There is no existing column that can
hold that string: `account_id varchar(128)` already carries the account half.

This migration adds exactly one nullable, additive column —
`family_scope_ref varchar(128)` — for that opaque family-scope string,
leaving every existing column and every existing row untouched. It does not
touch `person_id` / `family_id`: a caller that *does* have a real `families`
row to bind to should still use those, not this column; `family_scope_ref` is
specifically the escape hatch for the "no real Family row minted yet" case,
same posture `0070`'s widening took toward `service_cases`' non-UUID scope
refs.

`identity_receipts` is new and wholly owned by this migration: the
idempotency-key replay ledger for the two mutation endpoints
(`/auth/account-session`, `/auth/session/revoke`). It is not part of the
legacy baseline and does not collide with anything there.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0071_identity_sessions_family_scope_ref"
down_revision: str | None = "0070_service_cases_scope_refs_string"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "identity_sessions",
        sa.Column("family_scope_ref", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "idx_identity_sessions_family_scope_ref",
        "identity_sessions",
        ["family_scope_ref"],
    )

    op.create_table(
        "identity_receipts",
        sa.Column("receipt_key", sa.String(length=256), primary_key=True),
        sa.Column("token", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_id", sa.String(length=128), nullable=True),
        sa.Column("family_id", sa.String(length=128), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("identity_receipts")
    op.drop_index("idx_identity_sessions_family_scope_ref", table_name="identity_sessions")
    op.drop_column("identity_sessions", "family_scope_ref")
