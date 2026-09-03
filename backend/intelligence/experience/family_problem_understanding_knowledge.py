"""Reviewed-knowledge retrieval for generated family understanding.

This module is the narrow bridge between the shared knowledge lifecycle and
the family-problem-understanding model contract.  It does not generate advice
or turn knowledge into family facts.  Only published claims with explicit
applicability and limitations may enter a model request.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from backend.intelligence.experience.family_problem_understanding_contract import (
    FamilyConversationTurn,
    ReviewedKnowledgeExcerpt,
)
from backend.intelligence.knowledge.contracts import KnowledgeClaim
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.packages.contracts.evidence import EvidenceLevel

RelevanceScorer = Callable[[str, KnowledgeClaim], float]


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalTrace:
    """Explainable, content-minimal trace of one retrieval decision."""

    purpose: str
    scope: str
    candidate_count: int
    selected_claim_ids: tuple[str, ...]
    rejected_claim_ids: tuple[str, ...]
    relevance_scores: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class FamilyUnderstandingKnowledgeSelection:
    """Model-ready reviewed excerpts plus their retrieval trace."""

    excerpts: tuple[ReviewedKnowledgeExcerpt, ...]
    trace: KnowledgeRetrievalTrace


class FamilyUnderstandingKnowledgeRetriever:
    """Retrieve bounded, reviewed context for one family conversation."""

    def __init__(
        self,
        registry: KnowledgeRegistry,
        *,
        relevance_scorer: RelevanceScorer | None = None,
        minimum_relevance: float = 0.08,
        max_excerpts: int = 5,
    ) -> None:
        if not 0.0 <= minimum_relevance <= 1.0:
            raise ValueError("minimum_relevance must be between 0 and 1")
        if max_excerpts < 1:
            raise ValueError("max_excerpts must be positive")
        self._registry = registry
        self._relevance_scorer = relevance_scorer or lexical_relevance
        self._minimum_relevance = minimum_relevance
        self._max_excerpts = max_excerpts

    def retrieve(
        self,
        *,
        conversation_turns: Sequence[FamilyConversationTurn],
        scope: str,
        purpose: str = "family_problem_understanding",
        minimum_evidence: EvidenceLevel | None = None,
        at: datetime | None = None,
    ) -> FamilyUnderstandingKnowledgeSelection:
        if not conversation_turns:
            raise ValueError("conversation_turns are required")
        if not scope.strip() or not purpose.strip():
            raise ValueError("scope and purpose are required")
        query = "\n".join(turn.text for turn in conversation_turns)
        candidates = self._registry.retrieve_reviewed(
            purpose=purpose,
            scope=scope,
            minimum_evidence=minimum_evidence,
            establishing_only=False,
            at=at,
        )
        ranked: list[tuple[float, KnowledgeClaim, ReviewedKnowledgeExcerpt]] = []
        rejected: list[str] = []
        scores: list[tuple[str, float]] = []
        for claim in candidates:
            excerpt = _to_reviewed_excerpt(claim)
            if excerpt is None:
                rejected.append(claim.claim_id)
                continue
            score = float(self._relevance_scorer(query, claim))
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"invalid relevance score for {claim.claim_id}")
            scores.append((claim.claim_id, round(score, 6)))
            if score < self._minimum_relevance:
                rejected.append(claim.claim_id)
                continue
            ranked.append((score, claim, excerpt))

        ranked.sort(key=lambda item: (-item[0], item[1].claim_id))
        selected = ranked[: self._max_excerpts]
        rejected.extend(item[1].claim_id for item in ranked[self._max_excerpts :])
        selected_ids = tuple(item[1].claim_id for item in selected)
        return FamilyUnderstandingKnowledgeSelection(
            excerpts=tuple(item[2] for item in selected),
            trace=KnowledgeRetrievalTrace(
                purpose=purpose,
                scope=scope,
                candidate_count=len(candidates),
                selected_claim_ids=selected_ids,
                rejected_claim_ids=tuple(sorted(set(rejected))),
                relevance_scores=tuple(sorted(scores)),
            ),
        )


def lexical_relevance(query: str, claim: KnowledgeClaim) -> float:
    """Portable lexical baseline; production may inject a governed scorer."""

    query_features = _text_features(query)
    claim_features = _text_features(
        " ".join(
            (
                claim.text,
                str(claim.metadata.get("applicability", "")),
                " ".join(str(item) for item in claim.metadata.get("keywords", ())),
            )
        )
    )
    if not query_features or not claim_features:
        return 0.0
    overlap = len(query_features & claim_features)
    precision = overlap / len(claim_features)
    recall = overlap / len(query_features)
    return min(1.0, precision * 0.35 + recall * 0.65)


def _to_reviewed_excerpt(claim: KnowledgeClaim) -> ReviewedKnowledgeExcerpt | None:
    metadata = claim.metadata
    version = metadata.get("version")
    chunk_ref = metadata.get("chunk_ref")
    applicability = metadata.get("applicability")
    limitations = metadata.get("limitations")
    if not all(
        isinstance(value, str) and value.strip() for value in (version, chunk_ref, applicability)
    ):
        return None
    if not isinstance(limitations, (tuple, list)) or not limitations:
        return None
    normalized_limitations = tuple(
        str(item).strip() for item in limitations if isinstance(item, str) and item.strip()
    )
    if len(normalized_limitations) != len(limitations):
        return None
    return ReviewedKnowledgeExcerpt(
        knowledge_ref=claim.claim_id,
        source_ref=claim.source_id,
        version=version,
        chunk_ref=chunk_ref,
        content=claim.text,
        applicability=applicability,
        limitations=normalized_limitations,
    )


def _text_features(value: str) -> set[str]:
    normalized = value.lower()
    latin = set(re.findall(r"[a-z0-9]{2,}", normalized))
    cjk_sequences = re.findall(r"[\u3400-\u9fff]+", normalized)
    cjk = {
        sequence[index : index + 2]
        for sequence in cjk_sequences
        for index in range(max(0, len(sequence) - 1))
    }
    return latin | cjk


__all__ = [
    "FamilyUnderstandingKnowledgeRetriever",
    "FamilyUnderstandingKnowledgeSelection",
    "KnowledgeRetrievalTrace",
    "RelevanceScorer",
    "lexical_relevance",
]
