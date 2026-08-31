from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.journey.api.routes import (
    JourneyPlanActor,
    JourneyPlanHttpDependencies,
    build_journey_plan_router,
)
from backend.domains.journey.application.plan_service import JourneyPlanService


def _client() -> TestClient:
    app = FastAPI()
    service = JourneyPlanService()

    async def resolve_actor(authorization: str | None) -> JourneyPlanActor:
        if authorization != "Bearer parent-a":
            raise RuntimeError("unknown actor")
        return JourneyPlanActor("parent-a", "tenant-a", "family-a")

    async def resolve_focus(actor: JourneyPlanActor, focus_id: str) -> str | None:
        return focus_id if focus_id == "focus-1" else None

    app.include_router(
        build_journey_plan_router(
            JourneyPlanHttpDependencies(resolve_actor, resolve_focus, service)
        )
    )
    return TestClient(app)


def _headers(key: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer parent-a",
        "X-Tenant-Id": "tenant-a",
        "Idempotency-Key": key,
    }


def test_http_plan_confirm_readback_and_review() -> None:
    client = _client()
    created = client.post(
        "/families/family-a/growth/journey-plan",
        headers=_headers("create-1"),
        json={"focus_id": "focus-1", "goal_text": "先听懂彼此"},
    )
    assert created.status_code == 200
    plan_id = created.json()["plan"]["plan_id"]

    confirmed = client.post(
        f"/families/family-a/growth/journey-plan/{plan_id}/confirm",
        headers=_headers("confirm-1"),
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["plan"]["status"] == "ACTIVE"

    readback = client.get(
        f"/families/family-a/growth/journey-plan/{plan_id}",
        headers={"Authorization": "Bearer parent-a", "X-Tenant-Id": "tenant-a"},
    )
    assert readback.status_code == 200
    assert readback.json()["plan"]["status"] == "ACTIVE"

    reviewed = client.post(
        f"/families/family-a/growth/journey-plan/{plan_id}/review",
        headers=_headers("review-1"),
        json={"decision": "PAUSE", "observation": "先暂停"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["plan"]["status"] == "PAUSED"


def test_http_rejects_missing_auth_and_cross_scope() -> None:
    client = _client()
    assert client.get("/families/family-a/growth/journey-plan/x").status_code == 401
    assert (
        client.post(
            "/families/family-b/growth/journey-plan",
            headers={**_headers("create-1"), "X-Tenant-Id": "tenant-a"},
            json={"focus_id": "focus-1", "goal_text": "共同决定"},
        ).status_code
        == 403
    )
