"""Service-domain adapters for accepted Human Gate Named Actions.

The generic dispatcher deliberately knows nothing about business repositories.
This module is the FGCN composition seam: it registers the one service action
that already has a durable application command and converts its domain result
to the provider-neutral execution receipt.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from backend.intelligence.human_gate.contracts import NamedActionRequest
from backend.intelligence.tool_runtime.accepted_delivery import AcceptedActionDeliveryStore
from backend.intelligence.tool_runtime.accepted_dispatch import (
    AcceptedNamedActionDispatcher,
    ActionExecutionReceipt,
    ActionHandler,
)
from backend.intelligence.tool_runtime.accepted_worker import (
    AcceptedActionGate,
    AcceptedNamedActionWorker,
)
from backend.platform.audit import AuditRecorder

from .admission import DEFAULT_ASYNC_PROVIDER_ADMISSION, AsyncProviderAdmissionQuery
from .application import FGCNAssignmentRepository, execute_task_assignment_named_action
from .blueprint_proposal import (
    FGCNBlueprintProposalHandler,
    ServiceBlueprintProposalStore,
)


@dataclass(slots=True)
class FGCNAcceptedActionHandler:
    """Bind the FGCN assignment command to the accepted-action port.

    The application command remains the owner of actor/scope validation,
    provider admission, audit and transaction semantics.  This adapter only
    supplies those dependencies and returns an opaque receipt; it never calls a
    model provider or performs a second write.
    """

    repo: FGCNAssignmentRepository
    recorder: AuditRecorder
    provider_admission: AsyncProviderAdmissionQuery = DEFAULT_ASYNC_PROVIDER_ADMISSION

    async def __call__(self, request: NamedActionRequest) -> ActionExecutionReceipt:
        assignment = await execute_task_assignment_named_action(
            self.repo,
            request,
            recorder=self.recorder,
            provider_admission=self.provider_admission,
        )
        return ActionExecutionReceipt(
            request_id=request.request_id,
            action_name=request.action_name,
            result_ref=assignment.assignment_id,
        )


def build_fgcn_accepted_action_handlers(
    repo: FGCNAssignmentRepository,
    *,
    recorder: AuditRecorder,
    provider_admission: AsyncProviderAdmissionQuery = DEFAULT_ASYNC_PROVIDER_ADMISSION,
    proposal_store: ServiceBlueprintProposalStore | None = None,
) -> Mapping[str, ActionHandler]:
    """Return explicit service handlers for a dispatcher composition root."""

    handlers: dict[str, ActionHandler] = {
        "CONFIRM_SERVICE_TASK_ASSIGNMENT": FGCNAcceptedActionHandler(
            repo=repo,
            recorder=recorder,
            provider_admission=provider_admission,
        )
    }
    if proposal_store is not None:
        handlers["PROPOSE_SERVICE_BLUEPRINT"] = FGCNBlueprintProposalHandler(
            proposal_store, recorder=recorder
        )
    return handlers


def build_fgcn_accepted_action_worker(
    gate: AcceptedActionGate,
    delivery: AcceptedActionDeliveryStore,
    repo: FGCNAssignmentRepository,
    *,
    recorder: AuditRecorder,
    provider_admission: AsyncProviderAdmissionQuery = DEFAULT_ASYNC_PROVIDER_ADMISSION,
    proposal_store: ServiceBlueprintProposalStore | None = None,
    max_attempts: int = 3,
) -> AcceptedNamedActionWorker:
    """Compose the FGCN handler with the restart-safe accepted-action worker."""

    dispatcher = AcceptedNamedActionDispatcher(
        build_fgcn_accepted_action_handlers(
            repo,
            recorder=recorder,
            provider_admission=provider_admission,
            proposal_store=proposal_store,
        )
    )
    return AcceptedNamedActionWorker(
        gate,
        delivery,
        dispatcher,
        max_attempts=max_attempts,
    )


__all__ = [
    "FGCNAcceptedActionHandler",
    "FGCNBlueprintProposalHandler",
    "build_fgcn_accepted_action_handlers",
    "build_fgcn_accepted_action_worker",
]
