"""Deterministic retrieval seam between a family context and the knowledge registry.

No model call happens in this module. The set of candidates a family may see
is decided entirely by `KnowledgeRegistry.retrieve_reviewed` — published,
verified, in-scope, unexpired claims only. A model is never allowed to
invent a candidate that isn't already a registered claim; see
`candidate_explanation_adapter.py` for the (separate, narrower) step where a
model may only reword an already-retrieved claim's text.
"""

from __future__ import annotations

from backend.intelligence.knowledge.contracts import KnowledgeClaim
from backend.intelligence.knowledge.registry import KnowledgeRegistry

from .contracts import FamilyPathContext

CANDIDATE_GENERATION_PURPOSE = "path_orchestration_candidate_generation"


def scope_candidates_for(context: FamilyPathContext) -> tuple[str, ...]:
    """Map a family's fit tags/unknowns to candidate registry scopes.

    Deliberately simple and reviewable: each fit tag is tried as a scope
    value verbatim, plus a catch-all "general" scope so a family with no
    matching tag-specific claims still gets a chance at general guidance
    before falling back to an empty result. This mapping is expected to grow
    incrementally as real fit-tag taxonomy stabilizes — it is not meant to be
    a complete taxonomy on day one.
    """

    scopes = list(context.fit_tags)
    scopes.append("general")
    return tuple(dict.fromkeys(scopes))


def retrieve_candidate_claims(
    registry: KnowledgeRegistry, *, context: FamilyPathContext
) -> tuple[KnowledgeClaim, ...]:
    """Return published, in-scope claims for this family's context.

    Empty result is a valid, correct outcome — it means the registry has no
    reviewed knowledge for this family's situation yet, not that something
    is broken. The caller (KnowledgeBackedCapabilityCandidatePort) must not
    substitute a fallback candidate when this returns empty.
    """

    seen: dict[str, KnowledgeClaim] = {}
    for scope in scope_candidates_for(context):
        for claim in registry.retrieve_reviewed(
            purpose=CANDIDATE_GENERATION_PURPOSE,
            scope=scope,
        ):
            seen[claim.claim_id] = claim
    return tuple(sorted(seen.values(), key=lambda claim: claim.claim_id))


__all__ = [
    "CANDIDATE_GENERATION_PURPOSE",
    "retrieve_candidate_claims",
    "scope_candidates_for",
]
