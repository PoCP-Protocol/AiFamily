"""Model Gateway adapter for the provider-neutral Agent Runtime port."""

from __future__ import annotations

from dataclasses import dataclass

from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest
from backend.intelligence.model_gateway.gateway import ModelGateway


@dataclass(frozen=True, slots=True)
class ModelGatewayExecutionPort:
    """Bind one governed provider to ``AgentExecutionPort``.

    Agent Runtime deliberately has no provider identifier in ``AgentTask``:
    provider selection is a composition-root concern.  This adapter makes that
    choice explicit while preserving the single Model Gateway and its safety,
    admission, timeout and provenance checks.
    """

    gateway: ModelGateway
    provider_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.gateway, ModelGateway):
            raise TypeError("gateway must be a ModelGateway")
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ValueError("provider_id is required")
        if self.provider_id not in self.gateway.available_provider_ids():
            raise ValueError("provider_id must be wired in the Model Gateway")

    async def generate_structured(self, request: StructuredRequest) -> ModelDraft:
        return await self.gateway.generate_structured(request, provider_id=self.provider_id)


__all__ = ["ModelGatewayExecutionPort"]
