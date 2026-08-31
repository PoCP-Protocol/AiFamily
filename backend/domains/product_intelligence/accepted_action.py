"""Product Intelligence handler for accepted Human Gate Named Actions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from backend.intelligence.human_gate.contracts import NamedActionRequest
from backend.intelligence.tool_runtime.accepted_dispatch import (
    ActionExecutionReceipt,
    ActionHandler,
)
from backend.intelligence.tool_runtime.accepted_worker import PermanentAcceptedActionError
from backend.platform.audit import AuditRecorder

from .application.product_definition_adoption import (
    ADOPT_PRODUCT_DEFINITION_ACTION,
    ProductDefinitionAdoptionAuthorizer,
    ProductDefinitionAdoptionRepository,
    execute_product_definition_named_action,
)
from .domain.errors import ProductIntelligenceDomainError


@dataclass(frozen=True, slots=True)
class ProductDefinitionAcceptedActionHandler:
    repo: ProductDefinitionAdoptionRepository
    authorizer: ProductDefinitionAdoptionAuthorizer
    recorder_factory: Callable[[], AuditRecorder] = AuditRecorder

    async def __call__(self, request: NamedActionRequest) -> ActionExecutionReceipt:
        try:
            definition, _ = await execute_product_definition_named_action(
                self.repo,
                request,
                human_actor_authorizer=self.authorizer,
                recorder=self.recorder_factory(),
            )
        except ProductIntelligenceDomainError as exc:
            raise PermanentAcceptedActionError(exc.code) from exc
        return ActionExecutionReceipt(
            request_id=request.request_id,
            action_name=request.action_name,
            result_ref=definition.id,
        )


def build_product_definition_accepted_action_handlers(
    repo: ProductDefinitionAdoptionRepository,
    *,
    authorizer: ProductDefinitionAdoptionAuthorizer,
    recorder_factory: Callable[[], AuditRecorder] = AuditRecorder,
) -> Mapping[str, ActionHandler]:
    """Return the one explicitly registered PDM mutation handler."""

    return {
        ADOPT_PRODUCT_DEFINITION_ACTION: ProductDefinitionAcceptedActionHandler(
            repo=repo,
            authorizer=authorizer,
            recorder_factory=recorder_factory,
        )
    }


__all__ = [
    "ProductDefinitionAcceptedActionHandler",
    "build_product_definition_accepted_action_handlers",
]
