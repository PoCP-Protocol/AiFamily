"""Real SQLAlchemy repository implementing `IdentityRepositoryPort`.

Maps onto the legacy baseline's `accounts` / `identity_sessions` tables (see
`sqlalchemy_models.py`'s module docstring for why this domain does not own a
parallel schema) plus this domain's own additive `identity_receipts` table
and `identity_sessions.family_scope_ref` column
(`database/migrations/versions/0071_identity_sessions_family_scope_ref.py`).

Two translations exist because of that reuse, both load-bearing:

1. **Business identifier vs. database primary key.** `Account.account_id`
   (`domain/entities.py`) is the dev-convention business identifier
   (`"account-a"`, the segment before the colon in `external_ref`); the
   baseline's `accounts.account_id` is a real, internally-generated `uuid`
   primary key. `accounts.external_ref` is unique and always set to the full
   `external_ref` this domain receives, so every lookup goes through it — the
   internal uuid never leaks into the application layer.
2. **Plaintext token vs. `token_hash`.** `IdentitySession.session_id` (the
   domain's bearer token / lookup key) is hashed with sha256 before it is
   written to `identity_sessions.token_hash`; the plaintext is never
   persisted, matching that column's own comment in the baseline SQL.

`save_*` stage only; the caller commits once via `commit()` — same
unit-of-work convention as `SqlAlchemyMembershipRepository`.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.entities import Account, IdentitySession
from . import sqlalchemy_models as m


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _aware(dt):
    """SQLite drops tzinfo on round-trip; Postgres keeps it. Normalise to UTC
    on read so `IdentitySession.is_valid_at` always compares aware datetimes
    regardless of which engine backs the test."""

    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class SqlAlchemyIdentityRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    # -- accounts --

    async def save_account(self, account: Account) -> None:
        existing = await self._find_account_row(account.external_ref)
        row = m.AccountRow(
            account_id=existing.account_id if existing is not None else str(uuid.uuid4()),
            external_ref=account.external_ref,
            status="ACTIVE",
            created_at=account.created_at,
            updated_at=account.created_at,
        )
        await self._session.merge(row)

    async def _find_account_row(self, external_ref: str) -> m.AccountRow | None:
        result = await self._session.execute(
            select(m.AccountRow).where(m.AccountRow.external_ref == external_ref)
        )
        return result.scalars().first()

    async def find_account_by_external_ref(self, external_ref: str) -> Account | None:
        row = await self._find_account_row(external_ref)
        if row is None:
            return None
        # `Account.account_id` is the business identifier — the part of
        # `external_ref` before the colon, same convention
        # `IdentityApplicationService.create_account_session` derives it
        # with. Re-derive it here rather than storing it separately: it is a
        # pure function of `external_ref`, and storing a second copy would
        # let the two drift.
        account_id, _, _ = external_ref.partition(":")
        return Account(
            account_id=account_id or external_ref,
            external_ref=row.external_ref,
            created_at=_aware(row.created_at),
        )

    # -- sessions --

    async def save_session(self, session: IdentitySession) -> None:
        account_row = await self._find_account_row_for_business_id(session.account_id)
        await self._session.merge(
            m.IdentitySessionRow(
                session_id=session.session_id,
                token_hash=_hash_token(session.session_id),
                person_id=None,
                family_id=None,
                account_id=session.account_id,
                account_ref=account_row.account_id if account_row is not None else None,
                family_scope_ref=session.family_id,
                issued_at=session.issued_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                created_at=session.issued_at,
            )
        )

    async def _find_account_row_for_business_id(self, account_id: str) -> m.AccountRow | None:
        """Best-effort `accounts` row lookup for `account_ref` linkage.

        `session.account_id` is the business identifier
        (`Account.account_id`); `accounts.external_ref` is the full
        `external_ref` string it was derived from (which may carry a family
        segment after a colon). `create_account_session` always calls
        `save_account` before `save_session`, so a matching row exists by the
        time this runs — falling back to `None` (leaving `account_ref` unset)
        rather than raising keeps this purely a linkage nicety, never a
        blocker for the session write it accompanies.
        """

        result = await self._session.execute(
            select(m.AccountRow).where(
                (m.AccountRow.external_ref == account_id)
                | m.AccountRow.external_ref.like(f"{account_id}:%")
            )
        )
        return result.scalars().first()

    async def find_session(self, session_id: str) -> IdentitySession | None:
        result = await self._session.execute(
            select(m.IdentitySessionRow).where(
                m.IdentitySessionRow.token_hash == _hash_token(session_id)
            )
        )
        row = result.scalars().first()
        if row is None:
            return None
        return IdentitySession(
            session_id=session_id,
            account_id=row.account_id,
            family_id=row.family_scope_ref or row.account_id,
            issued_at=_aware(row.issued_at),
            expires_at=_aware(row.expires_at),
            revoked_at=_aware(row.revoked_at),
        )

    # -- idempotency receipts (this domain's own additive table) --

    async def find_receipt(self, idempotency_key: str) -> dict | None:
        result = await self._session.execute(
            select(m.IdentityReceiptRow).where(
                m.IdentityReceiptRow.receipt_key == idempotency_key
            )
        )
        row = result.scalars().first()
        if row is None:
            return None
        if row.revoked is not None:
            return {"revoked": row.revoked}
        return {
            "token": row.token,
            "expires_at": _aware(row.expires_at),
            "account_id": row.account_id,
            "family_id": row.family_id,
        }

    async def save_receipt(self, idempotency_key: str, response: dict) -> None:
        values = {
            "receipt_key": idempotency_key,
            "token": response.get("token"),
            "expires_at": response.get("expires_at"),
            "account_id": response.get("account_id"),
            "family_id": response.get("family_id"),
            "revoked": response.get("revoked"),
        }
        dialect = self._session.bind.dialect.name if self._session.bind is not None else ""
        if dialect == "postgresql":
            statement = pg_insert(m.IdentityReceiptRow).values(**values)
            statement = statement.on_conflict_do_nothing(index_elements=["receipt_key"])
            await self._session.execute(statement)
        else:
            existing = await self._session.get(m.IdentityReceiptRow, idempotency_key)
            if existing is None:
                self._session.add(m.IdentityReceiptRow(**values))


__all__ = ["SqlAlchemyIdentityRepository"]
