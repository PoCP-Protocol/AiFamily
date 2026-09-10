from datetime import UTC, datetime, time

import pytest

from backend.platform.notification.contracts import (
    DeliveryDecision,
    NotificationChannel,
    NotificationIntent,
    NotificationPolicy,
    NotificationScope,
)


def _scope() -> NotificationScope:
    return NotificationScope("tenant-a", "family-a", "person-a", "growth_tracking", "c-1")


def test_intent_identity_is_tenant_and_family_scoped() -> None:
    first = NotificationIntent.create(
        scope=_scope(),
        channel=NotificationChannel.PUSH,
        template_key="task.reminder",
        idempotency_key="task-1",
        correlation_id="corr-1",
        body="请查看今日成长行动",
    )
    replay = NotificationIntent.create(
        scope=_scope(),
        channel=NotificationChannel.PUSH,
        template_key="task.reminder",
        idempotency_key="task-1",
        correlation_id="corr-1",
        body="请查看今日成长行动",
    )
    assert first.intent_id == replay.intent_id


def test_intent_rejects_wrong_identity() -> None:
    with pytest.raises(ValueError, match="id must match"):
        NotificationIntent(
            intent_id=__import__("uuid").uuid4(),
            scope=_scope(),
            channel=NotificationChannel.PUSH,
            template_key="task.reminder",
            idempotency_key="task-1",
            correlation_id="corr-1",
            body="body",
            created_at=datetime.now(UTC),
        )


def test_consent_and_revoke_fail_closed() -> None:
    at = datetime(2026, 9, 10, 12, tzinfo=UTC)
    assert (
        NotificationPolicy(False).decide(channel=NotificationChannel.PUSH, at=at)
        is DeliveryDecision.REJECT
    )
    assert (
        NotificationPolicy(True, revoked=True).decide(channel=NotificationChannel.PUSH, at=at)
        is DeliveryDecision.REJECT
    )


def test_quiet_hours_suppress_external_channels_but_not_in_app() -> None:
    policy = NotificationPolicy(True, quiet_hours_start=time(22), quiet_hours_end=time(7))
    at = datetime(2026, 9, 10, 23, tzinfo=UTC)
    assert policy.decide(channel=NotificationChannel.PUSH, at=at) is DeliveryDecision.SUPPRESS
    assert policy.decide(channel=NotificationChannel.IN_APP, at=at) is DeliveryDecision.ALLOW
