from types import SimpleNamespace

import pytest

from backend.domains.service.fgcn.accepted_action import (
    FGCNAcceptedActionHandler,
    build_fgcn_accepted_action_handlers,
    build_fgcn_accepted_action_worker,
)
from backend.intelligence.human_gate.contracts import ActorType, GateScope, NamedActionRequest
from backend.intelligence.tool_runtime.accepted_dispatch import (
    AcceptedNamedActionDispatcher,
)
from backend.intelligence.tool_runtime.accepted_worker import AcceptedNamedActionWorker
from backend.platform.audit import AuditRecorder


def _request() -> NamedActionRequest:
    return NamedActionRequest(
        request_id="request-fgcn-001",
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments={"service_task_id": "task-001", "provider_id": "expert-001"},
        task_id="human-task-001",
        proposal_id="proposal-001",
        decision_id="decision-001",
        actor_id="guardian-001",
        actor_type=ActorType.GUARDIAN,
        scope=GateScope(
            tenant_id="tenant-fgcn",
            family_id="family-fgcn",
            subject_ids=("child-fgcn",),
            purpose="service_collaboration",
            consent_version="consent.v1",
            correlation_id="corr-fgcn",
        ),
        provenance_ref="human-gate:decision-001",
        idempotency_key="idem-fgcn-001",
    )


@pytest.mark.asyncio
async def test_fgcn_handler_adapts_durable_assignment_command(monkeypatch) -> None:
    calls: list[tuple[object, object, object, object]] = []

    async def fake_execute(repo, request, *, recorder, provider_admission):
        calls.append((repo, request, recorder, provider_admission))
        return SimpleNamespace(assignment_id="assignment-001")

    import backend.domains.service.fgcn.accepted_action as module

    monkeypatch.setattr(module, "execute_task_assignment_named_action", fake_execute)
    repo = object()
    recorder = AuditRecorder()
    admission = object()
    handler = FGCNAcceptedActionHandler(repo, recorder, admission)

    receipt = await handler(_request())

    assert receipt.request_id == "request-fgcn-001"
    assert receipt.action_name == "CONFIRM_SERVICE_TASK_ASSIGNMENT"
    assert receipt.result_ref == "assignment-001"
    assert calls == [(repo, _request(), recorder, admission)]


@pytest.mark.asyncio
async def test_fgcn_factory_composes_with_accepted_dispatcher(monkeypatch) -> None:
    async def fake_execute(repo, request, *, recorder, provider_admission):
        return SimpleNamespace(assignment_id="assignment-dispatched")

    import backend.domains.service.fgcn.accepted_action as module

    monkeypatch.setattr(module, "execute_task_assignment_named_action", fake_execute)
    request = _request()
    dispatcher = AcceptedNamedActionDispatcher(
        build_fgcn_accepted_action_handlers(object(), recorder=AuditRecorder())
    )

    receipt = await dispatcher.dispatch(
        request,
        tenant_id="tenant-fgcn",
        family_id="family-fgcn",
    )

    assert receipt.result_ref == "assignment-dispatched"


def test_fgcn_worker_factory_registers_domain_handler() -> None:
    worker = build_fgcn_accepted_action_worker(
        object(), object(), object(), recorder=AuditRecorder()
    )
    assert isinstance(worker, AcceptedNamedActionWorker)
