"""Application-neutral value objects for the canonical integration outbox."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

OUTBOX_EVENT_NAMESPACE = UUID("62d44d1e-6208-4c8d-af43-933517f14bce")


class OutboxConflictError(RuntimeError):
    """A deterministic event id already exists with different content."""


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """One immutable event staged after a business fact is accepted."""

    event_id: UUID
    tenant_id: str
    family_id: str
    aggregate_type: str
    aggregate_id: str
    event_name: str
    event_version: int
    idempotency_key: str
    request_hash: str
    correlation_id: str
    payload: dict[str, Any]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        required = {
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "event_name": self.event_name,
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "correlation_id": self.correlation_id,
        }
        missing = sorted(name for name, value in required.items() if not value.strip())
        if missing:
            raise ValueError(f"OutboxEvent is missing required field(s): {missing}")
        if self.event_version < 1:
            raise ValueError("OutboxEvent.event_version must be positive")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("OutboxEvent.occurred_at must be timezone-aware")
        expected = deterministic_event_id(
            tenant_id=self.tenant_id,
            family_id=self.family_id,
            event_name=self.event_name,
            idempotency_key=self.idempotency_key,
        )
        if self.event_id != expected:
            raise ValueError(
                "OutboxEvent.event_id must match its tenant-scoped idempotency identity"
            )
        try:
            normalized = json.loads(canonical_json(self.payload))
        except (TypeError, ValueError) as error:
            raise ValueError("OutboxEvent.payload must be JSON-serializable") from error
        object.__setattr__(self, "payload", normalized)

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        family_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_name: str,
        event_version: int,
        idempotency_key: str,
        request_hash: str,
        correlation_id: str,
        payload: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> OutboxEvent:
        return cls(
            event_id=deterministic_event_id(
                tenant_id=tenant_id,
                family_id=family_id,
                event_name=event_name,
                idempotency_key=idempotency_key,
            ),
            tenant_id=tenant_id,
            family_id=family_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_name=event_name,
            event_version=event_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            correlation_id=correlation_id,
            payload=payload,
            occurred_at=occurred_at or datetime.now(UTC),
        )

    def storage_payload(self) -> dict[str, Any]:
        """Return the canonical scope/idempotency envelope stored in ``payload``."""
        return {
            "platform": {
                "tenant_id": self.tenant_id,
                "family_id": self.family_id,
                "idempotency_key": self.idempotency_key,
                "request_hash": self.request_hash,
            },
            "event": self.payload,
        }


def deterministic_event_id(
    *, tenant_id: str, family_id: str, event_name: str, idempotency_key: str
) -> UUID:
    identity = ":".join((tenant_id, family_id, event_name, idempotency_key))
    return uuid5(OUTBOX_EVENT_NAMESPACE, identity)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


__all__ = [
    "OUTBOX_EVENT_NAMESPACE",
    "OutboxConflictError",
    "OutboxEvent",
    "canonical_json",
    "deterministic_event_id",
]
