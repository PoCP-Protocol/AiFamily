"""A real, context-driven `CapabilityCandidatePort` implementation.

Replaces the development-only fixed-pool port
(`ReviewedDevelopmentCapabilityPort` in the HTTP composition — see
contracts.py's docstring warning) with one that genuinely varies by context:
deterministic registry retrieval decides *which* claims are eligible for a
family (knowledge_candidate_source.py), and a Model Gateway call rewords
each retrieved claim into a candidate (candidate_explanation_adapter.py). No
candidate can appear that is not already a published KnowledgeClaim.
"""

from __future__ import annotations

from backend.intelligence.knowledge.registry import KnowledgeRegistry

from .candidate_explanation_adapter import GatewayBackedCandidateExplanationAdapter
from .contracts import CapabilityCandidate, FamilyPathContext, PathDraftEvidence
from .knowledge_candidate_source import retrieve_candidate_claims


class KnowledgeBackedCapabilityCandidatePort:
    """Genuinely context-driven: empty registry result means empty candidates.

    Does not fall back to a fixed pool when the registry has nothing for a
    family's context — that would silently reintroduce the fixed-pool
    problem this class exists to fix. An empty result here is a correct
    signal, not a failure: the caller's planner already has a clarification
    path for it (see test_unknown_context_returns_clarification_without_selecting_action).
    """

    def __init__(
        self,
        registry: KnowledgeRegistry,
        explanation_adapter: GatewayBackedCandidateExplanationAdapter,
    ) -> None:
        self._registry = registry
        self._explanation_adapter = explanation_adapter

    async def list_candidates(
        self, *, scope, context: FamilyPathContext
    ) -> tuple[CapabilityCandidate, ...]:
        claims = retrieve_candidate_claims(self._registry, context=context)
        candidates: list[CapabilityCandidate] = []
        for claim in claims:
            draft = await self._explanation_adapter.explain(
                claim_text=claim.text,
                fit_tags=context.fit_tags,
                context_snapshot_ref=context.context_snapshot_ref,
            )
            candidates.append(
                CapabilityCandidate(
                    capability_ref=f"knowledge:{claim.claim_id}",
                    title=draft.output["title"],
                    description=draft.output["description"],
                    fit_tags=context.fit_tags,
                    evidence=(
                        PathDraftEvidence(
                            ref=claim.claim_id,
                            kind="knowledge_claim",
                            version="v1",
                            excerpt=claim.text,
                        ),
                    ),
                )
            )
        return tuple(candidates)


__all__ = ["KnowledgeBackedCapabilityCandidatePort"]
