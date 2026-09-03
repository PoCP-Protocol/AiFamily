from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.journey.api.routes import (
    get_journey_actor,
    get_journey_service,
    register_exception_handlers,
    router,
)
from backend.domains.journey.application.service import JourneyActor, JourneyService
from backend.domains.journey.infrastructure.memory_repository import InMemoryJourneyRepository


class AllowPolicy:
    async def assert_can_read(self, family_id: str, actor_id: str) -> None:
        return None

    async def assert_can_manage(self, family_id: str, actor_id: str) -> None:
        return None

    async def assert_creation_preconditions(
        self, family_id: str, onboarding_id: str, actor_id: str
    ) -> None:
        return None


def _client() -> tuple[TestClient, InMemoryJourneyRepository]:
    family_id = "family-1"
    repository = InMemoryJourneyRepository()
    repository.active_priorities.add((family_id, "onboarding-1", "priority-1"))
    repository.priority_dimensions[(family_id, "onboarding-1", "priority-1")] = "R03"
    repository.active_onboardings.add((family_id, "onboarding-1"))
    service = JourneyService(repository, AllowPolicy())
    app = FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    app.dependency_overrides[get_journey_actor] = lambda: JourneyActor("actor-1", family_id)
    app.dependency_overrides[get_journey_service] = lambda: service
    return TestClient(app), repository


def test_create_confirm_and_project_journey_plan() -> None:
    client, repository = _client()
    created = client.post(
        "/families/family-1/growth/onboardings/onboarding-1/journey-plan",
        headers={"Idempotency-Key": "create-1"},
        json={"priority_id": "priority-1"},
    )
    assert created.status_code == 200
    plan = created.json()["plan"]
    assert plan["status"] == "DRAFT"
    assert plan["phases"][0] == {"phase": "SEE", "status": "PENDING"}

    confirmed = client.post(
        f"/families/family-1/growth/journey-plans/{plan['plan_id']}/confirm",
        headers={"Idempotency-Key": "confirm-1"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["plan"]["status"] == "ACTIVE"
    assert confirmed.json()["plan"]["phases"][0]["status"] == "ACTIVE"

    repository.completed_actions[plan["plan_id"]] = 3
    service_journey = client.get(
        "/families/family-1/growth/onboardings/onboarding-1/service-journey"
    )
    assert service_journey.status_code == 200
    assert service_journey.json()["state"] == "READY"
    assert service_journey.json()["process_summary"] == {
        "label": "已留下 3 次家庭行动记录",
        "completed_actions": 3,
        "boundary": "PROCESS_PROJECTION_NOT_SCORE_OR_OUTCOME",
    }
    assert service_journey.json()["source_plan_id"] == plan["plan_id"]

    projection = client.get("/families/family-1/growth/journey-plan")
    assert projection.status_code == 200
    assert projection.json()["plan"]["plan_id"] == plan["plan_id"]
    assert projection.json()["model_gateway_status"] == "NOOP"


def test_rejects_missing_priority_and_cross_family_scope() -> None:
    client, _repository = _client()
    missing = client.post(
        "/families/family-1/growth/onboardings/onboarding-1/journey-plan",
        headers={"Idempotency-Key": "create-2"},
        json={"priority_id": "missing"},
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "active_growth_priority_not_found"}

    denied = client.get("/families/family-2/growth/journey-plan")
    assert denied.status_code == 403
    assert denied.json() == {"detail": "family_access_denied"}


def test_requires_idempotency_key_for_mutations() -> None:
    client, _repository = _client()
    response = client.post(
        "/families/family-1/growth/onboardings/onboarding-1/journey-plan",
        json={"priority_id": "priority-1"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid_idempotency_key"}


def test_priority_and_rule_based_plan_preview_support_ui04() -> None:
    client, _repository = _client()
    priority = client.get(
        "/families/family-1/growth/onboardings/onboarding-1/priority"
    )
    assert priority.status_code == 200
    assert priority.json()["active_priority"]["priority_id"] == "priority-1"

    preview = client.get(
        "/families/family-1/growth/onboardings/onboarding-1/plan-preview"
    )
    assert preview.status_code == 200
    assert preview.json()["state"] == "FAMILY_REVIEW"
    assert [item["stage_id"] for item in preview.json()["structure"]["stages"]] == [
        "SEE",
        "ADJUST",
        "CO_CREATE",
        "STABILIZE",
    ]
    assert preview.json()["model_gateway_status"] == "NOOP_NOT_INVOKED"

    refreshed = client.post(
        "/families/family-1/growth/onboardings/onboarding-1/plan-preview/refresh",
        headers={"Idempotency-Key": "refresh-1"},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refreshed"] is True
    assert refreshed.json()["external_effect"] is False


def test_preview_requires_active_onboarding() -> None:
    client, _repository = _client()
    response = client.get(
        "/families/family-1/growth/onboardings/missing/plan-preview"
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "active_growth_onboarding_not_found"}

    service_journey = client.get(
        "/families/family-1/growth/onboardings/missing/service-journey"
    )
    assert service_journey.status_code == 404
    assert service_journey.json() == {"detail": "active_growth_onboarding_not_found"}


def test_service_journey_requires_confirmed_plan_before_ready() -> None:
    client, _repository = _client()
    response = client.get(
        "/families/family-1/growth/onboardings/onboarding-1/service-journey"
    )
    assert response.status_code == 200
    assert response.json()["state"] == "REVIEW_REQUIRED"
    assert response.json()["process_summary"]["completed_actions"] == 0
    assert response.json()["visibility"] == "FAMILY_PRIVATE"


def test_family_confirms_eligible_priority_and_replay_is_stable() -> None:
    client, repository = _client()
    repository.active_priorities.clear()
    repository.priority_candidates[("family-1", "onboarding-1")] = (
        "profile-1",
        "R03",
        "child-1",
    )
    draft = client.get(
        "/families/family-1/growth/onboardings/onboarding-1/priority"
    ).json()["draft"]

    response = client.post(
        "/families/family-1/growth/onboardings/onboarding-1/priority/confirm",
        headers={"Idempotency-Key": "priority-confirm-1"},
        json={"draft_id": draft["draft_id"], "decision": "R03"},
    )
    assert response.status_code == 200
    assert response.json()["priority"]["dimension_id"] == "R03"
    assert response.json()["draft"]["boundary"] == (
        "PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS"
    )

    replay = client.post(
        "/families/family-1/growth/onboardings/onboarding-1/priority/confirm",
        headers={"Idempotency-Key": "priority-confirm-1"},
        json={"draft_id": draft["draft_id"], "decision": "R03"},
    )
    assert replay.status_code == 200
    assert replay.json() == response.json()


def test_family_can_defer_without_writing_hidden_priority() -> None:
    client, repository = _client()
    repository.active_priorities.clear()
    repository.priority_candidates[("family-1", "onboarding-1")] = (
        "profile-1",
        "R03",
        "child-1",
    )
    draft = client.get(
        "/families/family-1/growth/onboardings/onboarding-1/priority"
    ).json()["draft"]
    response = client.post(
        "/families/family-1/growth/onboardings/onboarding-1/priority/confirm",
        headers={"Idempotency-Key": "priority-defer-1"},
        json={"draft_id": draft["draft_id"], "decision": "NO_PRIORITY_YET"},
    )
    assert response.status_code == 200
    assert response.json()["priority"] is None
    assert repository.active_priorities == set()


def test_priority_confirmation_rejects_stale_or_ineligible_decision() -> None:
    client, repository = _client()
    repository.active_priorities.clear()
    repository.priority_candidates[("family-1", "onboarding-1")] = (
        "profile-1",
        "R03",
        "child-1",
    )
    stale = client.post(
        "/families/family-1/growth/onboardings/onboarding-1/priority/confirm",
        headers={"Idempotency-Key": "priority-stale-1"},
        json={"draft_id": "stale", "decision": "R03"},
    )
    assert stale.status_code == 409
    assert stale.json() == {"detail": "growth_priority_draft_stale"}

    draft = client.get(
        "/families/family-1/growth/onboardings/onboarding-1/priority"
    ).json()["draft"]
    ineligible = client.post(
        "/families/family-1/growth/onboardings/onboarding-1/priority/confirm",
        headers={"Idempotency-Key": "priority-ineligible-1"},
        json={"draft_id": draft["draft_id"], "decision": "R04"},
    )
    assert ineligible.status_code == 409
    assert ineligible.json() == {"detail": "growth_priority_decision_not_eligible"}


def test_default_dependencies_fail_closed_without_postgres(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get(
        "/families/family-1/growth/journey-plan",
        headers={"Authorization": "Bearer development-token-must-not-be-trusted"},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "journey_postgres_not_configured"}
