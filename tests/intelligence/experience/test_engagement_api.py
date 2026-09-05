from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.intelligence.experience.contracts import ExperienceEvent, ExperienceScope
from backend.intelligence.experience.engagement import (
    EngagementDraftApplication,
    EngagementDraftService,
)
from backend.intelligence.experience.engagement_api import (
    get_engagement_draft_runtime_resolver,
    router,
)
from backend.intelligence.experience.synthetic_engagement_runtime import (
    SyntheticEngagementRuntimeResolver,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.experience.test_engagement import _output
from tests.intelligence.experience.test_gateway import _event
from tests.intelligence.model_gateway.test_fail_closed import build


@dataclass
class _Runtime:
    scope: ExperienceScope
    application: EngagementDraftApplication
    provider_id: str = "fake-deterministic"

    async def generate_draft(
        self,
        *,
        request_id: str,
        event_ids: tuple[str, ...],
        payload: dict[str, object] | None = None,
    ):
        return await self.application.generate_draft(
            request_id=request_id,
            provider_id=self.provider_id,
            scope=self.scope,
            actor_id="guardian-api",
            authorization_ref="auth:api",
            event_ids=event_ids,
            context_snapshot_ref="context:api",
            payload=payload,
        )


class _Reader:
    def __init__(self, event: ExperienceEvent) -> None:
        self.event = event

    async def read(self, *, scope, event_ids):
        if scope.family_id != self.event.scope.family_id:
            return ()
        return (self.event,) if event_ids == (self.event.event_id,) else ()


def _client(resolver: object | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if resolver is not None:
        app.dependency_overrides[get_engagement_draft_runtime_resolver] = lambda: resolver
    return TestClient(app)


def _runtime() -> tuple[_Runtime, FakeProvider]:
    event = _event(event_id="engagement-api-event")
    provider = FakeProvider(
        {"family-engagement-draft": _output(evidence_refs=[event.event_id])}
    )
    application = EngagementDraftApplication(
        EngagementDraftService(build(provider)), _Reader(event)
    )
    return _Runtime(event.scope, application), provider


def test_engagement_route_fails_closed_without_runtime() -> None:
    with _client() as client:
            response = client.post(
            "/families/family-a/experience/engagement/drafts",
            json={"request_id": "req-1", "event_ids": ["event-1"]},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "engagement_runtime_not_configured"


def test_engagement_route_reads_server_events_and_returns_draft() -> None:
    runtime, provider = _runtime()

    class Resolver:
        async def resolve(self, family_id: str):
            assert family_id == "family-a"
            return runtime

    with _client(Resolver()) as client:
            response = client.post(
            "/families/family-a/experience/engagement/drafts",
            json={
                "request_id": "req-1",
                "event_ids": ["engagement-api-event"],
                "payload": {"tone": "encouraging"},
            },
        )

    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "DRAFT"
    assert value["draft_id"].startswith("engagement-draft:")
    assert value["requires_human_confirmation"] is True
    assert value["evidence_event_ids"] == ["engagement-api-event"]
    assert value["scope"]["family_id"] == "family-a"
    assert value["provenance"]["provider_id"] == "fake-deterministic"
    assert len(provider.invocations) == 1


def test_engagement_route_rejects_client_scope_controls_before_runtime() -> None:
    calls: list[str] = []

    class Resolver:
        async def resolve(self, family_id: str):
            calls.append(family_id)
            return _runtime()[0]

    with _client(Resolver()) as client:
        response = client.post(
            "/families/family-api/experience/engagement/drafts",
            json={
                "request_id": "req-1",
                "event_ids": ["engagement-api-event"],
                "payload": {"nested": {"provider_id": "forged"}},
            },
        )

    assert response.status_code == 422
    assert "controlled by the server" in response.text
    assert calls == []


def test_synthetic_http_flow_persists_draft_and_opens_human_task_by_candidate_id() -> None:
    resolver = SyntheticEngagementRuntimeResolver(
        tenant_id="tenant-synthetic-review",
        subject_ids=("child-synthetic-review",),
        environment="test",
    )
    with _client(resolver) as client:
        generated = client.post(
            "/families/family-synthetic-review/experience/engagement/drafts",
            json={"request_id": "review-http-1", "event_ids": ["event-http-1"]},
        )
        assert generated.status_code == 200
        draft_id = generated.json()["draft_id"]
        submitted = client.post(
            f"/families/family-synthetic-review/experience/engagement/drafts/{draft_id}/"
            "achievement-candidates/synthetic-achievement-1/human-task",
            headers={"Idempotency-Key": "review-http-submit-1"},
            json={},
        )
        decided = client.post(
            f"/families/family-synthetic-review/experience/engagement/human-tasks/"
            f"{submitted.json()['task_id']}/decisions",
            headers={"Idempotency-Key": "review-http-decision-1"},
            json={"outcome": "ACCEPT"},
        )

    assert submitted.status_code == 201
    task = submitted.json()
    assert task["status"] == "OPEN"
    assert task["draft_id"] == draft_id
    assert task["candidate_id"] == "synthetic-achievement-1"
    assert task["message"] == "记录这次模拟尝试"
    assert task["evidence_refs"] == ["experience-event:event-http-1"]
    assert decided.status_code == 200
    assert decided.json()["status"] == "DECIDED"
    assert decided.json()["decision_outcome"] == "ACCEPT"


def test_candidate_submission_rejects_client_supplied_proposal_fields() -> None:
    resolver = SyntheticEngagementRuntimeResolver(
        tenant_id="tenant-synthetic-review",
        subject_ids=("child-synthetic-review",),
        environment="test",
    )
    with _client(resolver) as client:
        response = client.post(
            "/families/family-synthetic-review/experience/engagement/drafts/unknown/"
            "achievement-candidates/candidate/human-task",
            headers={"Idempotency-Key": "review-http-forged"},
            json={"message": "forged", "scope": {"family_id": "other"}},
        )

    assert response.status_code == 422
