"""Prepare one knowledge-grounded family-understanding model invocation.

The preparation boundary keeps retrieval, generation inputs and later quality
evaluation on the same evidence set.  This prevents an evaluator from grading
against knowledge or observations that the model never received.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

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
from backend.intelligence.experience.run_http import RunReplaySnapshot, RunScope
from backend.intelligence.model_gateway.contracts import DataClass, MediaInput, StructuredRequest
from backend.packages.contracts.evidence import EvidenceLevel


class ScopedReplayLedger(Protocol):
    def replay(self, *, scope: RunScope, run_id: str) -> RunReplaySnapshot | Any: ...


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
        prior_draft: Mapping[str, object] | None = None,
        expected_signal_terms: tuple[frozenset[str], ...] = (),
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
            prior_draft=prior_draft,
            locale=locale,
        )
        prior_hypothesis_statements = _hypothesis_statements(prior_draft)
        eval_spec = FamilyUnderstandingEvalSpec(
            allowed_evidence_refs=frozenset(request.input_refs),
            allowed_knowledge_refs=frozenset(selection.trace.selected_claim_ids),
            expected_signal_terms=expected_signal_terms,
            prior_hypothesis_statements=prior_hypothesis_statements,
            requires_revision=prior_run_id is not None,
        )
        return FamilyProblemUnderstandingPreparation(
            request=request,
            knowledge_selection=selection,
            eval_spec=eval_spec,
        )

    async def prepare_follow_up_from_ledger(
        self,
        *,
        ledger: ScopedReplayLedger,
        scope: RunScope,
        prior_run_id: str,
        run_id: str,
        data_class: DataClass,
        context_snapshot_ref: str,
        conversation_turns: tuple[FamilyConversationTurn, ...],
        knowledge_scope: str,
        media_inputs: tuple[MediaInput, ...] = (),
        expected_signal_terms: tuple[frozenset[str], ...] = (),
        minimum_evidence: EvidenceLevel | None = None,
        at: datetime | None = None,
        locale: str = "zh-CN",
    ) -> FamilyProblemUnderstandingPreparation:
        """Load the prior draft through the scoped ledger before revising it."""

        prior_replay = ledger.replay(scope=scope, run_id=prior_run_id)
        if inspect.isawaitable(prior_replay):
            prior_replay = await prior_replay
        if not isinstance(prior_replay, RunReplaySnapshot):
            raise ValueError("prior replay ledger returned an invalid snapshot")
        if prior_replay.scope.key != scope.key:
            raise ValueError("prior replay scope mismatch")
        if prior_replay.deletion_state != "active" or prior_replay.draft_payload is None:
            raise ValueError("prior replay draft is unavailable")
        return self.prepare(
            run_id=run_id,
            data_class=data_class,
            context_snapshot_ref=context_snapshot_ref,
            conversation_turns=conversation_turns,
            knowledge_scope=knowledge_scope,
            media_inputs=media_inputs,
            prior_run_id=prior_run_id,
            prior_draft=prior_replay.draft_payload,
            expected_signal_terms=expected_signal_terms,
            minimum_evidence=minimum_evidence,
            at=at,
            locale=locale,
        )


def _hypothesis_statements(prior_draft: Mapping[str, object] | None) -> tuple[str, ...]:
    if prior_draft is None:
        return ()
    hypotheses = prior_draft.get("hypotheses")
    if not isinstance(hypotheses, list):
        return ()
    statements: list[str] = []
    for item in hypotheses:
        if not isinstance(item, Mapping):
            continue
        statement = item.get("statement")
        if isinstance(statement, str) and statement.strip():
            statements.append(statement)
    return tuple(statements)


__all__ = [
    "FamilyProblemUnderstandingPreparation",
    "FamilyProblemUnderstandingPreparer",
    "ScopedReplayLedger",
]
