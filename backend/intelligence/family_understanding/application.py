"""Application seam for real, provider-generated family understanding drafts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.intelligence.family_understanding.contracts import (
    OUTPUT_SCHEMA,
    ContextInput,
    FamilyUnderstandingContextV1,
    KnowledgeRef,
)
from backend.intelligence.family_understanding.eval import (
    EvaluationArtifact,
    FamilyUnderstandingEvaluator,
)
from backend.intelligence.family_understanding.provenance import (
    UnderstandingProvenanceBinding,
)


@dataclass(frozen=True, slots=True)
class GenerateUnderstandingCommand:
    run_id: str
    tenant_id: str
    family_id: str
    subject_ref: str
    consent_ref: str
    context_snapshot_ref: str
    context_expires_at: datetime
    guardian_input_ref: str
    guardian_text: str
    revision: int
    prior_draft_artifact_hash: str | None
    reviewed_knowledge_refs: tuple[KnowledgeRef, ...]

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise ValueError("revision must be positive")
        if self.revision == 1 and self.prior_draft_artifact_hash is not None:
            raise ValueError("initial generation cannot reference a prior draft")
        if self.revision > 1 and not (self.prior_draft_artifact_hash or "").strip():
            raise ValueError("correction generation requires prior_draft_artifact_hash")
        if not self.guardian_text.strip():
            raise ValueError("guardian_text is required")


@dataclass(frozen=True, slots=True)
class UnderstandingDraftView:
    run_id: str
    artifact_hash: str
    request_hash: str
    provenance_ref: str
    version: int
    prior_draft_artifact_hash: str | None
    status: str
    summary: str
    hypotheses: tuple[dict[str, object], ...]
    unknowns: tuple[dict[str, str], ...]
    follow_up_questions: tuple[str, ...]
    strengths: tuple[dict[str, object], ...]
    desired_change: dict[str, object]
    source_refs: tuple[str, ...]
    knowledge_references: tuple[str, ...]
    provider_id: str
    model: str
    model_version: str
    prompt_version: str
    schema_version: str
    context_snapshot_ref: str
    provenance: dict[str, object]
    requires_guardian_confirmation: bool
    may_mutate_business_state: bool


class FamilyUnderstandingApplication:
    """Generate a draft through the one injected evaluator/Model Gateway path."""

    def __init__(self, evaluator: FamilyUnderstandingEvaluator) -> None:
        self._evaluator = evaluator

    async def generate(self, command: GenerateUnderstandingCommand) -> UnderstandingDraftView:
        context = FamilyUnderstandingContextV1(
            snapshot_ref=command.context_snapshot_ref,
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            subject_ref=command.subject_ref,
            consent_ref=command.consent_ref,
            consent_granted=True,
            expires_at=command.context_expires_at,
            inputs=(
                ContextInput(
                    source_ref=command.guardian_input_ref,
                    kind="GUARDIAN_TEXT",
                    text=command.guardian_text,
                    source="guardian",
                    fixture_only=False,
                    machine_derived=False,
                    guardian_confirmed=True,
                ),
            ),
            knowledge_refs=command.reviewed_knowledge_refs,
            data_class="FAMILY_PRIVATE_TEXT",
            fixture_only=False,
        )
        artifact = await self._evaluator.evaluate(
            context,
            run_id=command.run_id,
            tenant_id=command.tenant_id,
            family_id=command.family_id,
        )
        return _to_view(
            artifact,
            version=command.revision,
            prior_draft_artifact_hash=command.prior_draft_artifact_hash,
        )


def _to_view(
    artifact: EvaluationArtifact,
    *,
    version: int,
    prior_draft_artifact_hash: str | None,
) -> UnderstandingDraftView:
    draft = artifact.draft
    hypotheses = tuple(
        {
            "statement": item.statement,
            "source_refs": item.source_refs,
            "knowledge_refs": item.knowledge_refs,
            "uncertainty": item.uncertainty,
            "disconfirming_question": item.disconfirming_question,
        }
        for item in draft.hypotheses
    )
    unknowns = tuple({"question": item.question, "reason": item.reason} for item in draft.unknowns)
    strengths = tuple(
        {
            "statement": item.statement,
            "source_refs": item.source_refs,
            "uncertainty": item.uncertainty,
        }
        for item in draft.strengths
    )
    evidence_refs = tuple(
        dict.fromkeys((*draft.perspective.source_refs, *draft.perspective.knowledge_refs))
    )
    binding = UnderstandingProvenanceBinding(
        artifact_hash=artifact.artifact_hash,
        draft_version=version,
        output_schema=OUTPUT_SCHEMA,
        context_snapshot_ref=draft.provenance.context_snapshot_ref,
        source_refs=draft.perspective.source_refs,
        evidence_refs=evidence_refs,
        provider_id=draft.provenance.provider_id,
        model=draft.provenance.model,
        model_version=draft.provenance.model_version,
        prompt_version=draft.provenance.prompt_version,
        schema_version=draft.provenance.schema_version,
    )
    return UnderstandingDraftView(
        run_id=artifact.run_id,
        artifact_hash=artifact.artifact_hash,
        request_hash=artifact.request_hash,
        provenance_ref=binding.provenance_ref,
        version=version,
        prior_draft_artifact_hash=prior_draft_artifact_hash,
        status=draft.status,
        summary=draft.perspective.summary,
        hypotheses=hypotheses,
        unknowns=unknowns,
        follow_up_questions=draft.follow_up_questions,
        strengths=strengths,
        desired_change={
            "statement": draft.desired_change.statement,
            "source_refs": draft.desired_change.source_refs,
            "uncertainty": draft.desired_change.uncertainty,
        },
        source_refs=draft.perspective.source_refs,
        knowledge_references=draft.perspective.knowledge_refs,
        provider_id=draft.provenance.provider_id,
        model=draft.provenance.model,
        model_version=draft.provenance.model_version,
        prompt_version=draft.provenance.prompt_version,
        schema_version=draft.provenance.schema_version,
        context_snapshot_ref=draft.provenance.context_snapshot_ref,
        provenance={
            "provenance_ref": binding.provenance_ref,
            "artifact_hash": artifact.artifact_hash,
            "draft_version": version,
            "output_schema": OUTPUT_SCHEMA,
            "source_refs": draft.perspective.source_refs,
            "evidence_refs": evidence_refs,
            "provider_id": draft.provenance.provider_id,
            "model": draft.provenance.model,
            "model_version": draft.provenance.model_version,
            "prompt_version": draft.provenance.prompt_version,
            "schema_version": draft.provenance.schema_version,
            "context_snapshot_ref": draft.provenance.context_snapshot_ref,
            "use_case": draft.provenance.use_case,
            "confidence": draft.provenance.confidence,
            "generated_at": draft.provenance.generated_at.isoformat(),
        },
        requires_guardian_confirmation=draft.requires_human_confirmation,
        may_mutate_business_state=draft.may_mutate_business_state,
    )
