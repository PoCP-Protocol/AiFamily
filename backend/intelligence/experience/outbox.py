"""Caller-owned transactional writer for ``experience_outbox_messages``.

This is the single M1 outbox adapter.  It intentionally owns neither a
session factory nor a commit: the business write, ``AuditRecorder.flush()``,
this append, and the caller's receipt must all share one ``AsyncSession``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ExperienceOutboxError(ValueError):
    """Base error for the canonical experience outbox adapter."""


class ExperienceOutboxConflictError(ExperienceOutboxError):
    """A tenant idempotency key was reused for a different event."""


@dataclass(frozen=True, slots=True)
class ExperienceOutboxMessage:
    """Content-free, scoped event envelope persisted by revision 0007."""

    message_id: str
    event_type: str
    tenant_id: str
    region_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    purpose: str
    consent_version: str
    idempotency_key: str
    schema_version: str
    payload: dict[str, Any]
    enqueued_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "message_id",
            "event_type",
            "tenant_id",
            "region_id",
            "family_id",
            "purpose",
            "consent_version",
            "idempotency_key",
            "schema_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ExperienceOutboxError(f"{name} is required")
        if not self.subject_ids or any(not value.strip() for value in self.subject_ids):
            raise ExperienceOutboxError("subject_ids are required")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ExperienceOutboxError("subject_ids must be unique")
        if self.enqueued_at.tzinfo is None:
            raise ExperienceOutboxError("enqueued_at must be timezone-aware")

    @classmethod
    def now(cls, **values: Any) -> ExperienceOutboxMessage:
        return cls(enqueued_at=datetime.now(UTC), **values)


class SqlAlchemyExperienceOutboxWriter:
    """Append/replay adapter using the caller-owned transaction only."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, message: ExperienceOutboxMessage) -> ExperienceOutboxMessage:
        """Stage ``message`` without committing and return its exact replay.

        ``ON CONFLICT`` is scoped by the schema's ``tenant_id`` plus client
        idempotency key.  A replay must be byte-for-byte equivalent after JSON
        canonicalisation; a changed request fails closed rather than silently
        returning an unrelated prior event.
        """

        inserted = await self._session.execute(
            text(
                """
                INSERT INTO experience_outbox_messages (
                    message_id, event_type, tenant_id, region_id, family_id,
                    subject_ids, purpose, consent_version, idempotency_key,
                    schema_version, payload, enqueued_at, published_at
                ) VALUES (
                    :message_id, :event_type, :tenant_id, :region_id, :family_id,
                    CAST(:subject_ids AS jsonb), :purpose, :consent_version,
                    :idempotency_key, :schema_version, CAST(:payload AS jsonb),
                    :enqueued_at, NULL
                ) ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING message_id
                """
            ),
            self._params(message),
        )
        if inserted.scalar_one_or_none() is not None:
            return message

        existing = await self._session.execute(
            text(
                """
                SELECT message_id, event_type, tenant_id, region_id, family_id,
                       subject_ids, purpose, consent_version, idempotency_key,
                       schema_version, payload, enqueued_at
                FROM experience_outbox_messages
                WHERE tenant_id = :tenant_id AND idempotency_key = :idempotency_key
                """
            ),
            {"tenant_id": message.tenant_id, "idempotency_key": message.idempotency_key},
        )
        row = existing.mappings().one_or_none()
        if row is None:
            raise ExperienceOutboxError("outbox idempotency replay unavailable")
        replay = ExperienceOutboxMessage(
            message_id=row["message_id"],
            event_type=row["event_type"],
            tenant_id=row["tenant_id"],
            region_id=row["region_id"],
            family_id=row["family_id"],
            subject_ids=tuple(row["subject_ids"]),
            purpose=row["purpose"],
            consent_version=row["consent_version"],
            idempotency_key=row["idempotency_key"],
            schema_version=row["schema_version"],
            payload=row["payload"],
            enqueued_at=row["enqueued_at"],
        )
        if not self._same_event(replay, message):
            raise ExperienceOutboxConflictError("outbox idempotency replay mismatch")
        return replay

    @staticmethod
    def _params(message: ExperienceOutboxMessage) -> dict[str, Any]:
        return {
            "message_id": message.message_id,
            "event_type": message.event_type,
            "tenant_id": message.tenant_id,
            "region_id": message.region_id,
            "family_id": message.family_id,
            "subject_ids": json.dumps(message.subject_ids),
            "purpose": message.purpose,
            "consent_version": message.consent_version,
            "idempotency_key": message.idempotency_key,
            "schema_version": message.schema_version,
            "payload": json.dumps(message.payload, sort_keys=True, separators=(",", ":")),
            "enqueued_at": message.enqueued_at,
        }

    @staticmethod
    def _same_event(left: ExperienceOutboxMessage, right: ExperienceOutboxMessage) -> bool:
        return (
            left.event_type,
            left.tenant_id,
            left.region_id,
            left.family_id,
            left.subject_ids,
            left.purpose,
            left.consent_version,
            left.idempotency_key,
            left.schema_version,
            json.dumps(left.payload, sort_keys=True, separators=(",", ":")),
        ) == (
            right.event_type,
            right.tenant_id,
            right.region_id,
            right.family_id,
            right.subject_ids,
            right.purpose,
            right.consent_version,
            right.idempotency_key,
            right.schema_version,
            json.dumps(right.payload, sort_keys=True, separators=(",", ":")),
        )


__all__ = [
    "ExperienceOutboxConflictError",
    "ExperienceOutboxError",
    "ExperienceOutboxMessage",
    "SqlAlchemyExperienceOutboxWriter",
]
