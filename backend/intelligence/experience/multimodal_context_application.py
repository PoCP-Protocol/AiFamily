"""Context-bound entry point for the multimodal experience vertical slice.

The caller supplies an explicit ``ContextScope`` and capability request.  This
service creates a short-lived, read-only ContextSnapshot before the request can
reach model routing.  It prevents a screen or adapter from inventing a snapshot
reference and keeps tenant, family, subject, purpose, consent, and deletion
checks on the AI main path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.intelligence.context_engine.async_port import (
    AsyncContextBrokerAdapter,
    AsyncContextBrokerPort,
)
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
from backend.intelligence.experience.run_http import FeedbackPreferenceSnapshot
from backend.intelligence.experience.runs import DurableExperienceRun
from backend.intelligence.model_gateway.contracts import (
    MediaInput,
    ModelReleaseBinding,
    PromptExecutionPlan,
)
from backend.intelligence.model_gateway.provenance import (
    ModelDraftIdentity,
    ModelDraftNotFound,
    ModelDraftRegistryPort,
    ModelDraftScope,
    StoredModelDraft,
)


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
    model_draft_subject_id: str | None = None
    feedback_preferences: FeedbackPreferenceSnapshot | None = None
    snapshot_ttl: timedelta = timedelta(minutes=15)
    release_binding: ModelReleaseBinding | None = None
    prompt_execution_plan: PromptExecutionPlan | None = None

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
        if self.model_draft_subject_id is not None:
            if not self.model_draft_subject_id.strip():
                raise ValueError("model_draft_subject_id must not be blank")
            if self.model_draft_subject_id not in self.scope.subject_ids:
                raise ValueError("model_draft_subject_id must belong to context scope")
        if self.feedback_preferences is not None:
            if not isinstance(self.feedback_preferences, FeedbackPreferenceSnapshot):
                raise ValueError("feedback_preferences must be a FeedbackPreferenceSnapshot")
            feedback_scope = self.feedback_preferences.scope
            if (
                feedback_scope.tenant_id != self.scope.tenant_id
                or feedback_scope.family_id != self.scope.family_id
                or tuple(sorted(feedback_scope.subject_ids))
                != tuple(sorted(self.scope.subject_ids))
            ):
                raise ValueError("feedback_preferences scope must match context scope")


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

    @property
    def draft_id(self) -> str | None:
        return self.routed.experience.draft_id

    @property
    def provenance_ref(self) -> str | None:
        return self.routed.experience.provenance_ref


class ContextBoundMultimodalExperienceService:
    """Build context first, then delegate to the routed Gateway application seam."""

    def __init__(
        self,
        *,
        context: ContextBroker | AsyncContextBrokerPort,
        routed: RoutedMultimodalExperienceService,
        registry: ModelDraftRegistryPort | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if isinstance(context, ContextBroker):
            # Keep the deterministic synchronous broker available to tests and
            # local development without blocking the async application loop.
            self._context: AsyncContextBrokerPort = AsyncContextBrokerAdapter(context)
        elif isinstance(context, AsyncContextBrokerPort):
            self._context = context
        else:
            raise TypeError("context must implement AsyncContextBrokerPort")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._routed = routed
        self._registry = registry
        self._clock = clock or (lambda: datetime.now(UTC))

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
        stored = await self._resolve_existing(command)
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("context clock must return a timezone-aware datetime")
        snapshot = (
            await self._context.read(
                stored.draft.provenance.context_snapshot_ref,
                command.scope,
                now=now,
            )
            if stored is not None
            else await self._context.snapshot(
                scope=command.scope,
                now=now,
                snapshot_ttl=command.snapshot_ttl,
            )
        )
        generation_payload = dict(command.payload)
        # Server-derived aggregate context always wins over caller-provided
        # content at this reserved key, preventing prompt-side forgery.
        if command.feedback_preferences is not None:
            generation_payload["experience_feedback"] = (
                command.feedback_preferences.to_prompt_context()
            )
        generation_command = MultimodalExperienceCommand(
            run_id=command.run_id,
            provider_id="context-router",
            use_case=command.route_request.use_case,
            prompt_version=command.prompt_version,
            schema_version=command.schema_version,
            data_class=command.route_request.data_class,
            context_snapshot_ref=snapshot.snapshot_ref,
            payload=generation_payload,
            output_schema=dict(command.output_schema),
            # A caller may already include an evidence ref that the broker
            # returns in ``source_refs``.  Preserve order while deduplicating so
            # the generation command remains replay-safe and contract-valid.
            input_refs=tuple(dict.fromkeys((*command.input_refs, *snapshot.source_refs))),
            media_inputs=command.media_inputs,
            session_id=command.session_id,
            model_draft_scope=self._draft_scope(command),
            tenant_id=command.scope.tenant_id,
            family_id=command.scope.family_id,
            release_binding=command.release_binding,
            prompt_execution_plan=command.prompt_execution_plan,
        )
        routed = await self._routed.generate_draft(
            generation_command, command.route_request, run=run
        )
        return ContextBoundMultimodalDraft(snapshot=snapshot, routed=routed)

    async def _resolve_existing(
        self, command: ContextBoundMultimodalCommand
    ) -> StoredModelDraft | None:
        """Resolve a prior draft before minting a replacement context snapshot."""

        if self._registry is None:
            return None
        scope = self._draft_scope(command)
        if scope is None:
            raise ValueError(
                "model_draft_scope is required when a ModelDraft registry is configured"
            )
        identity = ModelDraftIdentity.from_run_id(command.run_id)
        try:
            return await self._registry.resolve_stored(
                identity.provenance_ref,
                tenant_id=scope.tenant_id,
                family_id=scope.family_id,
                subject_person_id=scope.subject_person_id,
                purpose=scope.purpose,
                correlation_id=scope.correlation_id,
            )
        except ModelDraftNotFound:
            return None

    @staticmethod
    def _draft_scope(command: ContextBoundMultimodalCommand) -> ModelDraftScope | None:
        """Derive a review/action subject without flattening multi-subject scope."""

        subject_id = command.model_draft_subject_id
        if subject_id is None and len(command.scope.subject_ids) == 1:
            subject_id = command.scope.subject_ids[0]
        if subject_id is None:
            # The generation service raises a precise configuration error only
            # when a registry is actually installed.  Keeping this ``None``
            # preserves direct, non-persisted multimodal contract tests while
            # preventing an application from silently inventing an action
            # subject in a multi-subject context.
            return None
        return ModelDraftScope(
            tenant_id=command.scope.tenant_id,
            family_id=command.scope.family_id,
            subject_person_id=subject_id,
            purpose=command.scope.purpose,
            correlation_id=command.scope.correlation_id,
        )


__all__ = [
    "ContextBoundMultimodalCommand",
    "ContextBoundMultimodalDraft",
    "ContextBoundMultimodalExperienceService",
]
