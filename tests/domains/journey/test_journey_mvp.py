from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.journey.api.routes import (
    JourneyAuthenticationError,
    JourneyHttpDependencies,
    build_journey_router,
)
from backend.domains.journey.application.ports import JourneyActor
from backend.domains.journey.application.service import HumanFamilyPolicy, JourneyService
from backend.domains.journey.domain.models import PhaseStatus, PlanStatus
from backend.domains.journey.infrastructure.memory import InMemoryJourneyRepository

TENANT = "tenant-a"
FAMILY = "family-a"
ONBOARDING = "onboarding-a"
PRIORITY = "priority-a"


def _app(repository: InMemoryJourneyRepository) -> FastAPI:
    service = JourneyService(repository, HumanFamilyPolicy())

    async def resolve_actor(authorization: str | None, family_id: str) -> JourneyActor:
        if authorization == "Bearer parent":
            return JourneyActor("parent-1", TENANT, FAMILY)
        if authorization == "Bearer ai":
            return JourneyActor("agent-1", TENANT, FAMILY, actor_type="AI")
        if authorization == "Bearer other-family":
            return JourneyActor("parent-2", TENANT, "family-b")
        if authorization == "Bearer other-tenant":
            return JourneyActor("parent-3", "tenant-b", family_id)
        raise JourneyAuthenticationError()

    app = FastAPI()
    app.include_router(build_journey_router(JourneyHttpDependencies(resolve_actor, service)))
    return app


def _seed(repository: InMemoryJourneyRepository) -> None:
    repository.add_confirmed_priority(
        tenant_id=TENANT,
        family_id=FAMILY,
        onboarding_id=ONBOARDING,
        priority_id=PRIORITY,
    )


def _create(client: TestClient, key: str = "create-1") -> dict:
    response = client.post(
        f"/families/{FAMILY}/growth/onboardings/{ONBOARDING}/journey-plan",
        headers={"Authorization": "Bearer parent", "Idempotency-Key": key},
        json={"priority_id": PRIORITY},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_read_confirm_and_first_action_form_one_family_loop() -> None:
    repository = InMemoryJourneyRepository()
    _seed(repository)
    with TestClient(_app(repository)) as client:
        created = _create(client)
        plan = created["plan"]
        assert created["created"] is True
        assert plan["horizon_days"] == 21
        assert plan["status"] == PlanStatus.DRAFT
        assert [phase["status"] for phase in plan["phases"]] == [
            PhaseStatus.PENDING,
            PhaseStatus.PENDING,
            PhaseStatus.PENDING,
        ]

        replay = _create(client)
        assert replay["created"] is True
        assert replay["replayed"] is True
        assert replay["plan"]["plan_id"] == plan["plan_id"]

        confirmed = client.post(
            f"/families/{FAMILY}/growth/journey-plans/{plan['plan_id']}/confirm",
            headers={"Authorization": "Bearer parent", "Idempotency-Key": "confirm-1"},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["plan"]["status"] == PlanStatus.ACTIVE
        assert confirmed.json()["plan"]["phases"][0]["status"] == PhaseStatus.ACTIVE

        action = client.post(
            f"/families/{FAMILY}/growth/journey-plans/{plan['plan_id']}/actions",
            headers={"Authorization": "Bearer parent", "Idempotency-Key": "action-1"},
            json={"action_text": "今晚先完整听完孩子想说的事"},
        )
        assert action.status_code == 200, action.text
        assert action.json()["action"]["day_no"] == 1
        assert action.json()["plan"]["current_day"] == 2

        detail = client.get(
            f"/families/{FAMILY}/growth/journey-plans/{plan['plan_id']}",
            headers={"Authorization": "Bearer parent"},
        )
        assert detail.status_code == 200
        assert len(detail.json()["actions"]) == 1
        assert detail.json()["outcome_status"] == "NOT_MEASURED"
        assert "score" not in detail.text.lower()
        assert "rank" not in detail.text.lower()


def test_phase_review_opens_after_seven_actions_and_continue_moves_phase() -> None:
    repository = InMemoryJourneyRepository()
    _seed(repository)
    with TestClient(_app(repository)) as client:
        plan_id = _create(client)["plan"]["plan_id"]
        client.post(
            f"/families/{FAMILY}/growth/journey-plans/{plan_id}/confirm",
            headers={"Authorization": "Bearer parent", "Idempotency-Key": "confirm-1"},
        )
        for day in range(1, 8):
            response = client.post(
                f"/families/{FAMILY}/growth/journey-plans/{plan_id}/actions",
                headers={
                    "Authorization": "Bearer parent",
                    "Idempotency-Key": f"action-{day}",
                },
                json={"action_text": f"第 {day} 天家庭小行动"},
            )
            assert response.status_code == 200, response.text

        review = client.post(
            f"/families/{FAMILY}/growth/journey-plans/{plan_id}/phase-review",
            headers={"Authorization": "Bearer parent", "Idempotency-Key": "review-1"},
            json={"decision": "CONTINUE", "notes": "继续这个节奏"},
        )
        assert review.status_code == 200, review.text
        assert review.json()["review"]["phase"] == "NOTICE"
        assert review.json()["plan"]["current_phase"] == "PRACTICE"
        assert review.json()["plan"]["current_day"] == 8
        assert review.json()["plan"]["phases"][0]["status"] == PhaseStatus.COMPLETED
        assert review.json()["plan"]["phases"][1]["status"] == PhaseStatus.ACTIVE


def test_scope_auth_and_human_gate_are_fail_closed() -> None:
    repository = InMemoryJourneyRepository()
    _seed(repository)
    with TestClient(_app(repository)) as client:
        missing = client.get(f"/families/{FAMILY}/growth/journey-plan")
        assert missing.status_code == 401

        other_family = client.get(
            f"/families/{FAMILY}/growth/journey-plan",
            headers={"Authorization": "Bearer other-family"},
        )
        assert other_family.status_code == 403

        ai = client.post(
            f"/families/{FAMILY}/growth/onboardings/{ONBOARDING}/journey-plan",
            headers={"Authorization": "Bearer ai", "Idempotency-Key": "ai-create"},
            json={"priority_id": PRIORITY},
        )
        assert ai.status_code == 403
        assert ai.json()["detail"] == "journey_mutation_requires_human_actor"

        missing_key = client.post(
            f"/families/{FAMILY}/growth/onboardings/{ONBOARDING}/journey-plan",
            headers={"Authorization": "Bearer parent"},
            json={"priority_id": PRIORITY},
        )
        assert missing_key.status_code == 400


def test_idempotency_conflict_and_tenant_isolation() -> None:
    repository = InMemoryJourneyRepository()
    _seed(repository)
    with TestClient(_app(repository)) as client:
        _create(client)
        conflict = client.post(
            f"/families/{FAMILY}/growth/onboardings/{ONBOARDING}/journey-plan",
            headers={"Authorization": "Bearer parent", "Idempotency-Key": "create-1"},
            json={"priority_id": "another-priority"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"] == "idempotency_conflict"

        other_tenant = client.get(
            f"/families/{FAMILY}/growth/journey-plan",
            headers={"Authorization": "Bearer other-tenant"},
        )
        assert other_tenant.status_code == 200
        assert other_tenant.json()["plan"] is None
