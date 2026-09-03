"""Prepare one knowledge-grounded family-understanding model invocation.

The preparation boundary keeps retrieval, generation inputs and later quality
evaluation on the same evidence set.  This prevents an evaluator from grading
against knowledge or observations that the model never received.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.intelligence.experience.family_problem_understanding_contract import (
    FamilyConversationTurn,
    build_family_problem_understanding_request,
)
from backend.intelligence.experience.family_problem_understanding_eval import (
    FamilyUnderstandingEvalSpec,
)
from backend.intelligence.experience.family_problem_understanding_knowledge import (
    FamilyUnderstandingKnowledgeRetriever,
    FamilyUnderstandingKnowledgeSelection,
)
from backend.intelligence.model_gateway.contracts import DataClass, MediaInput, StructuredRequest
from backend.packages.contracts.evidence import EvidenceLevel


@dataclass(frozen=True, slots=True)
class FamilyProblemUnderstandingPreparation:
    """A single evidence-consistent input for generation and evaluation."""

    request: StructuredRequest
    knowledge_selection: FamilyUnderstandingKnowledgeSelection
    eval_spec: FamilyUnderstandingEvalSpec

    def __post_init__(self) -> None:
        request_knowledge = {
            str(item["knowledge_ref"])
            for item in self.request.payload.get("reviewed_knowledge", ())
        }
        selected_knowledge = set(self.knowledge_selection.trace.selected_claim_ids)
        if request_knowledge != selected_knowledge:
            raise ValueError("request and knowledge selection refs must match")
        if request_knowledge != set(self.eval_spec.allowed_knowledge_refs):
            raise ValueError("request and evaluation knowledge refs must match")
        if set(self.request.input_refs) != set(self.eval_spec.allowed_evidence_refs):
            raise ValueError("request and evaluation evidence refs must match")


class FamilyProblemUnderstandingPreparer:
    """Coordinate reviewed retrieval with the server-owned model contract."""

    def __init__(self, knowledge_retriever: FamilyUnderstandingKnowledgeRetriever) -> None:
        self._knowledge_retriever = knowledge_retriever

    def prepare(
        self,
        *,
        run_id: str,
        data_class: DataClass,
        context_snapshot_ref: str,
        conversation_turns: tuple[FamilyConversationTurn, ...],
        knowledge_scope: str,
        media_inputs: tuple[MediaInput, ...] = (),
        prior_run_id: str | None = None,
        prior_hypothesis_statements: tuple[str, ...] = (),
        expected_signal_terms: tuple[frozenset[str], ...] = (),
        parent_felt_understood: float | None = None,
        minimum_evidence: EvidenceLevel | None = None,
        at: datetime | None = None,
        locale: str = "zh-CN",
    ) -> FamilyProblemUnderstandingPreparation:
        selection = self._knowledge_retriever.retrieve(
            conversation_turns=conversation_turns,
            scope=knowledge_scope,
            minimum_evidence=minimum_evidence,
            at=at,
        )
        request = build_family_problem_understanding_request(
            run_id=run_id,
            data_class=data_class,
            context_snapshot_ref=context_snapshot_ref,
            conversation_turns=conversation_turns,
            media_inputs=media_inputs,
            reviewed_knowledge=selection.excerpts,
            prior_run_id=prior_run_id,
            locale=locale,
        )
        eval_spec = FamilyUnderstandingEvalSpec(
            allowed_evidence_refs=frozenset(request.input_refs),
            allowed_knowledge_refs=frozenset(selection.trace.selected_claim_ids),
            expected_signal_terms=expected_signal_terms,
            prior_hypothesis_statements=prior_hypothesis_statements,
            requires_revision=prior_run_id is not None,
            parent_felt_understood=parent_felt_understood,
        )
        return FamilyProblemUnderstandingPreparation(
            request=request,
            knowledge_selection=selection,
            eval_spec=eval_spec,
        )


__all__ = [
    "FamilyProblemUnderstandingPreparation",
    "FamilyProblemUnderstandingPreparer",
]
