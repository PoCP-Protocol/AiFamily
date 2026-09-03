"""PostgreSQL-backed tenant-scoped idempotency reservations.

The adapter writes the existing canonical ``idempotency_keys`` table from
``database/baseline/0002_platform_foundation.sql``.  It deliberately accepts a
caller-owned ``AsyncSession`` and never commits, so the reservation can share
one transaction with the business fact, audit event, and outbox event.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.platform.idempotency.keys import IdempotencyKey

IDEMPOTENCY_METADATA = MetaData()
IDEMPOTENCY_KEYS_TABLE = Table(
    "idempotency_keys",
    IDEMPOTENCY_METADATA,
    Column("idempotency_key", String(128), primary_key=True),
    Column("action_name", String(128), nullable=False),
    Column("request_hash", String(128), nullable=False),
    Column("response_code", Integer),
    Column("response_body", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("expires_at", DateTime(timezone=True)),
)


class IdempotencyConflictError(RuntimeError):
    """The same tenant-scoped key was reused for a different operation."""


@dataclass(frozen=True, slots=True)
class SqlAlchemyIdempotencyStore:
    """Reserve tenant-scoped keys in the canonical platform table."""

    @staticmethod
    def storage_key(key: IdempotencyKey) -> str:
        digest = hashlib.sha256(key.scoped_value.encode("utf-8")).hexdigest()
        return f"tenant-v1:{digest}"

    async def reserve(
        self,
        session: AsyncSession,
        *,
        key: IdempotencyKey,
        action_name: str,
        request_hash: str,
    ) -> bool:
        """Return ``True`` for first use and ``False`` for an exact replay.

        A changed action or request hash is a conflict rather than a replay.
        The caller owns commit/rollback of ``session``.
        """
        if not action_name:
            raise ValueError("action_name must not be empty")
        if not request_hash:
            raise ValueError("request_hash must not be empty")

        storage_key = self.storage_key(key)
        statement = (
            insert(IDEMPOTENCY_KEYS_TABLE)
            .values(
                idempotency_key=storage_key,
                action_name=action_name,
                request_hash=request_hash,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(IDEMPOTENCY_KEYS_TABLE.c.idempotency_key)
        )
        inserted = (await session.execute(statement)).scalar_one_or_none()
        if inserted is not None:
            return True

        existing = (
            await session.execute(
                select(
                    IDEMPOTENCY_KEYS_TABLE.c.action_name,
                    IDEMPOTENCY_KEYS_TABLE.c.request_hash,
                ).where(IDEMPOTENCY_KEYS_TABLE.c.idempotency_key == storage_key)
            )
        ).one()
        if existing.action_name != action_name or existing.request_hash != request_hash:
            raise IdempotencyConflictError("idempotency_key_reused_with_different_request")
        return False
