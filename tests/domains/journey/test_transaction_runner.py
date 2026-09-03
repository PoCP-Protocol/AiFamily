from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.domains.journey.application.service import JourneyActor
from backend.domains.journey.domain.errors import JourneyConflictError
from backend.domains.journey.infrastructure.transaction import JourneyTransactionRunner


class Result:
    def __init__(self, row=None):
        self.row = row

    def first(self):
        return self.row


class Connection:
    def __init__(self, claim_row):
        self.claim_row = claim_row
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, statement, parameters):
        sql = str(statement)
        self.calls.append((sql, parameters))
        if "select action_name,request_hash,response_body" in sql:
            row = self.claim_row(parameters, self.calls)
            return Result(row)
        return Result()


class Begin:
    def __init__(self, connection):
        self.connection = connection
        self.exited_with = None

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        self.exited_with = exc_type


class Engine:
    def __init__(self, connection):
        self.context = Begin(connection)

    def begin(self):
        return self.context


def _claim_for_current_request(parameters, calls):
    insert_parameters = calls[0][1]
    return SimpleNamespace(
        action_name=insert_parameters["action"],
        request_hash=insert_parameters["request_hash"],
        response_body=None,
    )


async def test_runner_writes_audit_outbox_and_response_in_one_transaction() -> None:
    connection = Connection(_claim_for_current_request)
    engine = Engine(connection)
    runner = JourneyTransactionRunner(engine)  # type: ignore[arg-type]
    operation_calls = 0

    async def operation(service):
        nonlocal operation_calls
        operation_calls += 1
        return {"plan": {"plan_id": "plan-1", "status": "DRAFT"}}

    response = await runner.execute(
        actor=JourneyActor("actor-1", "family-1"),
        action="CreateJourneyPlan",
        resource_type="JourneyPlan",
        resource_id="plan-1",
        event_name="JourneyPlanCreated",
        idempotency_key="key-1",
        correlation_id="correlation-1",
        request_payload={"onboarding_id": "onboarding-1"},
        operation=operation,
    )
    assert response["plan"]["plan_id"] == "plan-1"
    assert operation_calls == 1
    statements = "\n".join(sql for sql, _parameters in connection.calls)
    assert "insert into idempotency_keys" in statements
    assert "insert into audit_logs" in statements
    assert "insert into outbox_events" in statements
    assert "update idempotency_keys" in statements
    assert engine.context.exited_with is None


async def test_runner_replays_without_executing_domain_operation() -> None:
    expected = {"plan": {"plan_id": "plan-existing"}}

    def replay(parameters, calls):
        insert_parameters = calls[0][1]
        return SimpleNamespace(
            action_name=insert_parameters["action"],
            request_hash=insert_parameters["request_hash"],
            response_body=expected,
        )

    connection = Connection(replay)
    runner = JourneyTransactionRunner(Engine(connection))  # type: ignore[arg-type]

    async def should_not_run(service):
        raise AssertionError("domain operation must not run on replay")

    response = await runner.execute(
        actor=JourneyActor("actor-1", "family-1"),
        action="CreateJourneyPlan",
        resource_type="JourneyPlan",
        resource_id="plan-1",
        event_name="JourneyPlanCreated",
        idempotency_key="key-1",
        correlation_id="correlation-1",
        request_payload={"onboarding_id": "onboarding-1"},
        operation=should_not_run,
    )
    assert response == expected
    assert len(connection.calls) == 2


async def test_runner_rejects_idempotency_key_reused_for_other_request() -> None:
    def conflict(parameters, calls):
        return SimpleNamespace(
            action_name="OtherAction", request_hash="other-hash", response_body=None
        )

    runner = JourneyTransactionRunner(Engine(Connection(conflict)))  # type: ignore[arg-type]
    with pytest.raises(JourneyConflictError, match="idempotency_conflict"):
        await runner.execute(
            actor=JourneyActor("actor-1", "family-1"),
            action="CreateJourneyPlan",
            resource_type="JourneyPlan",
            resource_id="plan-1",
            event_name="JourneyPlanCreated",
            idempotency_key="key-1",
            correlation_id="correlation-1",
            request_payload={"onboarding_id": "different"},
            operation=lambda service: None,  # type: ignore[arg-type]
        )
