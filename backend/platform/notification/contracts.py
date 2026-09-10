"""Small, provider-neutral contracts for the notification control plane.

This module owns no database tables and performs no external I/O.  It makes
scope, purpose, consent and idempotency explicit so callers cannot construct a
notification that silently escapes the platform governance boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid5


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    PUSH = "push"
    SMS = "sms"
    EMAIL = "email"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    RETRY = "retry"
    SUPPRESSED = "suppressed"
    DEAD_LETTER = "dead_letter"


class DeliveryDecision(StrEnum):
    ALLOW = "allow"
    SUPPRESS = "suppress"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class NotificationScope:
    tenant_id: str
    family_id: str
    subject_id: str
    purpose: str
    consent_version: str

    def __post_init__(self) -> None:
        fields = {
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "subject_id": self.subject_id,
            "purpose": self.purpose,
            "consent_version": self.consent_version,
        }
        missing = sorted(name for name, value in fields.items() if not value.strip())
        if missing:
            raise ValueError(f"notification scope missing required fields: {missing}")


@dataclass(frozen=True, slots=True)
class NotificationIntent:
    intent_id: UUID
    scope: NotificationScope
    channel: NotificationChannel
    template_key: str
    idempotency_key: str
    correlation_id: str
    body: str
    created_at: datetime
    external_effect: bool = True

    def __post_init__(self) -> None:
        if not self.template_key.strip() or not self.idempotency_key.strip():
            raise ValueError("notification template and idempotency key are required")
        if not self.correlation_id.strip() or not self.body.strip():
            raise ValueError("notification correlation and body are required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("notification created_at must be timezone-aware")
        expected = deterministic_intent_id(
            tenant_id=self.scope.tenant_id,
            family_id=self.scope.family_id,
            channel=self.channel,
            idempotency_key=self.idempotency_key,
        )
        if self.intent_id != expected:
            raise ValueError("notification intent id must match scoped idempotency identity")

    @classmethod
    def create(
        cls,
        *,
        scope: NotificationScope,
        channel: NotificationChannel,
        template_key: str,
        idempotency_key: str,
        correlation_id: str,
        body: str,
        created_at: datetime | None = None,
        external_effect: bool = True,
    ) -> NotificationIntent:
        return cls(
            intent_id=deterministic_intent_id(
                tenant_id=scope.tenant_id,
                family_id=scope.family_id,
                channel=channel,
                idempotency_key=idempotency_key,
            ),
            scope=scope,
            channel=channel,
            template_key=template_key,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            body=body,
            created_at=created_at or datetime.now(UTC),
            external_effect=external_effect,
        )


@dataclass(frozen=True, slots=True)
class NotificationPolicy:
    consent_granted: bool
    revoked: bool = False
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None

    def decide(self, *, channel: NotificationChannel, at: datetime) -> DeliveryDecision:
        if self.revoked or not self.consent_granted:
            return DeliveryDecision.REJECT
        if channel is NotificationChannel.IN_APP:
            return DeliveryDecision.ALLOW
        if self.quiet_hours_start is None or self.quiet_hours_end is None:
            return DeliveryDecision.ALLOW
        current = at.astimezone(UTC).time()
        in_quiet = (
            self.quiet_hours_start <= current < self.quiet_hours_end
            if self.quiet_hours_start <= self.quiet_hours_end
            else current >= self.quiet_hours_start or current < self.quiet_hours_end
        )
        return DeliveryDecision.SUPPRESS if in_quiet else DeliveryDecision.ALLOW


class NotificationChannelPort(Protocol):
    async def deliver(self, intent: NotificationIntent) -> DeliveryReceipt: ...


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    intent_id: UUID
    status: DeliveryStatus
    external_effect: bool
    provider_reference: str | None = None


def deterministic_intent_id(
    *, tenant_id: str, family_id: str, channel: NotificationChannel, idempotency_key: str
) -> UUID:
    return uuid5(
        UUID("3fcb1ad0-27c2-4f74-9619-8df8dca555aa"),
        ":".join((tenant_id, family_id, channel.value, idempotency_key)),
    )


__all__ = [
    "DeliveryDecision",
    "DeliveryReceipt",
    "DeliveryStatus",
    "NotificationChannel",
    "NotificationChannelPort",
    "NotificationIntent",
    "NotificationPolicy",
    "NotificationScope",
    "deterministic_intent_id",
]
