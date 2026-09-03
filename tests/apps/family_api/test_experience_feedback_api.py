from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.apps.family_api.main import create_app
from backend.intelligence.experience.achievement import AchievementEngine
from backend.intelligence.experience.contracts import ExperienceEventType
from backend.intelligence.experience.feedback_read import FeedbackReadRuntime
from backend.intelligence.experience.projections import StoredAchievementNotification
from tests.intelligence.experience.test_gateway import _event


class Reader:
    def __init__(self):
        event = _event(
            event_id="api-feedback-event",
            event_type=ExperienceEventType.ACTION_COMPLETED,
            occurred_at=datetime(2026, 8, 30, tzinfo=UTC),
        )
        self.scope = event.scope
        self.achievement = AchievementEngine().apply(event)[0]
        self.notification = StoredAchievementNotification(
            notification_id="achievement-notification:api-feedback",
            achievement_id=self.achievement.achievement_id,
            tenant_id=self.scope.tenant_id,
            family_id=self.scope.family_id,
            subject_ids=self.scope.subject_ids,
            title="完成一个小目标",
            message="继续保持家庭节奏",
            status="UNREAD",
            created_at=event.occurred_at,
            read_at=None,
        )

    async def achievements(self, _scope):
        return (self.achievement,)

    async def unread_notifications(self, _scope):
        return (self.notification,) if self.notification.status == "UNREAD" else ()

    async def mark_notification_read(self, notification_id, _scope):
        if notification_id != self.notification.notification_id:
            raise ValueError("ACHIEVEMENT_NOTIFICATION_NOT_FOUND")
        if self.notification.status == "UNREAD":
            self.notification = replace(
                self.notification,
                status="READ",
                read_at=datetime(2026, 8, 30, 1, tzinfo=UTC),
            )
        return self.notification

    async def analytics(self, _scope):
        return (("event:action_completed", 1), ("achievement:first_step", 1))


class Resolver:
    def __init__(self, reader: Reader):
        self.reader = reader

    async def resolve(self, family_id: str):
        if family_id != self.reader.scope.family_id:
            raise PermissionError("family mismatch")
        return FeedbackReadRuntime(scope=self.reader.scope, reader=self.reader)


def test_feedback_api_returns_private_projection_without_rank_or_score_fields():
    reader = Reader()
    app = create_app(feedback_runtime_resolver=Resolver(reader))
    with TestClient(app) as client:
        response = client.get(f"/families/{reader.scope.family_id}/experience/achievements")
        assert response.status_code == 200
        body = response.json()
        assert body["visibility"] == "FAMILY_PRIVATE"
        assert body["achievements"][0]["occurrence_id"] == "default"
        assert "rank" not in body and "score" not in body

        analytics = client.get(f"/families/{reader.scope.family_id}/experience/analytics")
        assert analytics.status_code == 200
        assert analytics.json()["metrics"][0]["value_count"] == 1

        missing_key = client.post(
            f"/families/{reader.scope.family_id}/experience/notifications/{reader.notification.notification_id}/read"
        )
        assert missing_key.status_code == 422

        path = (
            f"/families/{reader.scope.family_id}/experience/notifications/"
            f"{reader.notification.notification_id}/read"
        )
        receipt = client.post(path, headers={"Idempotency-Key": "read-notification-1"})
        assert receipt.status_code == 200
        assert receipt.json()["status"] == "READ"
        retry = client.post(path, headers={"Idempotency-Key": "read-notification-1"})
        assert retry.status_code == 200
        assert retry.json()["read_at"] == receipt.json()["read_at"]


def test_feedback_api_fails_closed_without_scope_resolver():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/families/family-a/experience/notifications")
    assert response.status_code == 503
    assert response.json()["detail"] == "experience_feedback_runtime_not_configured"
