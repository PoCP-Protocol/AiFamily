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
    ModelReleaseBinding,
    PromptExecutionPlan,
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
from backend.intelligence.model_gateway.routing import RoutingModelGateway


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
    tenant_id: str | None = None
    family_id: str | None = None
    release_binding: ModelReleaseBinding | None = None
    prompt_execution_plan: PromptExecutionPlan | None = None

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
        if (self.tenant_id is None) != (self.family_id is None):
            raise ValueError("tenant_id and family_id must be supplied together")

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
            tenant_id=(
                self.tenant_id
                if self.tenant_id is not None
                else self.model_draft_scope.tenant_id
                if self.model_draft_scope
                else None
            ),
            family_id=(
                self.family_id
                if self.family_id is not None
                else self.model_draft_scope.family_id
                if self.model_draft_scope
                else None
            ),
            release_binding=self.release_binding,
            prompt_execution_plan=self.prompt_execution_plan,
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
        fallback_provider_ids: tuple[str, ...] = (),
    ) -> MultimodalExperienceDraft:
        provider_order = _provider_order(command.provider_id, fallback_provider_ids)
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
                stored = await self._resolve_existing(command, identity, provider_order)
            if stored is None:
                request = command.to_structured_request()
                if len(provider_order) == 1:
                    draft = await self._gateway.generate_structured(
                        request,
                        provider_id=command.provider_id,
                    )
                else:
                    draft = await RoutingModelGateway(
                        self._gateway, provider_order
                    ).generate_structured(request)
                if self._registry is not None and identity is not None:
                    # ``save`` only flushes.  The composition root owns the
                    # session and decides when the surrounding transaction
                    # commits.  This keeps model invocation independent from
                    # persistence and allows a future run store, audit sink
                    # and registry to commit atomically in one UnitOfWork.
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
        provider_order: tuple[str, ...],
    ) -> StoredModelDraft | None:
        """Read an idempotent draft before invoking a provider.

        A provider call is an external side effect and may produce a different
        timestamp, latency or answer on every attempt.  Replaying the same
        ``run_id`` must therefore resolve the stored draft first.  A found
        record is accepted only when the immutable generation contract still
        matches; a changed request fails closed instead of silently reusing a
        result under a new prompt or context snapshot.
        """

        if self._registry is None:
            return None
        scope = command.model_draft_scope
        if scope is None:  # guarded by generate_draft, kept explicit for typing
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
            command.use_case,
            command.prompt_version,
            command.schema_version,
            command.data_class,
            command.context_snapshot_ref,
        )
        actual = (
            provenance.use_case,
            provenance.prompt_version,
            provenance.schema_version,
            provenance.data_class,
            provenance.context_snapshot_ref,
        )
        release_matches = command.release_binding is None and provenance.release_set_id is None
        if command.release_binding is not None:
            release_matches = (
                provenance.release_set_id == command.release_binding.release_set_id
                and provenance.bundle_id
                == command.release_binding.bundle_id_for(provenance.provider_id)
                and provenance.deployment_receipt_id
                == command.release_binding.deployment_receipt_id
                and provenance.runtime_config_digest
                == command.release_binding.runtime_config_digest
                and provenance.deployment_sequence
                == command.release_binding.deployment_sequence
                and provenance.control_id == command.release_binding.control_id
                and provenance.fence_claim_id is not None
            )
        if (
            provenance.provider_id not in provider_order
            or actual != expected
            or not release_matches
        ):
            raise ModelDraftRegistryError("MODEL_DRAFT_REPLAY_MISMATCH")
        return stored


def _provider_order(
    primary_provider_id: str,
    fallback_provider_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if not isinstance(fallback_provider_ids, tuple) or any(
        not isinstance(provider_id, str) or not provider_id.strip()
        for provider_id in fallback_provider_ids
    ):
        raise ValueError("fallback_provider_ids must contain non-empty provider ids")
    order = (primary_provider_id, *fallback_provider_ids)
    if len(set(order)) != len(order):
        raise ValueError("provider route must not contain duplicate provider ids")
    return order


__all__ = [
    "MultimodalExperienceCommand",
    "MultimodalExperienceDraft",
    "MultimodalExperienceService",
]
