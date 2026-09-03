from __future__ import annotations

import pytest

from backend.intelligence.human_gate.contracts import (
    ActorType,
    GateScope,
    NamedActionRequest,
)
from backend.intelligence.tool_runtime.accepted_dispatch import (
    AcceptedActionDispatchError,
    AcceptedNamedActionDispatcher,
    ActionExecutionReceipt,
)


def _request(action_name: str = "PROPOSE_SERVICE_BLUEPRINT") -> NamedActionRequest:
    return NamedActionRequest(
        request_id="request-dispatch-001",
        action_name=action_name,
        action_arguments={"blueprint_ref": "blueprint:v1"},
        task_id="task-001",
        proposal_id="proposal-001",
        decision_id="decision-001",
        actor_id="guardian-001",
        actor_type=ActorType.GUARDIAN,
        scope=GateScope(
            tenant_id="tenant-dispatch",
            family_id="family-dispatch",
            subject_ids=("child-dispatch",),
            purpose="growth_support",
            consent_version="consent.v1",
            correlation_id="corr-dispatch",
        ),
        provenance_ref="prov:dispatch",
        idempotency_key="idem:dispatch-001",
    )


@pytest.mark.asyncio
async def test_dispatches_only_registered_handler_and_replays_idempotently() -> None:
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return ActionExecutionReceipt(
            request_id=request.request_id,
            action_name=request.action_name,
        )

    dispatcher = AcceptedNamedActionDispatcher({"PROPOSE_SERVICE_BLUEPRINT": handler})
    request = _request()
    first = await dispatcher.dispatch(
        request,
        tenant_id="tenant-dispatch",
        family_id="family-dispatch",
    )
    replay = await dispatcher.dispatch(
        request,
        tenant_id="tenant-dispatch",
        family_id="family-dispatch",
    )
    assert first == replay
    assert calls == 1


@pytest.mark.asyncio
async def test_unregistered_and_cross_scope_actions_fail_closed() -> None:
    dispatcher = AcceptedNamedActionDispatcher()
    with pytest.raises(AcceptedActionDispatchError, match="ACTION_HANDLER_NOT_REGISTERED"):
        await dispatcher.dispatch(
            _request(), tenant_id="tenant-dispatch", family_id="family-dispatch"
        )
    with pytest.raises(AcceptedActionDispatchError, match="ACTION_SCOPE_MISMATCH"):
        await dispatcher.dispatch(
            _request(), tenant_id="tenant-other", family_id="family-dispatch"
        )


@pytest.mark.asyncio
async def test_handler_receipt_must_bind_to_request() -> None:
    async def wrong_handler(request):
        return ActionExecutionReceipt(request_id="other", action_name=request.action_name)

    dispatcher = AcceptedNamedActionDispatcher({"PROPOSE_SERVICE_BLUEPRINT": wrong_handler})
    with pytest.raises(AcceptedActionDispatchError, match="ACTION_RECEIPT_REQUEST_MISMATCH"):
        await dispatcher.dispatch(
            _request(), tenant_id="tenant-dispatch", family_id="family-dispatch"
        )
