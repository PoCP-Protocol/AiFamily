"""Quality evaluation for generated family-problem understanding drafts.

The evaluator never generates a family-facing answer.  It scores a model draft
against case-owned evidence, reviewed knowledge and conversation lineage so
prompt/model variants can be compared with repeatable synthetic or anonymous
gold cases.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backend.intelligence.experience.multimodal_eval import (
    GoldCase,
    MultimodalAdapterResult,
    MultimodalEvalError,
)

_GENERIC_PHRASES = (
    "我理解你的感受",
    "每个家庭都不容易",
    "这是一个很常见的问题",
    "建议多沟通",
    "保持耐心",
    "慢慢来",
)


@dataclass(frozen=True, slots=True)
class FamilyUnderstandingEvalSpec:
    """Case-owned references and lineage used to judge one generated draft."""

    allowed_evidence_refs: frozenset[str]
    allowed_knowledge_refs: frozenset[str]
    expected_signal_terms: tuple[frozenset[str], ...] = ()
    prior_hypothesis_statements: tuple[str, ...] = ()
    requires_revision: bool = False
    parent_felt_understood: float | None = None
    parent_feedback_evidence_status: str = "NOT_MEASURED"
    parent_feedback_response_count: int = 0
    parent_feedback_coverage_rate: float | None = None
    parent_feedback_rating_distribution: tuple[tuple[int, int], ...] = ()
    parent_feedback_high_understanding_rate: float | None = None
    parent_feedback_low_understanding_rate: float | None = None

    def __post_init__(self) -> None:
        if not self.allowed_evidence_refs:
            raise MultimodalEvalError("family understanding eval requires evidence refs")
        if any(not ref.strip() for ref in self.allowed_evidence_refs):
            raise MultimodalEvalError("evidence refs must be non-empty")
        if any(not ref.strip() for ref in self.allowed_knowledge_refs):
            raise MultimodalEvalError("knowledge refs must be non-empty")
        if any(
            not terms or any(not term.strip() for term in terms)
            for terms in self.expected_signal_terms
        ):
            raise MultimodalEvalError("expected signal terms must be non-empty")
        if self.requires_revision and not self.prior_hypothesis_statements:
            raise MultimodalEvalError("revision evaluation requires prior hypotheses")
        if (
            self.parent_felt_understood is not None
            and not 0.0 <= self.parent_felt_understood <= 1.0
        ):
            raise MultimodalEvalError("parent feedback must be between 0 and 1")
        if self.parent_feedback_response_count < 0:
            raise MultimodalEvalError("parent feedback response count must be non-negative")


@dataclass(frozen=True, slots=True)
class FamilyUnderstandingQualityReport:
    """Explainable dimensions behind one aggregate quality score."""

    evidence_grounding: float
    knowledge_grounding: float
    hypothesis_quality: float
    follow_up_information_gain: float
    revision_quality: float
    strengths_and_goal_grounding: float
    parent_felt_understood: float | None
    generic_response_penalty: float
    unsupported_certainty_penalty: float

    @property
    def score(self) -> float:
        weighted = (
            self.evidence_grounding * 0.22
            + self.knowledge_grounding * 0.10
            + self.hypothesis_quality * 0.20
            + self.follow_up_information_gain * 0.16
            + self.revision_quality * 0.12
            + self.strengths_and_goal_grounding * 0.12
        )
        feedback_weight = 0.08 if self.parent_felt_understood is not None else 0.0
        if self.parent_felt_understood is not None:
            weighted += self.parent_felt_understood * feedback_weight
        normalizer = 0.92 + feedback_weight
        penalties = self.generic_response_penalty + self.unsupported_certainty_penalty
        return round(max(0.0, min(1.0, weighted / normalizer - penalties)), 6)


class FamilyProblemUnderstandingEvaluator:
    """Callable quality evaluator compatible with ``MultimodalEvalRunner``."""

    def __init__(self, specs: Mapping[str, FamilyUnderstandingEvalSpec]) -> None:
        if not specs:
            raise MultimodalEvalError("at least one family understanding eval spec is required")
        self._specs = dict(specs)

    def __call__(self, case: GoldCase, result: MultimodalAdapterResult) -> float:
        return self.evaluate(case, result).score

    def evaluate(
        self, case: GoldCase, result: MultimodalAdapterResult
    ) -> FamilyUnderstandingQualityReport:
        try:
            spec = self._specs[case.case_id]
        except KeyError as exc:
            raise MultimodalEvalError(f"missing eval spec for case {case.case_id!r}") from exc
        if result.refused or result.output is None:
            return _zero_report(spec.parent_felt_understood)

        output = result.output
        hypotheses = _objects(output.get("hypotheses"))
        unknowns = _objects(output.get("unknowns"))
        questions = _objects(output.get("follow_up_questions"))
        strengths = _objects(output.get("strengths"))
        desired_change = _object(output.get("desired_change"))

        cited_evidence = {
            str(item.get("source_ref", ""))
            for hypothesis in hypotheses
            for item in _objects(hypothesis.get("evidence"))
        }
        cited_evidence.update(
            str(ref) for strength in strengths for ref in _strings(strength.get("evidence_refs"))
        )
        evidence_grounding = _reference_score(cited_evidence, spec.allowed_evidence_refs)

        cited_knowledge = {
            ref for hypothesis in hypotheses for ref in _strings(hypothesis.get("knowledge_refs"))
        }
        knowledge_grounding = _reference_score(
            cited_knowledge, spec.allowed_knowledge_refs, empty_allowed_score=1.0
        )

        statements = [str(item.get("statement", "")) for item in hypotheses]
        signal_coverage = _signal_coverage(statements, spec.expected_signal_terms)
        diversity = _diversity_score(statements)
        falsifiability = _non_empty_rate(
            str(item.get("disconfirming_evidence_needed", "")) for item in hypotheses
        )
        hypothesis_quality = _mean(signal_coverage, diversity, falsifiability)

        unknown_ids = {str(item.get("unknown_id", "")) for item in unknowns}
        answered_ids = [
            ref for question in questions for ref in _strings(question.get("answers_unknown_ids"))
        ]
        valid_answer_links = _reference_score(set(answered_ids), unknown_ids)
        unique_targets = len(set(answered_ids)) / max(len(answered_ids), 1)
        purposeful = _non_empty_rate(str(item.get("purpose", "")) for item in questions)
        follow_up_information_gain = _mean(valid_answer_links, unique_targets, purposeful)

        revision_quality = _revision_score(statements, spec)
        strengths_grounding = _non_empty_rate(
            ref for item in strengths for ref in _strings(item.get("evidence_refs"))
        )
        goal_grounding = float(
            bool(str(desired_change.get("statement", "")).strip())
            and bool(_strings(desired_change.get("observable_signs")))
            and bool(str(desired_change.get("confirmation_question", "")).strip())
        )
        strengths_and_goal_grounding = _mean(strengths_grounding, goal_grounding)

        all_text = " ".join(_walk_strings(output))
        generic_response_penalty = min(
            0.30, sum(phrase in all_text for phrase in _GENERIC_PHRASES) * 0.075
        )
        unsupported_certainty_penalty = _unsupported_certainty_penalty(hypotheses)
        return FamilyUnderstandingQualityReport(
            evidence_grounding=evidence_grounding,
            knowledge_grounding=knowledge_grounding,
            hypothesis_quality=hypothesis_quality,
            follow_up_information_gain=follow_up_information_gain,
            revision_quality=revision_quality,
            strengths_and_goal_grounding=strengths_and_goal_grounding,
            parent_felt_understood=spec.parent_felt_understood,
            generic_response_penalty=generic_response_penalty,
            unsupported_certainty_penalty=unsupported_certainty_penalty,
        )


def _zero_report(parent_feedback: float | None) -> FamilyUnderstandingQualityReport:
    return FamilyUnderstandingQualityReport(0, 0, 0, 0, 0, 0, parent_feedback, 0, 0)


def _reference_score(
    cited: set[str], allowed: frozenset[str] | set[str], *, empty_allowed_score: float = 0.0
) -> float:
    cited.discard("")
    if not allowed:
        return empty_allowed_score if not cited else 0.0
    if not cited:
        return 0.0
    precision = len(cited & set(allowed)) / len(cited)
    coverage = len(cited & set(allowed)) / len(allowed)
    return _mean(precision, coverage)


def _signal_coverage(statements: list[str], groups: tuple[frozenset[str], ...]) -> float:
    if not groups:
        return 1.0
    text = " ".join(statements).lower()
    return sum(any(term.lower() in text for term in group) for group in groups) / len(groups)


def _diversity_score(statements: list[str]) -> float:
    if len(statements) <= 1:
        return 0.5 if statements else 0.0
    similarities = [
        _jaccard(_features(left), _features(right))
        for index, left in enumerate(statements)
        for right in statements[index + 1 :]
    ]
    return max(0.0, 1.0 - max(similarities, default=1.0))


def _revision_score(statements: list[str], spec: FamilyUnderstandingEvalSpec) -> float:
    if not spec.requires_revision:
        return 1.0
    if not statements:
        return 0.0
    unchanged = max(
        (
            _jaccard(_features(current), _features(prior))
            for current in statements
            for prior in spec.prior_hypothesis_statements
        ),
        default=1.0,
    )
    return max(0.0, 1.0 - unchanged)


def _unsupported_certainty_penalty(hypotheses: list[Mapping[str, Any]]) -> float:
    penalty = 0.0
    for hypothesis in hypotheses:
        confidence = str(hypothesis.get("confidence", ""))
        evidence_count = len(_objects(hypothesis.get("evidence")))
        if confidence == "HIGH" and evidence_count < 2:
            penalty += 0.10
        statement = str(hypothesis.get("statement", ""))
        if re.search(r"(一定|就是|显然|毫无疑问|必然)", statement):
            penalty += 0.10
    return min(0.30, penalty)


def _features(value: str) -> set[str]:
    compact = re.sub(r"\s+", "", value.lower())
    return {compact[index : index + 2] for index in range(max(0, len(compact) - 1))}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _objects(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _object(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    return (
        [item for item in value if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for nested in value.values() for text in _walk_strings(nested)]
    if isinstance(value, list):
        return [text for nested in value for text in _walk_strings(nested)]
    return []


def _non_empty_rate(values: Any) -> float:
    items = list(values)
    return sum(bool(str(item).strip()) for item in items) / len(items) if items else 0.0


def _mean(*values: float) -> float:
    return sum(values) / len(values) if values else 0.0


__all__ = [
    "FamilyProblemUnderstandingEvaluator",
    "FamilyUnderstandingEvalSpec",
    "FamilyUnderstandingQualityReport",
]
