"""Canonical-outbox to notification-intent orchestration boundary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from backend.platform.notification.contracts import (
    DeliveryDecision,
    NotificationChannel,
    NotificationIntent,
    NotificationPolicy,
    NotificationScope,
)
from backend.platform.notification.persistence import (
    NotificationAttemptRow,
    SqlAlchemyNotificationStore,
)
from backend.platform.outbox import OutboxEvent


class NotificationOrchestrator:
    """Translate one committed domain event into one governed notification."""

    def __init__(
        self,
        store: SqlAlchemyNotificationStore,
        policy_loader: Callable[[str, str, str, str], NotificationPolicy],
    ) -> None:
        self._store = store
        self._policy_loader = policy_loader

    async def enqueue(
        self,
        event: OutboxEvent,
        *,
        subject_id: str,
        purpose: str,
        consent_version: str,
        channel: NotificationChannel,
        template_key: str,
        body: str,
        now: datetime,
    ) -> NotificationAttemptRow:
        if event.tenant_id.strip() == "" or event.family_id.strip() == "":
            raise ValueError("outbox event scope is required")
        intent = NotificationIntent.create(
            scope=NotificationScope(
                event.tenant_id,
                event.family_id,
                subject_id,
                purpose,
                consent_version,
            ),
            channel=channel,
            template_key=template_key,
            idempotency_key=f"{event.event_id}:{channel.value}",
            correlation_id=event.correlation_id,
            body=body,
            created_at=now,
            external_effect=channel is not NotificationChannel.IN_APP,
        )
        await self._store.create_intent(intent)
        attempt = await self._store.enqueue_attempt(intent_id=intent.intent_id, now=now)
        decision = self._policy_loader(
            event.tenant_id, event.family_id, subject_id, purpose
        ).decide(channel=channel, at=now)
        if attempt.status == "pending":
            if decision is DeliveryDecision.REJECT:
                await self._store.suppress(attempt, now=now, reason="consent_denied")
            elif decision is DeliveryDecision.SUPPRESS:
                await self._store.defer(
                    attempt,
                    until=_next_quiet_hours_end(
                        now,
                        self._policy_loader(event.tenant_id, event.family_id, subject_id, purpose),
                    ),
                    reason="quiet_hours",
                )
        return attempt


def _next_quiet_hours_end(now: datetime, policy: NotificationPolicy) -> datetime:
    """Return the next UTC instant at which a quiet window ends."""
    if policy.quiet_hours_end is None:
        raise ValueError("quiet-hours end is required for deferral")
    current = now.astimezone(now.tzinfo)
    candidate = current.replace(
        hour=policy.quiet_hours_end.hour,
        minute=policy.quiet_hours_end.minute,
        second=policy.quiet_hours_end.second,
        microsecond=policy.quiet_hours_end.microsecond,
    )
    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate


__all__ = ["NotificationOrchestrator"]
