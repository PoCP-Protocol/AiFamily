"""Typed, draft-only contracts for AIR-01 family problem understanding.

This package does not own a family domain aggregate. It accepts an authorised,
synthetic context snapshot and turns a schema-validated gateway response into a
typed draft. Promotion to a canonical fact, need, intent, plan, or outcome is
deliberately absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from backend.intelligence.model_gateway.contracts import AiProvenance

USE_CASE = "family_problem_understanding_v1"
SCHEMA_VERSION = "family_problem_understanding.v1"
InputKind = Literal["GUARDIAN_TEXT", "VOICE_TRANSCRIPT", "OCR_TEXT"]
InputSource = Literal["synthetic", "sandbox", "guardian"]
_INPUT_KINDS = frozenset({"GUARDIAN_TEXT", "VOICE_TRANSCRIPT", "OCR_TEXT"})
_INPUT_SOURCES = frozenset({"synthetic", "sandbox", "guardian"})
_FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "action",
        "canonical_fact",
        "diagnosis",
        "fact",
        "family_need",
        "growth_intent",
        "outcome",
        "plan",
        "may_mutate_business_state",
    }
)


def _required(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required")


def _unique_nonempty(values: tuple[str, ...], field_name: str) -> None:
    if not values or any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must contain non-empty references")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must not contain duplicate references")


@dataclass(frozen=True, slots=True)
class KnowledgeRef:
    ref: str
    source: str
    version: str
    chunk_ref: str
    content_digest: str
    applicability: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("ref", "source", "version", "chunk_ref", "content_digest", "applicability"):
            _required(getattr(self, name), f"KnowledgeRef.{name}")
        _unique_nonempty(self.limitations, "KnowledgeRef.limitations")


@dataclass(frozen=True, slots=True)
class ContextInput:
    source_ref: str
    kind: InputKind
    text: str
    source: InputSource
    fixture_only: bool = True
    machine_derived: bool = False
    guardian_confirmed: bool = True

    def __post_init__(self) -> None:
        _required(self.source_ref, "ContextInput.source_ref")
        _required(self.text, "ContextInput.text")
        if self.kind not in _INPUT_KINDS:
            raise ValueError(f"unsupported ContextInput.kind: {self.kind!r}")
        if self.source not in _INPUT_SOURCES:
            raise ValueError(f"unsupported ContextInput.source: {self.source!r}")
        if (self.source in {"synthetic", "sandbox"}) != self.fixture_only:
            raise ValueError("fixture_only must match synthetic/sandbox input source")
        if self.machine_derived and not self.guardian_confirmed:
            raise ValueError(
                "machine-derived input requires guardian confirmation before model access"
            )


@dataclass(frozen=True, slots=True)
class FamilyUnderstandingContextV1:
    snapshot_ref: str
    tenant_id: str
    family_id: str
    subject_ref: str
    consent_ref: str
    consent_granted: Literal[True]
    expires_at: datetime
    inputs: tuple[ContextInput, ...]
    knowledge_refs: tuple[KnowledgeRef, ...]
    purpose: Literal["family_problem_understanding_v1"] = USE_CASE
    data_class: Literal["SYNTHETIC", "FAMILY_PRIVATE_TEXT"] = "SYNTHETIC"
    fixture_only: bool = True

    def __post_init__(self) -> None:
        for name in ("snapshot_ref", "tenant_id", "family_id", "subject_ref", "consent_ref"):
            _required(getattr(self, name), f"FamilyUnderstandingContextV1.{name}")
        if self.purpose != USE_CASE:
            raise ValueError(f"unsupported purpose: {self.purpose!r}")
        if self.data_class not in {"SYNTHETIC", "FAMILY_PRIVATE_TEXT"}:
            raise ValueError(f"unsupported data class: {self.data_class!r}")
        if (self.data_class == "SYNTHETIC") != self.fixture_only:
            raise ValueError("fixture_only must match the SYNTHETIC data class")
        if any(item.fixture_only != self.fixture_only for item in self.inputs):
            raise ValueError("context and input fixture classification must match")
        if self.consent_granted is not True:
            raise ValueError("consent must be granted before model access")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("FamilyUnderstandingContextV1.expires_at must be timezone-aware")
        if self.expires_at <= datetime.now(UTC):
            raise ValueError("authorised context snapshot is expired")
        if not self.inputs:
            raise ValueError("FamilyUnderstandingContextV1.inputs must not be empty")
        if not self.knowledge_refs:
            raise ValueError("FamilyUnderstandingContextV1.knowledge_refs must not be empty")
        _unique_nonempty(tuple(item.source_ref for item in self.inputs), "context input refs")
        _unique_nonempty(tuple(item.ref for item in self.knowledge_refs), "context knowledge refs")

    @property
    def source_refs(self) -> tuple[str, ...]:
        return tuple(item.source_ref for item in self.inputs)

    @property
    def knowledge_ref_ids(self) -> tuple[str, ...]:
        return tuple(item.ref for item in self.knowledge_refs)

    def assert_scope(self, *, tenant_id: str, family_id: str) -> None:
        if tenant_id != self.tenant_id or family_id != self.family_id:
            raise ValueError("context snapshot tenant/family scope mismatch")

    def to_gateway_payload(self) -> dict[str, Any]:
        return {
            "purpose": self.purpose,
            "scope": {"tenant_id": self.tenant_id, "family_id": self.family_id},
            "subject_ref": self.subject_ref,
            "consent_ref": self.consent_ref,
            "fixture_only": self.fixture_only,
            "inputs": [
                {
                    "source_ref": item.source_ref,
                    "kind": item.kind,
                    "text": item.text,
                    "source": item.source,
                    "fixture_only": item.fixture_only,
                }
                for item in self.inputs
            ],
            "knowledge_refs": [
                {
                    "ref": item.ref,
                    "source": item.source,
                    "version": item.version,
                    "chunk_ref": item.chunk_ref,
                    "content_digest": item.content_digest,
                    "applicability": item.applicability,
                    "limitations": list(item.limitations),
                }
                for item in self.knowledge_refs
            ],
            "instructions": {
                "output_is_draft": True,
                "preserve_unknowns": True,
                "diagnosis_forbidden": True,
                "canonical_mutation_forbidden": True,
            },
        }


@dataclass(frozen=True, slots=True)
class PerspectiveDraft:
    summary: str
    source_refs: tuple[str, ...]
    knowledge_refs: tuple[str, ...]
    uncertainty: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("summary", "uncertainty"):
            _required(getattr(self, name), f"PerspectiveDraft.{name}")
        _unique_nonempty(self.limitations, "PerspectiveDraft.limitations")


@dataclass(frozen=True, slots=True)
class HypothesisDraft:
    statement: str
    source_refs: tuple[str, ...]
    knowledge_refs: tuple[str, ...]
    uncertainty: str
    disconfirming_question: str

    def __post_init__(self) -> None:
        for name in ("statement", "uncertainty", "disconfirming_question"):
            _required(getattr(self, name), f"HypothesisDraft.{name}")


@dataclass(frozen=True, slots=True)
class UnknownDraft:
    question: str
    reason: str

    def __post_init__(self) -> None:
        _required(self.question, "UnknownDraft.question")
        _required(self.reason, "UnknownDraft.reason")


@dataclass(frozen=True, slots=True)
class StrengthDraft:
    statement: str
    source_refs: tuple[str, ...]
    uncertainty: str

    def __post_init__(self) -> None:
        _required(self.statement, "StrengthDraft.statement")
        _required(self.uncertainty, "StrengthDraft.uncertainty")


@dataclass(frozen=True, slots=True)
class DesiredChangeDraft:
    statement: str
    source_refs: tuple[str, ...]
    uncertainty: str

    def __post_init__(self) -> None:
        _required(self.statement, "DesiredChangeDraft.statement")
        _required(self.uncertainty, "DesiredChangeDraft.uncertainty")


@dataclass(frozen=True, slots=True)
class ProblemUnderstandingDraftV1:
    perspective: PerspectiveDraft
    hypotheses: tuple[HypothesisDraft, ...]
    unknowns: tuple[UnknownDraft, ...]
    follow_up_questions: tuple[str, ...]
    strengths: tuple[StrengthDraft, ...]
    desired_change: DesiredChangeDraft
    provenance: AiProvenance
    status: Literal["DRAFT"] = "DRAFT"

    @property
    def may_mutate_business_state(self) -> bool:
        return False

    @property
    def requires_human_confirmation(self) -> bool:
        return True

    @classmethod
    def from_gateway_output(
        cls,
        output: dict[str, Any],
        *,
        provenance: AiProvenance,
        context: FamilyUnderstandingContextV1,
    ) -> ProblemUnderstandingDraftV1:
        forbidden = _find_forbidden_keys(output)
        if forbidden:
            raise ValueError(
                f"gateway output contains forbidden business-state fields: {forbidden}"
            )
        if (
            provenance.context_snapshot_ref != context.snapshot_ref
            or provenance.use_case != USE_CASE
            or provenance.schema_version != SCHEMA_VERSION
            or provenance.data_class != context.data_class
        ):
            raise ValueError("gateway provenance does not match the authorised AIR-01 context")
        perspective_raw = output["perspective"]
        perspective = PerspectiveDraft(
            summary=perspective_raw["summary"],
            source_refs=tuple(perspective_raw["source_refs"]),
            knowledge_refs=tuple(perspective_raw["knowledge_refs"]),
            uncertainty=perspective_raw["uncertainty"],
            limitations=tuple(perspective_raw["limitations"]),
        )
        hypotheses = tuple(
            HypothesisDraft(
                statement=item["statement"],
                source_refs=tuple(item["source_refs"]),
                knowledge_refs=tuple(item["knowledge_refs"]),
                uncertainty=item["uncertainty"],
                disconfirming_question=item["disconfirming_question"],
            )
            for item in output["hypotheses"]
        )
        unknowns = tuple(
            UnknownDraft(question=item["question"], reason=item["reason"])
            for item in output["unknowns"]
        )
        follow_up_questions = tuple(output["follow_up_questions"])
        strengths = tuple(
            StrengthDraft(
                statement=item["statement"],
                source_refs=tuple(item["source_refs"]),
                uncertainty=item["uncertainty"],
            )
            for item in output["strengths"]
        )
        desired_raw = output["desired_change"]
        desired_change = DesiredChangeDraft(
            statement=desired_raw["statement"],
            source_refs=tuple(desired_raw["source_refs"]),
            uncertainty=desired_raw["uncertainty"],
        )
        draft = cls(
            perspective=perspective,
            hypotheses=hypotheses,
            unknowns=unknowns,
            follow_up_questions=follow_up_questions,
            strengths=strengths,
            desired_change=desired_change,
            provenance=provenance,
        )
        draft._validate_grounding(context)
        return draft

    def _validate_grounding(self, context: FamilyUnderstandingContextV1) -> None:
        if not 1 <= len(self.hypotheses) <= 3:
            raise ValueError("draft must contain between one and three explicit hypotheses")
        if not self.unknowns:
            raise ValueError("draft must preserve at least one Unknown")
        _unique_nonempty(self.follow_up_questions, "draft follow_up_questions")
        if not self.strengths:
            raise ValueError("draft must preserve at least one family strength")
        source_allowlist = set(context.source_refs)
        knowledge_allowlist = set(context.knowledge_ref_ids)
        cited = (self.perspective, *self.hypotheses)
        for item in cited:
            _unique_nonempty(item.source_refs, "draft source_refs")
            _unique_nonempty(item.knowledge_refs, "draft knowledge_refs")
            unknown_sources = set(item.source_refs) - source_allowlist
            unknown_knowledge = set(item.knowledge_refs) - knowledge_allowlist
            if unknown_sources or unknown_knowledge:
                raise ValueError(
                    "draft contains citations outside the authorised context: "
                    f"sources={sorted(unknown_sources)}, knowledge={sorted(unknown_knowledge)}"
                )
        for item in (*self.strengths, self.desired_change):
            _unique_nonempty(item.source_refs, "draft source_refs")
            unknown_sources = set(item.source_refs) - source_allowlist
            if unknown_sources:
                raise ValueError(
                    "draft contains citations outside the authorised context: "
                    f"sources={sorted(unknown_sources)}"
                )


def _find_forbidden_keys(value: object) -> list[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            normalised = str(key).strip().lower()
            if normalised in _FORBIDDEN_OUTPUT_KEYS:
                found.add(normalised)
            found.update(_find_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_find_forbidden_keys(child))
    return sorted(found)


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "perspective",
        "hypotheses",
        "unknowns",
        "follow_up_questions",
        "strengths",
        "desired_change",
    ],
    "properties": {
        "perspective": {
            "type": "object",
            "required": [
                "summary",
                "source_refs",
                "knowledge_refs",
                "uncertainty",
                "limitations",
            ],
            "properties": {
                "summary": {"type": "string"},
                "source_refs": {"type": "array", "items": {"type": "string"}},
                "knowledge_refs": {"type": "array", "items": {"type": "string"}},
                "uncertainty": {"type": "string"},
                "limitations": {"type": "array", "items": {"type": "string"}},
            },
        },
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "statement",
                    "source_refs",
                    "knowledge_refs",
                    "uncertainty",
                    "disconfirming_question",
                ],
                "properties": {
                    "statement": {"type": "string"},
                    "source_refs": {"type": "array", "items": {"type": "string"}},
                    "knowledge_refs": {"type": "array", "items": {"type": "string"}},
                    "uncertainty": {"type": "string"},
                    "disconfirming_question": {"type": "string"},
                },
            },
        },
        "unknowns": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["question", "reason"],
                "properties": {
                    "question": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "follow_up_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "strengths": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["statement", "source_refs", "uncertainty"],
                "properties": {
                    "statement": {"type": "string"},
                    "source_refs": {"type": "array", "items": {"type": "string"}},
                    "uncertainty": {"type": "string"},
                },
            },
        },
        "desired_change": {
            "type": "object",
            "required": ["statement", "source_refs", "uncertainty"],
            "properties": {
                "statement": {"type": "string"},
                "source_refs": {"type": "array", "items": {"type": "string"}},
                "uncertainty": {"type": "string"},
            },
        },
    },
}
