"""Fail-closed dispatcher for accepted Human Gate Named Actions.

The dispatcher is an application seam, not a domain implementation.  Each
owning domain registers an explicit handler for a Named Action; unregistered
actions are rejected.  The handler owns authorization, transaction, audit and
business idempotency, while this layer prevents accidental AI-side execution.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from backend.intelligence.human_gate.contracts import NamedActionRequest


class AcceptedActionDispatchError(ValueError):
    """Raised when an accepted request cannot be safely dispatched."""


@dataclass(frozen=True, slots=True)
class ActionExecutionReceipt:
    """Opaque result returned by the owning domain handler."""

    request_id: str
    action_name: str
    status: str = "EXECUTED"
    result_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.request_id or not self.action_name or self.status != "EXECUTED":
            raise AcceptedActionDispatchError("ACTION_RECEIPT_INVALID")


ActionHandler = Callable[[NamedActionRequest], Awaitable[ActionExecutionReceipt]]


class AcceptedNamedActionDispatcher:
    """Dispatch accepted requests only to explicit, domain-owned handlers."""

    def __init__(self, handlers: Mapping[str, ActionHandler] | None = None) -> None:
        self._handlers: dict[str, ActionHandler] = {}
        self._completed: dict[str, ActionExecutionReceipt] = {}
        for action_name, handler in (handlers or {}).items():
            self.register(action_name, handler)

    def register(self, action_name: str, handler: ActionHandler) -> None:
        if not isinstance(action_name, str) or not action_name.strip():
            raise AcceptedActionDispatchError("ACTION_NAME_REQUIRED")
        if not callable(handler):
            raise AcceptedActionDispatchError("ACTION_HANDLER_REQUIRED")
        if action_name in self._handlers:
            raise AcceptedActionDispatchError("ACTION_HANDLER_DUPLICATE")
        self._handlers[action_name] = handler

    async def dispatch(
        self,
        request: NamedActionRequest,
        *,
        tenant_id: str,
        family_id: str | None,
    ) -> ActionExecutionReceipt:
        if not isinstance(request, NamedActionRequest):
            raise AcceptedActionDispatchError("NAMED_ACTION_REQUEST_REQUIRED")
        if request.scope.tenant_id != tenant_id or request.scope.family_id != family_id:
            raise AcceptedActionDispatchError("ACTION_SCOPE_MISMATCH")
        prior = self._completed.get(request.request_id)
        if prior is not None:
            if prior.action_name != request.action_name:
                raise AcceptedActionDispatchError("ACTION_REPLAY_MISMATCH")
            return prior
        handler = self._handlers.get(request.action_name)
        if handler is None:
            raise AcceptedActionDispatchError("ACTION_HANDLER_NOT_REGISTERED")
        receipt = await handler(request)
        if not isinstance(receipt, ActionExecutionReceipt):
            raise AcceptedActionDispatchError("ACTION_HANDLER_RECEIPT_REQUIRED")
        if receipt.request_id != request.request_id or receipt.action_name != request.action_name:
            raise AcceptedActionDispatchError("ACTION_RECEIPT_REQUEST_MISMATCH")
        self._completed[request.request_id] = receipt
        return receipt


__all__ = [
    "AcceptedActionDispatchError",
    "AcceptedNamedActionDispatcher",
    "ActionExecutionReceipt",
    "ActionHandler",
]
