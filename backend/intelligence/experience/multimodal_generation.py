"""Thin Web experience application seam for governed multimodal generation.

The service deliberately stops at ``ModelDraft``.  It does not publish a
recommendation, mutate a family aggregate, or call a provider directly.  A Web
application can use the returned draft to build a ``RecommendationDecision``
after scope/consent checks, while promotion into a business domain remains a
Named Action with a human actor (R8/R9).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.intelligence.model_gateway.contracts import (
    DataClass,
    MediaInput,
    ModelDraft,
    StructuredRequest,
)
from backend.intelligence.model_gateway.gateway import ModelGateway


@dataclass(frozen=True, slots=True)
class MultimodalExperienceCommand:
    """All information needed to start one governed experience run."""

    run_id: str
    provider_id: str
    use_case: str
    prompt_version: str
    schema_version: str
    data_class: DataClass
    context_snapshot_ref: str
    payload: dict[str, Any]
    output_schema: dict[str, Any]
    input_refs: tuple[str, ...] = ()
    media_inputs: tuple[MediaInput, ...] = ()
    session_id: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.run_id,
            self.provider_id,
            self.use_case,
            self.prompt_version,
            self.schema_version,
            self.context_snapshot_ref,
        )
        if not all(required):
            raise ValueError(
                "run_id, provider_id, use_case, prompt_version, schema_version and "
                "context_snapshot_ref are required"
            )
        if not self.output_schema:
            raise ValueError("output_schema is required for a multimodal experience run")
        if any(not ref for ref in self.input_refs):
            raise ValueError("input_refs must contain non-empty references")
        if len(set(self.input_refs)) != len(self.input_refs):
            raise ValueError("input_refs must not contain duplicates")

    def to_structured_request(self) -> StructuredRequest:
        """Build the gateway request without exposing provider details elsewhere."""

        return StructuredRequest(
            use_case=self.use_case,
            prompt_version=self.prompt_version,
            schema_version=self.schema_version,
            data_class=self.data_class,
            payload=dict(self.payload),
            output_schema=dict(self.output_schema),
            context_snapshot_ref=self.context_snapshot_ref,
            input_refs=self.input_refs,
            media_inputs=self.media_inputs,
            request_id=self.run_id,
            session_id=self.session_id,
        )


@dataclass(frozen=True, slots=True)
class MultimodalExperienceDraft:
    """A gateway draft plus the run/media refs needed for Web rendering."""

    run_id: str
    draft: ModelDraft
    media_inputs: tuple[MediaInput, ...]

    @property
    def output(self) -> dict[str, Any]:
        return self.draft.output

    @property
    def requires_human_confirmation(self) -> bool:
        return self.draft.requires_human_confirmation


class MultimodalExperienceService:
    """Generate a structured multimodal draft through the sole Model Gateway."""

    def __init__(self, gateway: ModelGateway) -> None:
        self._gateway = gateway

    async def generate_draft(
        self, command: MultimodalExperienceCommand
    ) -> MultimodalExperienceDraft:
        draft = await self._gateway.generate_structured(
            command.to_structured_request(),
            provider_id=command.provider_id,
        )
        return MultimodalExperienceDraft(
            run_id=command.run_id,
            draft=draft,
            media_inputs=command.media_inputs,
        )


__all__ = [
    "MultimodalExperienceCommand",
    "MultimodalExperienceDraft",
    "MultimodalExperienceService",
]
