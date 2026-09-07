"""SQLAlchemy ORM models for `auth_identity`.

**These map onto tables the legacy baseline already created**
(`database/baseline/0015_identity_sessions.sql`,
`0016_otp_challenges.sql`, `0018_account_family_membership.sql`,
`0019_account_scoped_session.sql`) — this domain does not own a new
migration, it is the first real application-layer writer for a schema that
has existed since the baseline replay but had zero producers anywhere in
`backend/` until now (`grep -rln "INSERT INTO identity_sessions" backend/
database/` returns only the baseline's own one-time backfill). `MIGRATION_MANIFEST.yaml`
-> `auth_identity`'s own evidence line names these four tables explicitly as
the source repository's real Postgres schema; disposition is `MIGRATE`, not
`REIMPLEMENT` — the schema is not this slice's to reinvent.

Column names mirror the SQL exactly, same convention `domains/membership` and
`domains/family_need` already use for baselined tables. Two columns matter
for why this domain's dev/test convention (`external_ref` = `"<account>:
<family>"`, no real `families`/`persons` row ever minted) still fits a schema
built around real UUID `person_id`/`family_id`:

* `identity_sessions.person_id` / `.family_id` were made nullable by 0019
  precisely to support "account-scoped (no family chosen yet)" sessions —
  this domain's session always leaves them `NULL` and carries the family
  scope in the pre-existing `account_id varchar(128)` column instead, exactly
  the shape `dev_auth.py`'s convention already used.
* `accounts.external_ref` is the caller-supplied identifier
  (`Account.external_ref` in `domain/entities.py`) — unique, nullable only
  for "internally issued" accounts this domain does not create.

`token_hash` stores `sha256(token)`, never the plaintext bearer value — the
plaintext exists only in the HTTP response body once, at issuance, matching
`0015_identity_sessions.sql`'s own comment ("服务端不透明 Bearer 令牌(存
sha256,不存明文)"). `dev_auth.py`'s process-local dict stored the plaintext
token as its own dict key, which was acceptable only because the dict was
never persisted; a real table must not repeat that.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import TypeDecorator

Base = declarative_base()


class _PortableUuid(TypeDecorator):
    """`UUID` on Postgres, `String` everywhere else (SQLite).

    Same widened-typing convention `domains/membership` and `domains/family_need`
    use so one model class runs against both the real baselined Postgres
    schema and the in-memory SQLite fast test path.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=False))
        return dialect.type_descriptor(String(36))


class AccountRow(Base):
    """Maps onto the baseline's `accounts` (0018)."""

    __tablename__ = "accounts"

    account_id = Column(_PortableUuid(), primary_key=True)
    external_ref = Column(String, nullable=True, unique=True)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class IdentitySessionRow(Base):
    """Maps onto the baseline's `identity_sessions` (0015, altered by 0019
    and by this domain's own `0071_identity_sessions_family_scope_ref`).

    `person_id` / `family_id` (the real UUID FKs) stay `NULL` for every
    session this domain issues today — see module docstring.
    `family_scope_ref` (added by 0071) carries the opaque family-scope string
    dev/test's convention uses instead. `token_hash` is the sha256 of the
    opaque bearer token; the plaintext is never written to this table.
    """

    __tablename__ = "identity_sessions"

    session_id = Column(_PortableUuid(), primary_key=True)
    token_hash = Column(String(128), nullable=False, unique=True)
    person_id = Column(_PortableUuid(), nullable=True)
    family_id = Column(_PortableUuid(), nullable=True)
    account_id = Column(String(128), nullable=True)
    account_ref = Column(_PortableUuid(), nullable=True)
    family_scope_ref = Column(String(128), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


class IdentityReceiptRow(Base):
    """Idempotency-key replay ledger for the two mutation endpoints
    (`/auth/account-session`, `/auth/session/revoke`). Not part of the legacy
    baseline — this is a genuinely new, additive table this domain owns
    outright (see `database/migrations/versions/0071_identity_receipts.py`),
    scoped narrowly to replay bookkeeping rather than identity state itself.
    """

    __tablename__ = "identity_receipts"

    receipt_key = Column(String(256), primary_key=True)
    token = Column(String(128), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    account_id = Column(String(128), nullable=True)
    family_id = Column(String(128), nullable=True)
    revoked = Column(Boolean, nullable=True)
