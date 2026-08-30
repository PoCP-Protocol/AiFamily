from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


def _client() -> tuple[TestClient, FakeFamilyNeedPolicy]:
    repository = FakeFamilyNeedRepository()
    policy = FakeFamilyNeedPolicy()
    policy.bind_family("tenant-1", "family-1")
    policy.grant_actor("family-1", "guardian-1", ActorType.FAMILY_GUARDIAN)
    policy.add_subject("family-1", "child-1")
    policy.grant_consent("family-1", "child-1", "FAMILY_NEED", "v1")
    service = FamilyNeedApplicationService(repository, policy)
    app = FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    app.dependency_overrides[get_family_need_actor] = lambda: FamilyNeedActor(
        tenant_id="tenant-1",
        family_id="family-1",
        actor_id="guardian-1",
        actor_type=ActorType.FAMILY_GUARDIAN,
    )
    app.dependency_overrides[get_family_need_service] = lambda: service
    return TestClient(app), policy


def _body() -> dict:
    return {
        "raw_text": "最近每天写作业都很累，想先找到一个能一起坚持的小方法",
        "statement": "家庭需要一个可持续的学习陪伴方法",
        "desired_outcome": "今晚能完成一个十分钟的共同小行动",
        "source": "FAMILY_EXPRESSED",
        "purpose": "FAMILY_NEED",
        "consent_version": "v1",
        "data_class": "MINOR_PERSONAL_DATA",
        "subject_person_ids": ["child-1"],
    }


def test_capture_need_route_returns_n0_n1_and_is_idempotent() -> None:
    client, _ = _client()
    headers = {"Idempotency-Key": "need-1"}
    first = client.post("/families/family-1/needs/signals", json=_body(), headers=headers)
    replay = client.post("/families/family-1/needs/signals", json=_body(), headers=headers)
    assert first.status_code == 201
    assert first.json()["boundary"] == "FAMILY_EXPRESSION_NOT_AI_DIAGNOSIS"
    assert first.json()["need"]["status"] == "CAPTURED"
    assert replay.status_code == 201
    assert replay.json()["replayed"] is True
    assert replay.json()["need"]["need_id"] == first.json()["need"]["need_id"]


def test_capture_need_route_rejects_missing_idempotency_and_cross_family() -> None:
    client, _ = _client()
    missing_key = client.post("/families/family-1/needs/signals", json=_body())
    cross_family = client.post(
        "/families/family-2/needs/signals", json=_body(), headers={"Idempotency-Key": "need-2"}
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["detail"] == "invalid_idempotency_key"
    assert cross_family.status_code == 403
    assert cross_family.json()["detail"] == "family_access_denied"


def test_capture_need_route_rejects_unconsented_child() -> None:
    client, policy = _client()
    policy.grants.clear()
    response = client.post(
        "/families/family-1/needs/signals",
        json=_body(),
        headers={"Idempotency-Key": "need-3"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "consent_not_granted"


def test_capture_need_route_does_not_accept_client_environment_override() -> None:
    client, _ = _client()
    payload = _body()
    payload["environment"] = "production"
    response = client.post(
        "/families/family-1/needs/signals",
        json=payload,
        headers={"Idempotency-Key": "need-4"},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "extra_forbidden"
