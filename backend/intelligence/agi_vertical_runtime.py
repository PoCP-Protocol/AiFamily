"""Evaluation-only vertical family-growth runtime prototype.

This module is deliberately isolated from domain repositories.  It consumes the
existing ModelGateway port and produces an evaluation ledger record; it never
mutates FamilyNeed, CanonicalFact, service, commerce, or achievement state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from backend.intelligence.capability_registry.contracts import CapabilityOffer
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.model_gateway.contracts import (
    KnowledgeExecutionPayload,
    MediaInput,
    ModelDraft,
    PromptExecutionPlan,
    StructuredRequest,
)


class VerticalRuntimeError(RuntimeError):
    """Fail-closed error for missing scope, consent, knowledge, or gateway output."""


@dataclass(frozen=True, slots=True)
class FamilyGrowthContext:
    tenant_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    purpose: str
    consent_version: str
    context_snapshot_ref: str
    values: dict[str, Any]

    @property
    def snapshot_hash(self) -> str:
        encoded = json.dumps(self.values, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()

    def __post_init__(self) -> None:
        if not all(
            (
                self.tenant_id,
                self.family_id,
                self.purpose,
                self.consent_version,
                self.context_snapshot_ref,
            )
        ):
            raise VerticalRuntimeError("CONTEXT_SCOPE_REQUIRED")
        if not self.subject_ids:
            raise VerticalRuntimeError("CONTEXT_SUBJECT_REQUIRED")


@dataclass(frozen=True, slots=True)
class PublishedKnowledge:
    ref: str
    version: str
    source: str
    applicability: str
    digest: str
    content: str
    status: str = "PUBLISHED"

    def __post_init__(self) -> None:
        if self.status != "PUBLISHED" or not all(
            (self.ref, self.version, self.source, self.applicability, self.digest, self.content)
        ):
            raise VerticalRuntimeError("KNOWLEDGE_NOT_PUBLISHED")


class ContextPort(Protocol):
    async def read(self, *, family_id: str, context_snapshot_ref: str) -> FamilyGrowthContext: ...


class KnowledgePort(Protocol):
    async def published(self, *, ref: str) -> PublishedKnowledge | None: ...


class CapabilityPort(Protocol):
    """Read-only supply catalogue used to ground path candidates."""

    def retrieve_published(
        self,
        *,
        purpose: str,
        scope: str,
        need_type: str | None = None,
        required_keys: tuple[str, ...] = (),
    ) -> tuple[CapabilityOffer, ...]: ...


class RegistryKnowledgePort:
    """Expose only an in-scope published claim to the vertical runtime.

    The vertical pipeline must ground generation in the canonical Knowledge
    Registry rather than a development fixture.  This adapter deliberately
    resolves one claim by id and rechecks publication, source verification,
    purpose, scope and expiry through ``retrieve_reviewed``.
    """

    def __init__(self, registry: KnowledgeRegistry, *, purpose: str, scope: str) -> None:
        if not purpose.strip() or not scope.strip():
            raise ValueError("knowledge adapter purpose and scope are required")
        self._registry = registry
        self._purpose = purpose
        self._scope = scope

    async def published(self, *, ref: str) -> PublishedKnowledge | None:
        claims = self._registry.retrieve_reviewed(
            purpose=self._purpose,
            scope=self._scope,
        )
        claim = next((item for item in claims if item.claim_id == ref), None)
        if claim is None:
            return None
        digest = hashlib.sha256(claim.text.encode("utf-8")).hexdigest()
        return PublishedKnowledge(
            ref=claim.claim_id,
            version=str(claim.metadata.get("version", "1")),
            source=claim.source_id,
            applicability=claim.scope,
            digest=digest,
            content=claim.text,
        )


class FeedbackPort(Protocol):
    async def latest(self, *, family_need_id: str) -> tuple[str, ...]: ...


class ModelGatewayPort(Protocol):
    async def generate_structured(
        self, request: StructuredRequest, *, provider_id: str | None = None
    ) -> ModelDraft: ...


@dataclass(frozen=True, slots=True)
class GuardianDecision:
    decision_ref: str
    family_need_id: str
    run_id: str
    path_id: str
    state: str
    edits: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in {"ACCEPT", "REJECT", "EDIT", "DEFER"}:
            raise VerticalRuntimeError("GUARDIAN_DECISION_INVALID")
        if not all((self.decision_ref, self.family_need_id, self.run_id, self.path_id)):
            raise VerticalRuntimeError("GUARDIAN_DECISION_CORRELATION_REQUIRED")
        allowed = {"next_step", "path", "focus", "questions"}
        if any(key not in allowed for key in self.edits):
            raise VerticalRuntimeError("GUARDIAN_CALIBRATION_FIELD_INVALID")
        for key, value in self.edits.items():
            if key in {"next_step", "focus"}:
                if not isinstance(value, str) or not value.strip() or len(value) > 2000:
                    raise VerticalRuntimeError("GUARDIAN_CALIBRATION_TEXT_INVALID")
            elif (
                not isinstance(value, list)
                or len(value) > 20
                or any(
                    not isinstance(item, str) or not item.strip() or len(item) > 500
                    for item in value
                )
            ):
                raise VerticalRuntimeError("GUARDIAN_CALIBRATION_LIST_INVALID")


@dataclass(frozen=True, slots=True)
class EvaluationLedgerEntry:
    family_need_id: str
    path_id: str
    run_id: str
    context_snapshot_ref: str
    draft: ModelDraft
    feedback_refs: tuple[str, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    guardian_calibration: dict[str, Any] | None = None
    capability_refs: tuple[str, ...] = ()


class EvaluationLedger:
    """Process-local experiment store; never a canonical business ledger."""

    def __init__(self) -> None:
        self._entries: dict[str, EvaluationLedgerEntry] = {}
        self._decisions: dict[str, GuardianDecision] = {}

    def append(self, entry: EvaluationLedgerEntry) -> None:
        if entry.run_id in self._entries:
            raise VerticalRuntimeError("RUN_ID_REPLAY_COLLISION")
        self._entries[entry.run_id] = entry

    def decision(self, value: GuardianDecision) -> None:
        self._decisions[value.decision_ref] = value

    def read(self, run_id: str) -> EvaluationLedgerEntry:
        try:
            return self._entries[run_id]
        except KeyError as exc:
            raise VerticalRuntimeError("EVALUATION_ENTRY_NOT_FOUND") from exc

    def replay(self, run_id: str) -> EvaluationLedgerEntry:
        """Read-only replay; it never calls a gateway or appends an event."""
        return self.read(run_id)

    def delete(self, run_id: str) -> str:
        """Delete an experiment entry and return a deletion proof reference."""
        if run_id not in self._entries:
            raise VerticalRuntimeError("EVALUATION_ENTRY_NOT_FOUND")
        del self._entries[run_id]
        return f"deletion:{run_id}"


class VerticalFamilyGrowthRuntime:
    """UNDERSTAND → CLARIFY → DESIGN_PATH → PROPOSE_ACTION draft pipeline."""

    def __init__(
        self,
        *,
        gateway: ModelGatewayPort,
        context: ContextPort,
        knowledge: KnowledgePort,
        feedback: FeedbackPort,
        ledger: EvaluationLedger,
        capabilities: CapabilityPort | None = None,
    ) -> None:
        self._gateway = gateway
        self._context = context
        self._knowledge = knowledge
        self._feedback = feedback
        self._ledger = ledger
        self._capabilities = capabilities

    async def run(
        self,
        *,
        family_need_id: str,
        path_id: str,
        run_id: str,
        family_id: str,
        knowledge_ref: str,
        provider_id: str | None = None,
        guardian_decision: GuardianDecision | None = None,
        media_inputs: tuple[MediaInput, ...] = (),
    ) -> EvaluationLedgerEntry:
        context = await self._context.read(
            family_id=family_id, context_snapshot_ref=f"context:{run_id}"
        )
        if context.family_id != family_id:
            raise VerticalRuntimeError("CONTEXT_SCOPE_MISMATCH")
        material = await self._knowledge.published(ref=knowledge_ref)
        if material is None:
            raise VerticalRuntimeError("KNOWLEDGE_NOT_PUBLISHED")
        feedback_refs = await self._feedback.latest(family_need_id=family_need_id)
        capability_candidates: tuple[dict[str, Any], ...] = ()
        if self._capabilities is not None:
            values = context.values
            need_type = values.get("need_type")
            if not isinstance(need_type, str):
                need_type = None
            raw_keys = values.get("required_capability_keys", ())
            required_keys = (
                tuple(key for key in raw_keys if isinstance(key, str) and key.strip())
                if isinstance(raw_keys, (list, tuple))
                else ()
            )
            offers = self._capabilities.retrieve_published(
                purpose="growth_path_design",
                scope="family_growth",
                need_type=need_type,
                required_keys=required_keys,
            )
            # Keep candidates supply-side and bounded; no family identifiers or
            # activation state are copied into the model payload.
            capability_candidates = tuple(
                {
                    "capability_ref": offer.capability_ref,
                    "version": offer.version,
                    "title": offer.title,
                    "description": offer.description,
                    "delivery_kind": offer.delivery_kind,
                }
                for offer in offers
            )
            if not capability_candidates:
                raise VerticalRuntimeError("NO_PUBLISHED_CAPABILITY_CANDIDATES")
        capability_refs = tuple(
            f"{candidate['capability_ref']}@{candidate['version']}"
            for candidate in capability_candidates
        )
        calibration: dict[str, Any] | None = None
        if guardian_decision is not None:
            if guardian_decision.family_need_id != family_need_id:
                raise VerticalRuntimeError("GUARDIAN_DECISION_SCOPE_MISMATCH")
            self._ledger.decision(guardian_decision)
            feedback_refs = (*feedback_refs, guardian_decision.decision_ref)
            # A reference alone is not a learning signal: the next model run
            # must receive the guardian's bounded correction.  Keep this as
            # explicit calibration metadata rather than merging it into the
            # family context, because AI output and guardian intent are
            # different semantic layers (R9).
            calibration = {
                "decision_ref": guardian_decision.decision_ref,
                "state": guardian_decision.state,
                "edits": dict(guardian_decision.edits),
            }
        request = StructuredRequest(
            use_case="vertical_family_growth",
            prompt_version="vertical-growth.v1",
            schema_version="vertical-growth-draft.v1",
            data_class="MINOR_PERSONAL_DATA",
            payload={
                "family_need_id": family_need_id,
                "path_id": path_id,
                "context": context.values,
                "feedback_refs": feedback_refs,
                "guardian_calibration": calibration,
                "capability_candidates": capability_candidates,
            },
            output_schema={
                "type": "object",
                "required": ["understanding", "next_step", "path"],
                "properties": {
                    "understanding": {"type": "string"},
                    "next_step": {"type": "string"},
                    "path": {"type": "array"},
                },
            },
            context_snapshot_ref=context.context_snapshot_ref,
            input_refs=(family_need_id, path_id, *feedback_refs, *capability_refs),
            media_inputs=media_inputs,
            request_id=run_id,
            tenant_id=context.tenant_id,
            family_id=context.family_id,
            prompt_execution_plan=PromptExecutionPlan(
                prompt_ref="vertical-family-growth",
                prompt_version="vertical-growth.v1",
                template="Generate a draft only.",
                system_policy_ref="family-growth-safety.v1",
                safety_policy_version="family-growth-safety.v1",
                knowledge_refs=(material.ref,),
                asset_digest=context.snapshot_hash,
                system_policy="Draft only; never write facts.",
                system_policy_digest="policy-digest",
                knowledge_materials=(
                    KnowledgeExecutionPayload(
                        knowledge_ref=material.ref,
                        content=material.content,
                        source_ref=material.source,
                        license_ref="reviewed",
                        evidence_level="E3",
                        content_digest=material.digest,
                    ),
                ),
                material_digest=material.digest,
            ),
        )
        draft = await self._gateway.generate_structured(request, provider_id=provider_id)
        if draft.status != "DRAFT" or draft.may_mutate_business_state:
            raise VerticalRuntimeError("DRAFT_ONLY_VIOLATION")
        _assert_capability_grounding(draft.output, capability_refs)
        entry = EvaluationLedgerEntry(
            family_need_id,
            path_id,
            run_id,
            context.context_snapshot_ref,
            draft,
            feedback_refs,
            guardian_calibration=calibration,
            capability_refs=capability_refs,
        )
        self._ledger.append(entry)
        return entry


def _assert_capability_grounding(output: dict[str, Any], capability_refs: tuple[str, ...]) -> None:
    """Reject explicit model capability references absent from the reviewed catalogue."""

    if not capability_refs:
        return
    allowed = set(capability_refs)
    references: list[Any] = []
    declared = output.get("capability_refs")
    if isinstance(declared, (list, tuple)):
        references.extend(declared)
    path = output.get("path")
    if isinstance(path, (list, tuple)):
        for node in path:
            if isinstance(node, dict) and "capability_ref" in node:
                ref = node["capability_ref"]
                version = node.get("version")
                references.append(f"{ref}@{version}" if isinstance(version, str) else ref)
    if any(not isinstance(ref, str) or ref not in allowed for ref in references):
        raise VerticalRuntimeError("CAPABILITY_GROUNDING_VIOLATION")


__all__ = [
    "EvaluationLedger",
    "EvaluationLedgerEntry",
    "FamilyGrowthContext",
    "FeedbackPort",
    "GuardianDecision",
    "KnowledgePort",
    "CapabilityPort",
    "RegistryKnowledgePort",
    "ModelGatewayPort",
    "PublishedKnowledge",
    "VerticalFamilyGrowthRuntime",
    "VerticalRuntimeError",
]
