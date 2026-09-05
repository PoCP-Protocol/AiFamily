from __future__ import annotations

import pytest

from backend.domains.journey.application.service import JourneyActor
from backend.domains.journey.domain.models import PhaseDecision
from backend.domains.journey.infrastructure.application import (
    SqlAlchemyJourneyApplication,
    build_postgres_journey_application,
)


class Runner:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


async def test_create_routes_through_transaction_runner_with_audit_metadata() -> None:
    runner = Runner({"plan": {"plan_id": "plan-1", "status": "DRAFT"}})
    application = SqlAlchemyJourneyApplication(
        object(), transaction_runner=runner  # type: ignore[arg-type]
    )
    response = await application.create(
        JourneyActor("actor-1", "family-1"),
        "onboarding-1",
        "priority-1",
        "key-1",
        "correlation-1",
    )
    assert response["plan"]["plan_id"] == "plan-1"
    call = runner.calls[0]
    assert call["action"] == "CreateJourneyPlan"
    assert call["event_name"] == "JourneyPlanCreated"
    assert call["idempotency_key"] == "key-1"
    assert call["correlation_id"] == "correlation-1"
    assert call["resource_id"](response) == "plan-1"


async def test_phase_review_keeps_human_decision_in_request_fingerprint() -> None:
    runner = Runner({"plan": {"plan_id": "plan-1"}, "decision": "ADJUST"})
    application = SqlAlchemyJourneyApplication(
        object(), transaction_runner=runner  # type: ignore[arg-type]
    )
    await application.review(
        JourneyActor("actor-1", "family-1"),
        "plan-1",
        PhaseDecision.ADJUST,
        "key-review",
        "correlation-review",
    )
    call = runner.calls[0]
    assert call["request_payload"] == {"plan_id": "plan-1", "decision": "ADJUST"}
    assert call["event_name"] == "JourneyPhaseReviewed"


def test_production_builder_refuses_sqlite_fallback() -> None:
    with pytest.raises(RuntimeError, match="journey_production_requires_postgresql"):
        build_postgres_journey_application("sqlite+aiosqlite:///:memory:")
