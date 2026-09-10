"""Narrow Knowledge -> Model Gateway runtime seam.

This adapter is intentionally not a second agent runtime.  It retrieves only
published, in-scope claims from :class:`KnowledgeRegistry`, binds their refs to
one structured gateway request, and returns the gateway's non-mutating
``ModelDraft``.  No domain fact or canonical plan is written here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.intelligence.model_gateway.contracts import (
    DataClass,
    ModelDraft,
    PromptExecutionPlan,
    StructuredRequest,
)
from backend.intelligence.model_gateway.gateway import ModelGateway

from .contracts import KnowledgeClaim
from .registry import KnowledgeRegistry


class KnowledgeRuntimeError(RuntimeError):
    """Knowledge admission failed closed before model invocation."""


@dataclass(frozen=True, slots=True)
class KnowledgeContext:
    tenant_id: str
    family_id: str
    purpose: str
    scope: str
    context_snapshot_ref: str
    data_class: DataClass
    correlation_id: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.tenant_id,
                self.family_id,
                self.purpose,
                self.scope,
                self.context_snapshot_ref,
                self.correlation_id,
            )
        ):
            raise ValueError("knowledge context identity is required")


@dataclass(frozen=True, slots=True)
class KnowledgeDraftRequest:
    context: KnowledgeContext
    provider_id: str
    prompt_version: str
    schema_version: str
    payload: dict[str, Any]
    output_schema: dict[str, Any]
    prompt_execution_plan: PromptExecutionPlan
    minimum_evidence: Any = None
    establishing_only: bool = False
    at: datetime | None = None


class KnowledgeDraftRuntime:
    """Retrieve governed knowledge, then call the one Model Gateway."""

    def __init__(self, registry: KnowledgeRegistry, gateway: ModelGateway) -> None:
        self._registry = registry
        self._gateway = gateway

    async def generate_draft(self, request: KnowledgeDraftRequest) -> ModelDraft:
        claims: tuple[KnowledgeClaim, ...] = self._registry.retrieve_reviewed(
            purpose=request.context.purpose,
            scope=request.context.scope,
            minimum_evidence=request.minimum_evidence,
            establishing_only=request.establishing_only,
            at=request.at,
        )
        if not claims:
            raise KnowledgeRuntimeError("KNOWLEDGE_NOT_AVAILABLE")
        knowledge_refs = tuple(claim.claim_id for claim in claims)
        knowledge_materials = tuple(
            {
                "claim_id": claim.claim_id,
                "text": claim.text,
                "source_id": claim.source_id,
                "evidence_level": claim.provenance.level,
                "expires_at": claim.expires_at.isoformat() if claim.expires_at else None,
            }
            for claim in claims
        )
        payload = dict(request.payload)
        payload["knowledge_claim_refs"] = knowledge_refs
        payload["knowledge_claims"] = knowledge_materials
        structured = StructuredRequest(
            use_case=request.context.purpose,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
            data_class=request.context.data_class,
            payload=payload,
            output_schema=dict(request.output_schema),
            context_snapshot_ref=request.context.context_snapshot_ref,
            request_id=request.context.correlation_id,
            tenant_id=request.context.tenant_id,
            family_id=request.context.family_id,
            prompt_execution_plan=request.prompt_execution_plan,
        )
        draft = await self._gateway.generate_structured(
            structured,
            provider_id=request.provider_id,
        )
        if draft.status != "DRAFT" or draft.may_mutate_business_state:
            raise KnowledgeRuntimeError("KNOWLEDGE_DRAFT_BOUNDARY_INVALID")
        return draft


__all__ = [
    "KnowledgeContext",
    "KnowledgeDraftRequest",
    "KnowledgeDraftRuntime",
    "KnowledgeRuntimeError",
]
