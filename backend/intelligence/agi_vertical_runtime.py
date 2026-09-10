"""Evaluation-only vertical family-growth runtime prototype.

This module is deliberately isolated from domain repositories.  It consumes the
existing ModelGateway port and produces an evaluation ledger record; it never
mutates FamilyNeed, CanonicalFact, service, commerce, or achievement state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
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
    async def latest(
        self, *, family_need_id: str, family_id: str | None = None
    ) -> tuple[str, ...]: ...

    async def preferences(self, *, family_id: str, family_need_id: str) -> object | None: ...


class ConsentPort(Protocol):
    """Live consent check used by the vertical runtime.

    Implementations must read the current consent record for every call.  The
    runtime intentionally accepts a port rather than a cached boolean so that
    withdrawal takes effect before the next generation and cannot leave an
    already-created context snapshot as an implicit permission.
    """

    async def is_current(
        self,
        *,
        family_id: str,
        subject_ids: tuple[str, ...],
        purpose: str,
        consent_version: str,
    ) -> bool: ...


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
    knowledge_ref: str = ""
    knowledge_version: str = ""
    lineage_ref: str = ""
    parent_run_id: str = ""
    input_refs: tuple[str, ...] = ()
    prompt_ref: str = ""
    system_policy_ref: str = ""
    knowledge_source: str = ""
    knowledge_digest: str = ""


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
        consent: ConsentPort | None = None,
    ) -> None:
        self._gateway = gateway
        self._context = context
        self._knowledge = knowledge
        self._feedback = feedback
        self._ledger = ledger
        self._capabilities = capabilities
        self._consent = consent
        # Process-local scope index used by the evaluation ledger boundary.
        # Durable deployments use ``DurableVerticalLedgerAdapter``; this index
        # still prevents a caller from replaying/deleting a run under another
        # family while exercising the in-process runtime.
        self._run_families: dict[str, str] = {}

    @property
    def context_durability_mode(self) -> str:
        """Expose the selected context port's durability for composition checks."""

        return str(getattr(self._context, "durability_mode", "UNKNOWN"))

    @property
    def context_port(self) -> ContextPort:
        """Return the context port used for every generation."""

        return self._context

    @property
    def feedback_port(self) -> FeedbackPort:
        """Return the feedback port used for next-round learning input."""

        return self._feedback

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
        context_snapshot_ref: str | None = None,
    ) -> EvaluationLedgerEntry:
        context = await self._context.read(
            family_id=family_id,
            context_snapshot_ref=context_snapshot_ref or f"context:{run_id}",
        )
        if context.family_id != family_id:
            raise VerticalRuntimeError("CONTEXT_SCOPE_MISMATCH")
        if self._consent is not None:
            current = await self._consent.is_current(
                family_id=family_id,
                subject_ids=context.subject_ids,
                purpose=context.purpose,
                consent_version=context.consent_version,
            )
            if not current:
                raise VerticalRuntimeError("CONSENT_NOT_ACTIVE")
        material = await self._knowledge.published(ref=knowledge_ref)
        if material is None:
            raise VerticalRuntimeError("KNOWLEDGE_NOT_PUBLISHED")
        feedback_refs = await _feedback_latest(
            self._feedback, family_need_id=family_need_id, family_id=family_id
        )
        feedback_preferences = await _feedback_preferences(
            self._feedback, family_id=family_id, family_need_id=family_need_id
        )
        calibration: dict[str, Any] | None = None
        if guardian_decision is not None:
            if (
                guardian_decision.family_need_id != family_need_id
                or guardian_decision.run_id != run_id
                or guardian_decision.path_id != path_id
            ):
                raise VerticalRuntimeError("GUARDIAN_DECISION_SCOPE_MISMATCH")
            self._ledger.decision(guardian_decision)
            feedback_refs = (*feedback_refs, guardian_decision.decision_ref)
            # A reference alone is not a learning signal: the next model run
            # must receive the guardian's bounded correction. Keep this as
            # explicit calibration metadata rather than merging it into the
            # family context (R9).
            calibration = {
                "decision_ref": guardian_decision.decision_ref,
                "state": guardian_decision.state,
                "edits": dict(guardian_decision.edits),
            }
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
        lineage_ref = _lineage_ref(
            context_snapshot_ref=context.context_snapshot_ref,
            context_source_refs=_context_source_refs(context.values),
            knowledge_ref=material.ref,
            knowledge_version=material.version,
            capability_refs=capability_refs,
            feedback_refs=feedback_refs,
            calibration=calibration,
        )
        request = StructuredRequest(
            use_case="vertical_family_growth",
            prompt_version="vertical-growth.v1",
            schema_version="vertical-growth-draft.v1",
            data_class="MINOR_PERSONAL_DATA",
            payload={
                "family_need_id": family_need_id,
                "path_id": path_id,
                "context": context.values,
                "required_dimensions": _required_dimensions(context.values),
                "feedback_refs": feedback_refs,
                "feedback_preferences": feedback_preferences,
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
                    # Optional v2 understanding envelope. Legacy providers
                    # remain readable, while any provider emitting dimensions
                    # must carry explicit evidence/unknown semantics below.
                    "dimensions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name"],
                            "properties": {
                                "name": {"type": "string"},
                                "state": {"type": "string"},
                                "evidence_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "unknowns": {"type": "array"},
                    "contradictions": {"type": "array"},
                },
            },
            context_snapshot_ref=context.context_snapshot_ref,
            input_refs=(
                family_need_id,
                path_id,
                f"knowledge:{material.ref}@{material.version}",
                *feedback_refs,
                *capability_refs,
            ),
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
        _assert_understanding_evidence_honesty(
            draft.output,
            source_refs=context.values.get("source_refs"),
            required_dimensions=_required_dimensions(context.values),
        )
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
            knowledge_ref=material.ref,
            knowledge_version=material.version,
            lineage_ref=lineage_ref,
            input_refs=request.input_refs,
            prompt_ref=request.prompt_execution_plan.prompt_ref,
            system_policy_ref=request.prompt_execution_plan.system_policy_ref,
            knowledge_source=material.source,
            knowledge_digest=material.digest,
        )
        self._ledger.append(entry)
        self._run_families[run_id] = family_id
        return entry

    def replay(self, *, run_id: str, family_id: str) -> EvaluationLedgerEntry:
        """Replay a draft only when its server-owned family scope matches."""

        if self._run_families.get(run_id) != family_id:
            raise VerticalRuntimeError("CONTEXT_SCOPE_MISMATCH")
        return self._ledger.replay(run_id)

    def delete(self, *, run_id: str, family_id: str) -> str:
        """Delete an evaluation artifact after enforcing family isolation."""

        if self._run_families.get(run_id) != family_id:
            raise VerticalRuntimeError("CONTEXT_SCOPE_MISMATCH")
        proof = self._ledger.delete(run_id)
        self._run_families.pop(run_id, None)
        return proof

    async def decide(
        self, *, run_id: str, family_id: str, decision: GuardianDecision
    ) -> EvaluationLedgerEntry:
        """Record a guardian calibration against an in-process draft.

        Development/test composition uses this method directly; production
        composition overrides the same contract with durable replay semantics.
        """

        if self._run_families.get(run_id) != family_id:
            raise VerticalRuntimeError("CONTEXT_SCOPE_MISMATCH")
        current = self._ledger.replay(run_id)
        if (
            current.family_need_id != decision.family_need_id
            or current.path_id != decision.path_id
            or current.run_id != decision.run_id
        ):
            raise VerticalRuntimeError("GUARDIAN_DECISION_SCOPE_MISMATCH")
        self._ledger.decision(decision)
        return self._ledger.replay(run_id)

    async def revise(
        self,
        *,
        run_id: str,
        next_run_id: str,
        family_id: str,
        decision: GuardianDecision,
    ) -> EvaluationLedgerEntry:
        """Generate a new draft from a guardian correction without rewriting history."""

        if not next_run_id.strip() or next_run_id == run_id:
            raise VerticalRuntimeError("REVISION_RUN_ID_INVALID")
        if next_run_id in self._run_families:
            existing = self.replay(run_id=next_run_id, family_id=family_id)
            if existing.parent_run_id != run_id:
                raise VerticalRuntimeError("REVISION_RUN_ID_CONFLICT")
            return existing
        current = await self.decide(run_id=run_id, family_id=family_id, decision=decision)
        next_decision = replace(decision, run_id=next_run_id)
        revised = await self.run(
            family_need_id=current.family_need_id,
            path_id=current.path_id,
            run_id=next_run_id,
            family_id=family_id,
            knowledge_ref=current.knowledge_ref,
            guardian_decision=next_decision,
            context_snapshot_ref=current.context_snapshot_ref,
        )
        revised = replace(revised, parent_run_id=run_id)
        self._ledger.delete(next_run_id)
        self._ledger.append(revised)
        if revised.draft.output == current.draft.output:
            self.delete(run_id=next_run_id, family_id=family_id)
            raise VerticalRuntimeError("REVISION_NO_CHANGE")
        return revised

    async def reflect(
        self,
        *,
        run_id: str,
        reflection_run_id: str,
        family_id: str,
        knowledge_ref: str | None = None,
        source_entry: EvaluationLedgerEntry | None = None,
    ) -> EvaluationLedgerEntry:
        """Generate a draft reflection from a prior growth run.

        Reflection is a new child draft, never an update to the source run.
        Only the scoped context, the source draft's bounded output, and
        metadata-only feedback references enter the request.  The result
        remains ``DRAFT`` and cannot become an outcome or fact here.
        """

        if not reflection_run_id.strip() or reflection_run_id == run_id:
            raise VerticalRuntimeError("REFLECTION_RUN_ID_INVALID")
        if source_entry is None and self._run_families.get(run_id) != family_id:
            raise VerticalRuntimeError("CONTEXT_SCOPE_MISMATCH")
        if reflection_run_id in self._run_families:
            existing = self.replay(run_id=reflection_run_id, family_id=family_id)
            if existing.parent_run_id != run_id:
                raise VerticalRuntimeError("REFLECTION_RUN_ID_CONFLICT")
            return existing
        source = source_entry if source_entry is not None else self._ledger.replay(run_id)
        if source.run_id != run_id:
            raise VerticalRuntimeError("REFLECTION_SOURCE_MISMATCH")
        context = await self._context.read(
            family_id=family_id, context_snapshot_ref=source.context_snapshot_ref
        )
        if self._consent is not None and not await self._consent.is_current(
            family_id=family_id,
            subject_ids=context.subject_ids,
            purpose=context.purpose,
            consent_version=context.consent_version,
        ):
            raise VerticalRuntimeError("CONSENT_NOT_ACTIVE")
        material = await self._knowledge.published(ref=knowledge_ref or source.knowledge_ref)
        if material is None:
            raise VerticalRuntimeError("KNOWLEDGE_NOT_PUBLISHED")
        feedback_refs = await _feedback_latest(
            self._feedback, family_need_id=source.family_need_id, family_id=family_id
        )
        request = StructuredRequest(
            use_case="vertical_family_growth_reflection",
            prompt_version="vertical-growth-reflection.v1",
            schema_version="vertical-growth-reflection.v1",
            data_class="MINOR_PERSONAL_DATA",
            payload={
                "family_need_id": source.family_need_id,
                "path_id": source.path_id,
                "source_run_id": source.run_id,
                "source_draft": {
                    "understanding": source.draft.output.get("understanding"),
                    "next_step": source.draft.output.get("next_step"),
                    "path": source.draft.output.get("path", ()),
                },
                "context": context.values,
                "feedback_refs": feedback_refs,
            },
            output_schema={
                "type": "object",
                "required": ["what_changed", "what_helped", "next_question", "unknowns"],
                "properties": {
                    "what_changed": {"type": "string"},
                    "what_helped": {"type": "string"},
                    "next_question": {"type": "string"},
                    "unknowns": {"type": "array", "items": {"type": "string"}},
                },
            },
            context_snapshot_ref=context.context_snapshot_ref,
            input_refs=(source.run_id, source.family_need_id, *feedback_refs),
            request_id=reflection_run_id,
            tenant_id=context.tenant_id,
            family_id=context.family_id,
            prompt_execution_plan=PromptExecutionPlan(
                prompt_ref="vertical-family-growth-reflection",
                prompt_version="vertical-growth-reflection.v1",
                template="Reflect on the bounded growth draft; never state a fact or diagnosis.",
                system_policy_ref="family-growth-safety.v1",
                safety_policy_version="family-growth-safety.v1",
                knowledge_refs=(material.ref,),
                asset_digest=context.snapshot_hash,
                system_policy="Draft only; never write facts or outcomes.",
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
        draft = await self._gateway.generate_structured(request)
        if draft.status != "DRAFT" or draft.may_mutate_business_state:
            raise VerticalRuntimeError("DRAFT_ONLY_VIOLATION")
        for field_name in ("what_changed", "what_helped", "next_question"):
            value = draft.output.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise VerticalRuntimeError("REFLECTION_OUTPUT_INVALID")
        unknowns = draft.output.get("unknowns")
        if not isinstance(unknowns, list) or any(
            not isinstance(item, str) or not item.strip() for item in unknowns
        ):
            raise VerticalRuntimeError("REFLECTION_OUTPUT_INVALID")
        entry = EvaluationLedgerEntry(
            family_need_id=source.family_need_id,
            path_id=source.path_id,
            run_id=reflection_run_id,
            context_snapshot_ref=context.context_snapshot_ref,
            draft=draft,
            feedback_refs=feedback_refs,
            parent_run_id=source.run_id,
            input_refs=request.input_refs,
            prompt_ref=request.prompt_execution_plan.prompt_ref,
            system_policy_ref=request.prompt_execution_plan.system_policy_ref,
            knowledge_ref=material.ref,
            knowledge_version=material.version,
            lineage_ref=source.lineage_ref,
            knowledge_source=material.source,
            knowledge_digest=material.digest,
        )
        self._ledger.append(entry)
        self._run_families[reflection_run_id] = family_id
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


def _assert_understanding_evidence_honesty(
    output: dict[str, Any],
    *,
    source_refs: object = None,
    required_dimensions: tuple[str, ...] = (),
) -> None:
    """Validate the optional v2 understanding envelope without inventing facts.

    Legacy drafts remain valid. When a provider emits structured dimensions,
    every dimension must cite evidence or explicitly declare ``UNKNOWN``;
    contradictions must remain visible as structured data rather than being
    silently collapsed into the prose understanding.
    """

    envelope_fields = ("dimensions", "evidence_refs", "unknowns", "contradictions")
    if not any(field in output for field in envelope_fields):
        if required_dimensions:
            raise VerticalRuntimeError("UNDERSTANDING_ENVELOPE_REQUIRED")
        return
    dimensions = output.get("dimensions", [])
    if not isinstance(dimensions, list):
        raise VerticalRuntimeError("UNDERSTANDING_DIMENSIONS_INVALID")
    if required_dimensions:
        names = [
            dimension.get("name")
            for dimension in dimensions
            if isinstance(dimension, dict)
        ]
        if len(names) != len(set(names)) or set(names) != set(required_dimensions):
            raise VerticalRuntimeError("UNDERSTANDING_DIMENSION_SET_INVALID")
    evidence_refs = output.get("evidence_refs", ())
    if not isinstance(evidence_refs, list) or any(
        not isinstance(ref, str) or not ref.strip() for ref in evidence_refs
    ):
        raise VerticalRuntimeError("UNDERSTANDING_EVIDENCE_REFS_INVALID")
    if source_refs is not None:
        if not isinstance(source_refs, (list, tuple)) or any(
            not isinstance(ref, str) or not ref.strip() for ref in source_refs
        ):
            raise VerticalRuntimeError("UNDERSTANDING_SOURCE_REFS_INVALID")
        allowed_refs = set(source_refs)
        if any(ref not in allowed_refs for ref in evidence_refs):
            raise VerticalRuntimeError("UNDERSTANDING_EVIDENCE_REF_UNGROUNDED")
    unknowns = output.get("unknowns", ())
    contradictions = output.get("contradictions", ())
    if not isinstance(unknowns, list) or not isinstance(contradictions, list):
        raise VerticalRuntimeError("UNDERSTANDING_DISCLOSURE_FIELDS_INVALID")
    declared_refs = set(evidence_refs)
    unknown_dimensions = {
        item.get("dimension")
        for item in unknowns
        if isinstance(item, dict) and isinstance(item.get("dimension"), str)
    }
    for dimension in dimensions:
        if not isinstance(dimension, dict) or not isinstance(dimension.get("name"), str):
            raise VerticalRuntimeError("UNDERSTANDING_DIMENSION_INVALID")
        refs = dimension.get("evidence_refs", ())
        # ``status`` is reserved by the durable run contract for DRAFT;
        # dimension epistemic state therefore uses the non-ambiguous ``state``
        # key so UNKNOWN cannot be mistaken for a lifecycle promotion.
        is_unknown = dimension.get("state") == "UNKNOWN"
        if is_unknown and dimension.get("name") not in unknown_dimensions:
            raise VerticalRuntimeError("UNDERSTANDING_UNKNOWN_NOT_DISCLOSED")
        if not is_unknown and (
            not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
        ):
            raise VerticalRuntimeError("UNDERSTANDING_DIMENSION_EVIDENCE_MISSING")
        if not is_unknown and any(ref not in set(source_refs or ()) for ref in refs):
            raise VerticalRuntimeError("UNDERSTANDING_DIMENSION_EVIDENCE_UNGROUNDED")
        if not is_unknown and any(ref not in declared_refs for ref in refs):
            raise VerticalRuntimeError("UNDERSTANDING_DIMENSION_EVIDENCE_NOT_DECLARED")
    for contradiction in contradictions:
        if not isinstance(contradiction, dict):
            raise VerticalRuntimeError("UNDERSTANDING_CONTRADICTION_INVALID")
        refs = contradiction.get("refs", ())
        if not isinstance(refs, list) or not refs:
            raise VerticalRuntimeError("UNDERSTANDING_CONTRADICTION_REFS_MISSING")
        if any(not isinstance(ref, str) or ref not in declared_refs for ref in refs):
            raise VerticalRuntimeError("UNDERSTANDING_CONTRADICTION_REF_NOT_DECLARED")
        if source_refs is not None and any(ref not in set(source_refs) for ref in refs):
            raise VerticalRuntimeError("UNDERSTANDING_CONTRADICTION_REF_UNGROUNDED")


def _required_dimensions(values: dict[str, Any]) -> tuple[str, ...]:
    """Return the server-declared understanding dimensions for this context.

    The list is context metadata, not a client-controlled request field.  It
    lets a product surface require a complete five-dimension observation while
    keeping older internal callers on the backwards-compatible envelope path.
    """

    raw = values.get("required_dimensions", ())
    if not isinstance(raw, (list, tuple)):
        return ()
    dimensions = tuple(item.strip() for item in raw if isinstance(item, str) and item.strip())
    if len(dimensions) != len(set(dimensions)):
        raise VerticalRuntimeError("UNDERSTANDING_REQUIRED_DIMENSIONS_INVALID")
    return dimensions


async def _feedback_latest(
    feedback: FeedbackPort, *, family_need_id: str, family_id: str
) -> tuple[str, ...]:
    """Read feedback with the family scope when supported by the adapter."""
    try:
        value = feedback.latest(family_need_id=family_need_id, family_id=family_id)
    except TypeError:
        value = feedback.latest(family_need_id=family_need_id)
    return tuple(await value if hasattr(value, "__await__") else value)


async def _feedback_preferences(
    feedback: FeedbackPort, *, family_id: str, family_need_id: str
) -> object | None:
    reader = getattr(feedback, "preferences", None)
    if not callable(reader):
        return None
    value = reader(family_id=family_id, family_need_id=family_need_id)
    return await value if hasattr(value, "__await__") else value


def _lineage_ref(
    *,
    context_snapshot_ref: str,
    context_source_refs: tuple[str, ...],
    knowledge_ref: str,
    knowledge_version: str,
    capability_refs: tuple[str, ...],
    feedback_refs: tuple[str, ...],
    calibration: dict[str, Any] | None,
) -> str:
    """Return a stable, content-free identity for one generation lineage."""

    material = json.dumps(
        {
            "context_snapshot_ref": context_snapshot_ref,
            "context_source_refs": context_source_refs,
            "knowledge": f"{knowledge_ref}@{knowledge_version}",
            "capabilities": capability_refs,
            "feedback_refs": feedback_refs,
            "calibration": calibration,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "lineage:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _context_source_refs(values: dict[str, Any]) -> tuple[str, ...]:
    """Return deterministic evidence refs carried by the scoped context."""

    refs = values.get("source_refs", ())
    if not isinstance(refs, (list, tuple)):
        return ()
    return tuple(sorted(ref for ref in refs if isinstance(ref, str) and ref.strip()))


__all__ = [
    "EvaluationLedger",
    "EvaluationLedgerEntry",
    "FamilyGrowthContext",
    "FeedbackPort",
    "ConsentPort",
    "GuardianDecision",
    "KnowledgePort",
    "CapabilityPort",
    "RegistryKnowledgePort",
    "ModelGatewayPort",
    "PublishedKnowledge",
    "VerticalFamilyGrowthRuntime",
    "VerticalRuntimeError",
]
