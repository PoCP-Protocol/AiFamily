from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    DecisionOutcome,
    GateScope,
    GateStatus,
    HumanDecision,
    HumanTask,
    HumanTaskClaim,
    NamedActionRequest,
)
from backend.intelligence.tool_runtime.accepted_delivery import (
    AcceptedActionDelivery,
    AcceptedActionDeliveryStatus,
)
from backend.intelligence.tool_runtime.accepted_dispatch import (
    AcceptedNamedActionDispatcher,
    ActionExecutionReceipt,
)
from backend.intelligence.tool_runtime.accepted_worker import (
    AcceptedActionScheduler,
    AcceptedActionWorkerStatus,
    AcceptedNamedActionWorker,
)
from backend.platform.audit import AuditRecorder

NOW = datetime(2026, 8, 30, 10, tzinfo=UTC)


def _request(action_name: str = "CONFIRM_SERVICE_TASK_ASSIGNMENT") -> NamedActionRequest:
    return NamedActionRequest(
        request_id="request-worker-001",
        action_name=action_name,
        action_arguments={"service_task_id": "task-001"},
        task_id="human-task-001",
        proposal_id="proposal-001",
        decision_id="decision-001",
        actor_id="guardian-001",
        actor_type=ActorType.GUARDIAN,
        scope=GateScope(
            tenant_id="tenant-worker",
            family_id="family-worker",
            subject_ids=("child-worker",),
            purpose="service_collaboration",
            consent_version="consent.v1",
            correlation_id="corr-worker",
        ),
        provenance_ref="human-gate:decision-001",
        idempotency_key="idem-worker-001",
    )


def _task(request: NamedActionRequest) -> HumanTask:
    proposal = ActionProposal(
        proposal_id=request.proposal_id,
        draft_id="draft-worker-001",
        draft_status="DRAFT",
        action_name=request.action_name,
        action_arguments=request.action_arguments,
        scope=request.scope,
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref=request.provenance_ref,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    decision = HumanDecision(
        decision_id=request.decision_id,
        task_id=request.task_id,
        actor_id=request.actor_id,
        actor_type=ActorType.GUARDIAN,
        outcome=DecisionOutcome.ACCEPT,
        reason=None,
        decided_at=NOW,
    )
    return HumanTask(
        task_id=request.task_id,
        proposal=proposal,
        status=GateStatus.DECIDED,
        decision=decision,
        action_request=request,
        created_at=NOW,
    )


class _Gate:
    def __init__(self, task: HumanTask) -> None:
        self.task = task
        self.claims = 0
        self.completions = 0

    async def get(self, task_id: str) -> HumanTask:
        assert task_id == self.task.task_id
        return self.task

    async def claim_accepted(self, task_id: str, *, claim_owner, lease_ttl, recorder, now=None):
        self.claims += 1
        current = now or NOW
        return HumanTaskClaim(
            task=self.task,
            claim_owner=claim_owner,
            claim_expires_at=current + lease_ttl,
        )

    async def complete_claim(self, task_id: str, *, claim_owner, recorder, now=None):
        self.completions += 1
        return self.task

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        return len(recorder.all_events())

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _Queue:
    def __init__(self, *task_ids: str) -> None:
        self.task_ids = task_ids

    async def pending_accepted_task_ids(self, *, limit: int = 100) -> tuple[str, ...]:
        return self.task_ids[:limit]


@dataclass
class _Delivery:
    record: AcceptedActionDelivery | None = None

    async def get(self, request_id: str):
        return self.record

    async def begin_attempt(self, request, *, now=None):
        current = now or NOW
        if self.record is None:
            self.record = AcceptedActionDelivery(
                request_id=request.request_id,
                task_id=request.task_id,
                action_name=request.action_name,
                tenant_id=request.scope.tenant_id,
                family_id=request.scope.family_id,
                attempts=1,
                status=AcceptedActionDeliveryStatus.PENDING,
                last_error=None,
                result_ref=None,
                created_at=current,
                updated_at=current,
            )
        elif self.record.status is AcceptedActionDeliveryStatus.PENDING:
            self.record = replace(
                self.record, attempts=self.record.attempts + 1, updated_at=current
            )
        return self.record

    async def mark_succeeded(self, request, receipt, *, now=None):
        self.record = replace(
            self.record,
            status=AcceptedActionDeliveryStatus.SUCCEEDED,
            result_ref=receipt.result_ref,
            updated_at=now or NOW,
        )
        return self.record

    async def mark_dead_lettered(self, request, *, error, now=None):
        self.record = replace(
            self.record,
            status=AcceptedActionDeliveryStatus.DEAD_LETTERED,
            last_error=error,
            dead_lettered_at=now or NOW,
            updated_at=now or NOW,
        )
        return self.record

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@pytest.mark.asyncio
async def test_worker_claims_dispatches_and_replays_from_durable_receipt() -> None:
    request = _request()
    gate = _Gate(_task(request))
    delivery = _Delivery()
    calls = 0

    async def handler(value):
        nonlocal calls
        calls += 1
        return ActionExecutionReceipt(
            request_id=value.request_id,
            action_name=value.action_name,
            result_ref="assignment-worker-001",
        )

    worker = AcceptedNamedActionWorker(
        gate,
        delivery,
        AcceptedNamedActionDispatcher({request.action_name: handler}),
    )
    first = await worker.consume(request.task_id, claim_owner="worker-a", claimed_at=NOW)
    replay = await worker.consume(
        request.task_id, claim_owner="worker-b", claimed_at=NOW + timedelta(hours=1)
    )

    assert first.status is AcceptedActionWorkerStatus.SUCCEEDED
    assert replay.status is AcceptedActionWorkerStatus.SUCCEEDED
    assert replay.receipt is not None and replay.receipt.result_ref == "assignment-worker-001"
    assert calls == 1
    assert delivery.record is not None and delivery.record.attempts == 1
    assert gate.completions == 2


@pytest.mark.asyncio
async def test_worker_dead_letters_unregistered_action_and_stops_replay() -> None:
    request = _request()
    gate = _Gate(_task(request))
    delivery = _Delivery()
    worker = AcceptedNamedActionWorker(gate, delivery, AcceptedNamedActionDispatcher())

    result = await worker.consume(request.task_id, claim_owner="worker-a", claimed_at=NOW)
    replay = await worker.consume(
        request.task_id, claim_owner="worker-b", claimed_at=NOW + timedelta(hours=1)
    )

    assert result.status is AcceptedActionWorkerStatus.DEAD_LETTERED
    assert replay.status is AcceptedActionWorkerStatus.DEAD_LETTERED
    assert result.error == "ACTION_HANDLER_NOT_REGISTERED"
    assert gate.claims == 1


@pytest.mark.asyncio
async def test_worker_run_once_is_bounded_and_isolates_task_failure() -> None:
    request = _request()
    gate = _Gate(_task(request))
    delivery = _Delivery()
    worker = AcceptedNamedActionWorker(gate, delivery, AcceptedNamedActionDispatcher())

    report = await worker.run_once(
        _Queue(request.task_id, "missing-task"), claim_owner="worker-a", limit=2, claimed_at=NOW
    )

    assert report.pulled == 2
    assert report.dead_lettered == 1
    assert report.retried == 1
    assert report.succeeded == 0


@pytest.mark.asyncio
async def test_scheduler_stops_after_terminal_pass() -> None:
    request = _request()
    gate = _Gate(_task(request))
    delivery = _Delivery()

    async def handler(value):
        return ActionExecutionReceipt(
            request_id=value.request_id,
            action_name=value.action_name,
            result_ref="assignment-scheduled",
        )

    worker = AcceptedNamedActionWorker(
        gate,
        delivery,
        AcceptedNamedActionDispatcher({request.action_name: handler}),
    )
    scheduler = AcceptedActionScheduler(worker, _Queue(request.task_id))

    report = await scheduler.run_until_idle(
        claim_owner="worker-a", max_polls=5, claimed_at=NOW
    )

    assert len(report.passes) == 1
    assert report.pulled == 1
    assert report.succeeded == 1
    assert report.retried == 0
