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

from backend.intelligence.experience.runs import DurableExperienceRun, RunState
from backend.intelligence.model_gateway.contracts import (
    DataClass,
    MediaInput,
    ModelDraft,
    StructuredRequest,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import (
    ModelDraftIdentity,
    ModelDraftNotFound,
    ModelDraftRegistryError,
    ModelDraftRegistryPort,
    ModelDraftScope,
    StoredModelDraft,
)


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
    model_draft_scope: ModelDraftScope | None = None

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
        if self.model_draft_scope is not None and not isinstance(
            self.model_draft_scope, ModelDraftScope
        ):
            raise ValueError("model_draft_scope must be a ModelDraftScope")

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
    draft_id: str | None = None
    provenance_ref: str | None = None

    @property
    def output(self) -> dict[str, Any]:
        return self.draft.output

    @property
    def requires_human_confirmation(self) -> bool:
        return self.draft.requires_human_confirmation


class MultimodalExperienceService:
    """Generate a structured multimodal draft through the sole Model Gateway."""

    def __init__(
        self,
        gateway: ModelGateway,
        *,
        registry: ModelDraftRegistryPort | None = None,
    ) -> None:
        self._gateway = gateway
        self._registry = registry

    async def generate_draft(
        self,
        command: MultimodalExperienceCommand,
        *,
        run: DurableExperienceRun | None = None,
    ) -> MultimodalExperienceDraft:
        identity: ModelDraftIdentity | None = None
        if self._registry is not None:
            if command.model_draft_scope is None:
                raise ValueError(
                    "model_draft_scope is required when a ModelDraft registry is configured"
                )
            identity = ModelDraftIdentity.from_run_id(command.run_id)

        if run is not None:
            if run.run_id != command.run_id:
                raise ValueError("run_id does not match the experience command")
            if run.state is RunState.QUEUED:
                run.transition(RunState.RUNNING, event_id=f"{run.run_id}:started")
        stored: StoredModelDraft | None = None
        try:
            if self._registry is not None and identity is not None:
                stored = await self._resolve_existing(command, identity)
            if stored is None:
                draft = await self._gateway.generate_structured(
                    command.to_structured_request(),
                    provider_id=command.provider_id,
                )
                if self._registry is not None and identity is not None:
                    stored = await self._registry.save(
                        draft_id=identity.draft_id,
                        provenance_ref=identity.provenance_ref,
                        scope=command.model_draft_scope,
                        draft=draft,
                    )
            else:
                draft = stored.draft
        except Exception:
            if run is not None and run.state is RunState.RUNNING:
                run.transition(RunState.FAILED, event_id=f"{run.run_id}:failed")
            raise

        if run is not None:
            run.checkpoint(
                checkpoint_id=f"{run.run_id}:draft",
                payload=(
                    {
                        "draft_id": stored.draft_id,
                        "provenance_ref": stored.provenance_ref,
                        "status": "DRAFT",
                    }
                    if stored is not None
                    else {}
                ),
                artifact_refs=tuple(
                    f"media:sha256:{media.sha256}" for media in command.media_inputs
                ),
                draft_payload=draft.output,
            )
            run.transition(RunState.SUCCEEDED, event_id=f"{run.run_id}:succeeded")
        return MultimodalExperienceDraft(
            run_id=command.run_id,
            draft=draft,
            media_inputs=command.media_inputs,
            draft_id=stored.draft_id if stored is not None else None,
            provenance_ref=stored.provenance_ref if stored is not None else None,
        )

    async def _resolve_existing(
        self,
        command: MultimodalExperienceCommand,
        identity: ModelDraftIdentity,
    ) -> StoredModelDraft | None:
        if self._registry is None:
            return None
        scope = command.model_draft_scope
        if scope is None:
            raise ValueError(
                "model_draft_scope is required when a ModelDraft registry is configured"
            )
        try:
            stored = await self._registry.resolve_stored(
                identity.provenance_ref,
                tenant_id=scope.tenant_id,
                family_id=scope.family_id,
                subject_person_id=scope.subject_person_id,
                purpose=scope.purpose,
                correlation_id=scope.correlation_id,
            )
        except ModelDraftNotFound:
            return None

        provenance = stored.draft.provenance
        expected = (
            command.provider_id,
            command.use_case,
            command.prompt_version,
            command.schema_version,
            command.data_class,
            command.context_snapshot_ref,
        )
        actual = (
            provenance.provider_id,
            provenance.use_case,
            provenance.prompt_version,
            provenance.schema_version,
            provenance.data_class,
            provenance.context_snapshot_ref,
        )
        if actual != expected:
            raise ModelDraftRegistryError("MODEL_DRAFT_REPLAY_MISMATCH")
        return stored


__all__ = [
    "MultimodalExperienceCommand",
    "MultimodalExperienceDraft",
    "MultimodalExperienceService",
]
