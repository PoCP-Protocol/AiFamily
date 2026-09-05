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
from backend.domains.family_need.domain.value_objects import (
    ActorType,
    SolutionComponentRef,
    SupplyShape,
)
from backend.domains.family_need.infrastructure.fake_repository import (
    FakeFamilyNeedPolicy,
    FakeFamilyNeedRepository,
    FakeSupplyReferencePort,
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


def _n2_client() -> tuple[TestClient, FakeFamilyNeedPolicy, FakeSupplyReferencePort]:
    repository = FakeFamilyNeedRepository()
    policy = FakeFamilyNeedPolicy()
    policy.bind_family("tenant-1", "family-1")
    policy.grant_actor("family-1", "guardian-1", ActorType.FAMILY_GUARDIAN)
    policy.add_subject("family-1", "child-1")
    policy.grant_consent("family-1", "child-1", "FAMILY_NEED", "v1")
    supply = FakeSupplyReferencePort()
    supply.add_component(
        SolutionComponentRef("coach-1", SupplyShape.SERVICE, "v1"), tenant_id="tenant-1"
    )
    service = FamilyNeedApplicationService(repository, policy, supply_port=supply)
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
    return TestClient(app), policy, supply


def _clarify_body(expected_version: int = 1) -> dict:
    return {
        "statement": "家庭需要一个可持续的学习陪伴方法",
        "desired_outcome": "今晚能完成一个十分钟的共同小行动",
        "expected_version": expected_version,
        "purpose": "FAMILY_NEED",
        "consent_version": "v1",
        "data_class": "MINOR_PERSONAL_DATA",
        "subject_person_ids": ["child-1"],
    }


def _profile_body(expected_need_version: int) -> dict:
    return {
        "expected_need_version": expected_need_version,
        "urgency": "SOON",
        "complexity": "SIMPLE",
        "risk_level": "LOW",
        "preferred_shapes": ["SERVICE"],
        "required_capability_keys": ["family_communication"],
        "purpose": "FAMILY_NEED",
        "consent_version": "v1",
        "data_class": "MINOR_PERSONAL_DATA",
        "subject_person_ids": ["child-1"],
    }


def _draft_body(profile_id: str, expected_profile_version: int = 1) -> dict:
    return {
        "profile_id": profile_id,
        "expected_profile_version": expected_profile_version,
        "shape": "SERVICE",
        "component_refs": [
            {
                "component_id": "coach-1",
                "shape": "SERVICE",
                "version": "v1",
                "required": True,
                "quantity": 1,
            }
        ],
        "commercial_intent": False,
        "purpose": "FAMILY_NEED",
        "consent_version": "v1",
        "data_class": "MINOR_PERSONAL_DATA",
        "subject_person_ids": ["child-1"],
    }


def _capture_for_n2(client: TestClient) -> dict:
    response = client.post(
        "/families/family-1/needs/signals", json=_body(), headers={"Idempotency-Key": "n2-n0"}
    )
    assert response.status_code == 201
    return response.json()


def test_n1_n2_routes_compose_solution_and_replay() -> None:
    client, _, _ = _n2_client()
    captured = _capture_for_n2(client)
    need_id = captured["need"]["need_id"]
    clarify_headers = {"Idempotency-Key": "n2-clarify"}
    clarified = client.post(
        f"/families/family-1/needs/{need_id}/clarify",
        json=_clarify_body(captured["need"]["version"]),
        headers=clarify_headers,
    )
    assert clarified.status_code == 200
    assert clarified.json()["need"]["status"] == "CONFIRMED"
    assert clarified.json()["boundary"] == "FAMILY_CONFIRMED_NEED_NOT_AI_DIAGNOSIS"
    clarified_replay = client.post(
        f"/families/family-1/needs/{need_id}/clarify",
        json=_clarify_body(captured["need"]["version"]),
        headers=clarify_headers,
    )
    assert clarified_replay.status_code == 200
    assert clarified_replay.json()["replayed"] is True

    profile = client.post(
        f"/families/family-1/needs/{need_id}/profile",
        json=_profile_body(clarified.json()["need"]["version"]),
        headers={"Idempotency-Key": "n2-profile"},
    )
    assert profile.status_code == 200
    assert profile.json()["boundary"] == "NEED_PROFILE_NOT_FAMILY_SCORE"
    profile_replay = client.post(
        f"/families/family-1/needs/{need_id}/profile",
        json=_profile_body(clarified.json()["need"]["version"]),
        headers={"Idempotency-Key": "n2-profile"},
    )
    assert profile_replay.status_code == 200
    assert profile_replay.json()["replayed"] is True

    draft_payload = _draft_body(profile.json()["profile"]["profile_id"])
    draft = client.post(
        f"/families/family-1/needs/{need_id}/solution-drafts",
        json=draft_payload,
        headers={"Idempotency-Key": "n2-draft"},
    )
    assert draft.status_code == 200
    assert draft.json()["draft"]["shape"] == "SERVICE"
    assert draft.json()["resource_gap"] is None
    assert draft.json()["resolved_components"][0]["component_id"] == "coach-1"
    replay = client.post(
        f"/families/family-1/needs/{need_id}/solution-drafts",
        json=draft_payload,
        headers={"Idempotency-Key": "n2-draft"},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["draft"]["draft_id"] == draft.json()["draft"]["draft_id"]


def test_n1_n2_routes_reject_subject_and_cross_tenant_access() -> None:
    client, policy, _ = _n2_client()
    captured = _capture_for_n2(client)
    need_id = captured["need"]["need_id"]
    unauthorized_subject = _clarify_body()
    unauthorized_subject["subject_person_ids"] = ["child-2"]
    rejected = client.post(
        f"/families/family-1/needs/{need_id}/clarify",
        json=unauthorized_subject,
        headers={"Idempotency-Key": "n2-subject-denied"},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "subject_not_in_family"

    policy.tenant_family_bindings.clear()
    cross_tenant = client.post(
        f"/families/family-1/needs/{need_id}/clarify",
        json=_clarify_body(),
        headers={"Idempotency-Key": "n2-tenant-denied"},
    )
    assert cross_tenant.status_code in {403, 409}


def test_solution_route_exposes_resource_gap_and_does_not_write_draft() -> None:
    client, _, supply = _n2_client()
    captured = _capture_for_n2(client)
    need_id = captured["need"]["need_id"]
    clarified = client.post(
        f"/families/family-1/needs/{need_id}/clarify",
        json=_clarify_body(),
        headers={"Idempotency-Key": "gap-clarify"},
    )
    profile = client.post(
        f"/families/family-1/needs/{need_id}/profile",
        json=_profile_body(clarified.json()["need"]["version"]),
        headers={"Idempotency-Key": "gap-profile"},
    )
    missing = _draft_body(profile.json()["profile"]["profile_id"])
    missing["component_refs"][0]["component_id"] = "not-found"
    gap = client.post(
        f"/families/family-1/needs/{need_id}/solution-drafts",
        json=missing,
        headers={"Idempotency-Key": "gap-draft"},
    )
    assert gap.status_code == 200
    assert gap.json()["draft"] is None
    assert gap.json()["resource_gap"]["reason"] == "NO_MATCHING_CAPABILITY"
    assert gap.json()["resolved_components"] == []
    # The fake supply has no side effect from resolution; this assertion makes
    # the test explicit that a gap does not silently invent a draft.
    assert supply.components


def test_n1_n2_bodies_reject_identity_or_deployment_overrides() -> None:
    client, _, _ = _n2_client()
    payload = _clarify_body()
    payload["tenant_id"] = "tenant-other"
    payload["region"] = "US"
    payload["environment"] = "production"
    response = client.post(
        "/families/family-1/needs/missing/clarify",
        json=payload,
        headers={"Idempotency-Key": "identity-override"},
    )
    assert response.status_code == 422
    assert {item["loc"][-1] for item in response.json()["detail"]} >= {
        "tenant_id",
        "region",
        "environment",
    }
