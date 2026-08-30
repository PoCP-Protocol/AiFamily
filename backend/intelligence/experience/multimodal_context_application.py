"""Context-bound entry point for the multimodal experience vertical slice.

The caller supplies an explicit ``ContextScope`` and capability request.  This
service creates a short-lived, read-only ContextSnapshot before the request can
reach model routing.  It prevents a screen or adapter from inventing a snapshot
reference and keeps tenant, family, subject, purpose, consent, and deletion
checks on the AI main path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from backend.intelligence.context_engine.contracts import ContextScope, ContextSnapshot
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceDraft,
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import (
    MultimodalExperienceCommand,
)
from backend.intelligence.experience.multimodal_routing import MultimodalRouteRequest
from backend.intelligence.experience.runs import DurableExperienceRun
from backend.intelligence.model_gateway.contracts import MediaInput


@dataclass(frozen=True, slots=True)
class ContextBoundMultimodalCommand:
    """Input for one run; no caller-provided context snapshot reference."""

    run_id: str
    route_request: MultimodalRouteRequest
    scope: ContextScope
    prompt_version: str
    schema_version: str
    payload: dict[str, Any]
    output_schema: dict[str, Any]
    input_refs: tuple[str, ...] = ()
    media_inputs: tuple[MediaInput, ...] = ()
    session_id: str | None = None
    snapshot_ttl: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        required = (self.run_id, self.prompt_version, self.schema_version)
        if not all(required):
            raise ValueError("run_id, prompt_version and schema_version are required")
        if self.route_request.data_class != self.scope.data_class.value:
            raise ValueError("route request data_class must match context scope")
        if self.route_request.use_case != self.scope.purpose:
            raise ValueError("route request use_case must match context purpose")
        if not self.output_schema:
            raise ValueError("output_schema is required")
        if self.snapshot_ttl <= timedelta(0):
            raise ValueError("snapshot_ttl must be positive")


@dataclass(frozen=True, slots=True)
class ContextBoundMultimodalDraft:
    snapshot: ContextSnapshot
    routed: RoutedMultimodalExperienceDraft

    @property
    def run_id(self) -> str:
        return self.routed.run_id

    @property
    def output(self) -> dict[str, object]:
        return self.routed.output

    @property
    def requires_human_confirmation(self) -> bool:
        return self.routed.requires_human_confirmation


class ContextBoundMultimodalExperienceService:
    """Build context first, then delegate to the routed Gateway application seam."""

    def __init__(
        self,
        *,
        context: ContextBroker,
        routed: RoutedMultimodalExperienceService,
    ) -> None:
        self._context = context
        self._routed = routed

    async def generate_draft(
        self,
        command: ContextBoundMultimodalCommand,
        *,
        run: DurableExperienceRun | None = None,
    ) -> ContextBoundMultimodalDraft:
        if run is not None and (
            run.tenant_id != command.scope.tenant_id
            or run.family_id != command.scope.family_id
            or run.subject_ids != command.scope.subject_ids
        ):
            raise ValueError("run scope must match context scope")
        snapshot = self._context.snapshot(
            scope=command.scope,
            now=None,
            snapshot_ttl=command.snapshot_ttl,
        )
        generation_command = MultimodalExperienceCommand(
            run_id=command.run_id,
            provider_id="context-router",
            use_case=command.route_request.use_case,
            prompt_version=command.prompt_version,
            schema_version=command.schema_version,
            data_class=command.route_request.data_class,
            context_snapshot_ref=snapshot.snapshot_ref,
            payload=dict(command.payload),
            output_schema=dict(command.output_schema),
            # A caller may already include an evidence ref that the broker
            # returns in ``source_refs``.  Preserve order while deduplicating so
            # the generation command remains replay-safe and contract-valid.
            input_refs=tuple(dict.fromkeys((*command.input_refs, *snapshot.source_refs))),
            media_inputs=command.media_inputs,
            session_id=command.session_id,
        )
        routed = await self._routed.generate_draft(
            generation_command, command.route_request, run=run
        )
        return ContextBoundMultimodalDraft(snapshot=snapshot, routed=routed)


__all__ = [
    "ContextBoundMultimodalCommand",
    "ContextBoundMultimodalDraft",
    "ContextBoundMultimodalExperienceService",
]
