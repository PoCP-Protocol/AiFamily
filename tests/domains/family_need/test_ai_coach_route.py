"""AI Coach HTTP route — FakeProvider contract tests.

These tests never call a real model. They verify the governance-relevant
plumbing that must hold regardless of which provider answers:

* the schema-validated structure (guiding_question/reflection) round-trips
  through the route;
* the payload sent to the provider carries real need data, not fabricated
  content;
* a schema-violating model response is rejected fail-closed rather than
  silently patched;
* provenance is complete.

Real generative behaviour is verified separately and only when
`AI_COACH_MODEL_API_KEY` is set — see
`tests/intelligence/experience/test_family_ai_coach_real_model.py`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.family_need.api.ai_coach_dependencies import AiCoachDeps, get_ai_coach_deps
from backend.domains.family_need.api.dependencies import (
    FamilyNeedActor,
    get_family_need_actor,
    get_family_need_service,
)
from backend.domains.family_need.api.routes import register_exception_handlers, router
from backend.domains.family_need.application.service import FamilyNeedApplicationService
from backend.domains.family_need.domain.value_objects import ActorType
from backend.domains.family_need.infrastructure.fake_repository import (
    FakeFamilyNeedPolicy,
    FakeFamilyNeedRepository,
)
from backend.intelligence.model_gateway.gateway import build_gateway
from backend.intelligence.model_gateway.provider_registry import default_provider_registry
from backend.intelligence.model_gateway.providers.fake import FakeProvider

_TENANT_ID = "tenant-1"
_FAMILY_ID = "family-1"
_ACTOR_ID = "guardian-1"

_COACH_USE_CASE = "FAMILY_AI_COACH_SOCRATIC_PERSPECTIVE"


def _capture_body() -> dict:
    # `data_class: PUBLIC` here is deliberate, not a shortcut: it is what maps
    # to the gateway's `OPERATIONAL_TEXT`, the only class `fake-deterministic`
    # is registered to receive (see `provider_registry.py`). A need captured
    # as `MINOR_PERSONAL_DATA`/`FAMILY_PRIVATE` is correctly rejected by
    # admission for *every* shipped provider today — including the fake one
    # — because no provider (real or fake) has a §16-equivalent clearance for
    # regulated data recorded for it. That rejection is the governance working
    # as intended, not a bug this test should route around.
    return {
        "raw_text": "孩子每天写作业都拖到很晚，说了很多次都没用",
        "statement": "孩子写作业拖延，已经上过一门课但没完全解决",
        "desired_outcome": "希望孩子能自己按时开始写作业",
        "source": "FAMILY_EXPRESSED",
        "purpose": "FAMILY_NEED",
        "consent_version": "v1",
        "data_class": "PUBLIC",
        "subject_person_ids": ["child-1"],
    }


def _build_client(
    *, fake_provider: FakeProvider | None = None
) -> tuple[TestClient, FakeFamilyNeedRepository, FakeProvider]:
    repository = FakeFamilyNeedRepository()
    policy = FakeFamilyNeedPolicy()
    policy.bind_family(_TENANT_ID, _FAMILY_ID)
    policy.grant_actor(_FAMILY_ID, _ACTOR_ID, ActorType.FAMILY_GUARDIAN)
    policy.add_subject(_FAMILY_ID, "child-1")
    policy.grant_consent(_FAMILY_ID, "child-1", "FAMILY_NEED", "v1")
    service = FamilyNeedApplicationService(repository, policy)

    provider = fake_provider or FakeProvider(
        provider_id="fake-deterministic",
        responses_by_use_case={
            _COACH_USE_CASE: {
                "reflection": "听起来这件事已经反复出现，家长也尝试过办法，还是感觉卡住了。",
                "guiding_question": "如果今晚孩子主动开始写作业，你觉得会是什么让他愿意开始？",
            }
        },
    )
    registry = default_provider_registry()
    gateway = build_gateway(
        environment="test",
        providers={"fake-deterministic": provider},
        registry=registry,
    )

    app = FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    app.dependency_overrides[get_family_need_actor] = lambda: FamilyNeedActor(
        tenant_id=_TENANT_ID,
        family_id=_FAMILY_ID,
        actor_id=_ACTOR_ID,
        actor_type=ActorType.FAMILY_GUARDIAN,
    )
    app.dependency_overrides[get_family_need_service] = lambda: service
    app.dependency_overrides[get_ai_coach_deps] = lambda: AiCoachDeps(
        gateway=gateway,
        repository=repository,
        provider_id="fake-deterministic",
    )
    return TestClient(app), repository, provider


def _capture_need(client: TestClient) -> str:
    response = client.post(
        f"/families/{_FAMILY_ID}/needs/signals",
        json=_capture_body(),
        headers={"Idempotency-Key": "coach-need-1"},
    )
    assert response.status_code == 201
    return response.json()["need"]["need_id"]


def test_ai_coach_route_returns_guiding_question_and_reflection_and_boundary() -> None:
    client, _, _ = _build_client()
    need_id = _capture_need(client)

    response = client.post(
        f"/families/{_FAMILY_ID}/needs/{need_id}/ai-coach/messages",
        json={"parent_message": "孩子今天又没写作业，我不知道该怎么办了"},
        headers={"Idempotency-Key": "coach-msg-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "AI_COACH_PERSPECTIVE"
    assert body["boundary"] == "AI_PERSPECTIVE_NOT_FAMILY_FACT_GUIDANCE_NOT_ANSWER"
    assert body["reflection"]
    assert body["guiding_question"]
    assert "answer" not in body
    assert "solution" not in body


def test_ai_coach_context_sent_to_provider_carries_real_need_data_not_fabricated() -> None:
    client, _, provider = _build_client()
    need_id = _capture_need(client)

    client.post(
        f"/families/{_FAMILY_ID}/needs/{need_id}/ai-coach/messages",
        json={"parent_message": "孩子今天又没写作业"},
        headers={"Idempotency-Key": "coach-msg-2"},
    )

    assert len(provider.invocations) == 1
    request = provider.invocations[0]
    assert request.use_case == _COACH_USE_CASE
    family_context = request.payload["family_context"]
    assert family_context["need_statement"] == _capture_body()["statement"]
    assert family_context["desired_outcome"] == _capture_body()["desired_outcome"]
    assert request.payload["parent_message"] == "孩子今天又没写作业"


def test_ai_coach_provenance_is_complete() -> None:
    client, _, _ = _build_client()
    need_id = _capture_need(client)

    response = client.post(
        f"/families/{_FAMILY_ID}/needs/{need_id}/ai-coach/messages",
        json={"parent_message": "孩子今天又没写作业"},
        headers={"Idempotency-Key": "coach-msg-3"},
    )

    provenance = response.json()["provenance"]
    assert provenance["provider_id"] == "fake-deterministic"
    assert provenance["model"]
    assert provenance["prompt_version"] == "family-ai-coach-prompt-v1"
    assert provenance["schema_version"] == "family-ai-coach-schema-v1"
    assert provenance["context_snapshot_ref"]
    assert isinstance(provenance["latency_ms"], int)


def test_ai_coach_route_fails_closed_on_schema_violating_model_response() -> None:
    bad_provider = FakeProvider(
        provider_id="fake-deterministic",
        # Missing required "guiding_question" — must be rejected, not patched
        # with a filler question.
        responses_by_use_case={_COACH_USE_CASE: {"reflection": "只反馈，没有问题"}},
    )
    client, _, _ = _build_client(fake_provider=bad_provider)
    need_id = _capture_need(client)

    response = client.post(
        f"/families/{_FAMILY_ID}/needs/{need_id}/ai-coach/messages",
        json={"parent_message": "孩子今天又没写作业"},
        headers={"Idempotency-Key": "coach-msg-4"},
    )

    assert response.status_code >= 400


def test_ai_coach_route_requires_idempotency_key() -> None:
    client, _, _ = _build_client()
    need_id = _capture_need(client)

    response = client.post(
        f"/families/{_FAMILY_ID}/needs/{need_id}/ai-coach/messages",
        json={"parent_message": "孩子今天又没写作业"},
    )

    assert response.status_code == 400


def test_ai_coach_route_rejects_cross_family_actor() -> None:
    client, _, _ = _build_client()
    need_id = _capture_need(client)

    response = client.post(
        f"/families/family-2/needs/{need_id}/ai-coach/messages",
        json={"parent_message": "孩子今天又没写作业"},
        headers={"Idempotency-Key": "coach-msg-5"},
    )

    assert response.status_code == 403


def test_ai_coach_route_404s_for_unknown_need() -> None:
    client, _, _ = _build_client()

    response = client.post(
        f"/families/{_FAMILY_ID}/needs/does-not-exist/ai-coach/messages",
        json={"parent_message": "孩子今天又没写作业"},
        headers={"Idempotency-Key": "coach-msg-6"},
    )

    assert response.status_code == 404
