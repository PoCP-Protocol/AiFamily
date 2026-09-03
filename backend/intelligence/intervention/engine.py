"""Provider-neutral Growth Intervention decision boundary.

The engine consumes already validated hypotheses and action candidates.  It
selects a small, evidence-bound set of *draft* suggestions; it never invokes
a model, writes a domain fact, or computes a family/person score or rank.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from backend.intelligence.experience.contracts import ExperienceScope

InterventionStatus = Literal["DRAFT"]


class InterventionEngineError(ValueError):
    """Raised when an interpretation cannot safely enter intervention."""


@dataclass(frozen=True, slots=True)
class InterventionCandidate:
    """A reviewable next-step suggestion, never a committed action."""

    action_ref: str
    primary_contradiction_ref: str | None
    confidence: float
    evidence_refs: tuple[str, ...]
    status: InterventionStatus = "DRAFT"
    human_gate_required: bool = False
    reason_code: str = "EVIDENCE_BOUND_CANDIDATE"

    def __post_init__(self) -> None:
        if not self.action_ref or self.status != "DRAFT":
            raise InterventionEngineError("INTERVENTION_DRAFT_ONLY")
        if not 0.0 <= self.confidence <= 1.0:
            raise InterventionEngineError("INTERVENTION_CONFIDENCE_INVALID")
        if not self.evidence_refs or any(not ref for ref in self.evidence_refs):
            raise InterventionEngineError("INTERVENTION_EVIDENCE_REQUIRED")
        if not self.reason_code:
            raise InterventionEngineError("INTERVENTION_REASON_REQUIRED")


@dataclass(frozen=True, slots=True)
class InterventionDraft:
    """Immutable output of one bounded intervention selection pass."""

    scope: ExperienceScope
    context_snapshot_ref: str
    primary_contradiction_refs: tuple[str, ...]
    candidates: tuple[InterventionCandidate, ...]
    status: InterventionStatus = "DRAFT"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExperienceScope):
            raise InterventionEngineError("EXPERIENCE_SCOPE_REQUIRED")
        if not self.context_snapshot_ref or self.status != "DRAFT":
            raise InterventionEngineError("INTERVENTION_DRAFT_ONLY")
        if len(self.primary_contradiction_refs) > 3:
            raise InterventionEngineError("TOO_MANY_PRIMARY_CONTRADICTIONS")
        if any(not ref for ref in self.primary_contradiction_refs):
            raise InterventionEngineError("PRIMARY_CONTRADICTION_REF_INVALID")

    def to_payload(self) -> dict[str, Any]:
        """Return the bounded API projection consumed by Experience/UI layers."""

        return {
            "status": self.status,
            "context_snapshot_ref": self.context_snapshot_ref,
            "primary_contradiction_refs": list(self.primary_contradiction_refs),
            "candidates": [
                {
                    "action_ref": candidate.action_ref,
                    "primary_contradiction_ref": candidate.primary_contradiction_ref,
                    "confidence": candidate.confidence,
                    "evidence_refs": list(candidate.evidence_refs),
                    "status": candidate.status,
                    "human_gate_required": candidate.human_gate_required,
                    "reason_code": candidate.reason_code,
                }
                for candidate in self.candidates
            ],
        }


class GrowthInterventionEngine:
    """Select evidence-bound drafts from an assessment interpretation payload."""

    def select(
        self,
        *,
        scope: ExperienceScope,
        context_snapshot_ref: str,
        hypotheses: Sequence[Mapping[str, Any]],
        action_candidates: Sequence[Mapping[str, Any]],
        evidence_refs: Sequence[str],
        high_impact: bool = False,
    ) -> InterventionDraft:
        if not isinstance(scope, ExperienceScope):
            raise InterventionEngineError("EXPERIENCE_SCOPE_REQUIRED")
        if not scope.consent_granted:
            raise InterventionEngineError("INTERVENTION_CONSENT_REQUIRED")
        refs = _unique_refs(evidence_refs, "INTERVENTION_EVIDENCE_REQUIRED")
        primary = _primary_contradictions(hypotheses)
        if not action_candidates:
            raise InterventionEngineError("INTERVENTION_ACTION_CANDIDATES_REQUIRED")

        selected: list[InterventionCandidate] = []
        for index, raw in enumerate(action_candidates):
            action_ref = raw.get("action_ref")
            boundary = raw.get("boundary")
            if not isinstance(action_ref, str) or not action_ref.strip():
                raise InterventionEngineError("INTERVENTION_ACTION_REF_REQUIRED")
            if boundary != "recommendation_not_decision":
                raise InterventionEngineError("INTERVENTION_BOUNDARY_REQUIRED")
            contradiction_ref = raw.get("primary_contradiction_ref")
            if contradiction_ref is not None and contradiction_ref not in primary:
                raise InterventionEngineError("INTERVENTION_CONTRADICTION_NOT_PRIMARY")
            if contradiction_ref is None and primary:
                contradiction_ref = primary[min(index, len(primary) - 1)]
            confidence = _confidence(raw.get("confidence", 0.5))
            selected.append(
                InterventionCandidate(
                    action_ref=action_ref.strip(),
                    primary_contradiction_ref=contradiction_ref,
                    confidence=confidence,
                    evidence_refs=refs,
                    human_gate_required=(
                        high_impact or str(scope.data_class) == "MINOR_PERSONAL_DATA"
                    ),
                    reason_code=str(raw.get("reason_code") or "EVIDENCE_BOUND_CANDIDATE"),
                )
            )

        selected.sort(
            key=lambda candidate: (
                -candidate.confidence,
                candidate.action_ref,
            )
        )
        return InterventionDraft(
            scope=scope,
            context_snapshot_ref=context_snapshot_ref,
            primary_contradiction_refs=primary,
            candidates=tuple(selected),
        )


def _primary_contradictions(
    hypotheses: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    values: list[tuple[int, str]] = []
    for index, hypothesis in enumerate(hypotheses):
        ref = hypothesis.get("hypothesis_ref")
        if not isinstance(ref, str) or not ref.strip():
            raise InterventionEngineError("HYPOTHESIS_REF_REQUIRED")
        if hypothesis.get("is_primary_contradiction"):
            values.append((index, ref.strip()))
    if len(values) > 3:
        raise InterventionEngineError("TOO_MANY_PRIMARY_CONTRADICTIONS")
    return tuple(ref for _, ref in values)


def _unique_refs(values: Sequence[str], error_code: str) -> tuple[str, ...]:
    refs = tuple(value.strip() for value in values if isinstance(value, str) and value.strip())
    if not refs:
        raise InterventionEngineError(error_code)
    return tuple(dict.fromkeys(refs))


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InterventionEngineError("INTERVENTION_CONFIDENCE_INVALID")
    if not 0.0 <= float(value) <= 1.0:
        raise InterventionEngineError("INTERVENTION_CONFIDENCE_INVALID")
    return round(float(value), 6)


__all__ = [
    "GrowthInterventionEngine",
    "InterventionCandidate",
    "InterventionDraft",
    "InterventionEngineError",
]
