"""Application layer for `ImprovementCandidate`: record + list.

No `ActorContext` is threaded through `record_improvement_candidate` on
purpose — unlike every other command in this domain, this one carries no
actor-scoped data at all (see `domain/improvement_candidate.py`'s privacy
invariant), so there is nothing for an actor context to scope. The caller
(`family_need`'s `confirm_family_outcome` route) still authenticates and
authorizes the family-side request through its own `family_need` actor; this
module only ever receives already-de-identified fields.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.improvement_candidate import (
    ComponentShape,
    ImprovementCandidate,
    InterventionTierLabel,
    NeedCategoryLabel,
    OutcomeDecision,
)


class ImprovementCandidateRepository(Protocol):
    async def save_improvement_candidate(self, candidate: ImprovementCandidate) -> None: ...

    async def list_improvement_candidates(self) -> tuple[ImprovementCandidate, ...]: ...


async def record_improvement_candidate(
    repo: ImprovementCandidateRepository,
    *,
    component_id: str,
    component_shape: ComponentShape,
    decision: OutcomeDecision,
    category: NeedCategoryLabel,
    intervention_tier: InterventionTierLabel,
) -> ImprovementCandidate:
    """Write one de-identified "this component did not help" data point.

    Every keyword argument here is already de-identified by the caller
    (component/shape/decision/category/tier are all facts about the need or
    the matched component, never about the family) — this function does not
    accept, and must never be changed to accept, anything that could name a
    family.
    """

    candidate = ImprovementCandidate.record(
        component_id=component_id,
        component_shape=component_shape,
        decision=decision,
        category=category,
        intervention_tier=intervention_tier,
    )
    await repo.save_improvement_candidate(candidate)
    return candidate


async def list_improvement_candidates(
    repo: ImprovementCandidateRepository,
) -> tuple[ImprovementCandidate, ...]:
    return await repo.list_improvement_candidates()


__all__ = [
    "ImprovementCandidateRepository",
    "list_improvement_candidates",
    "record_improvement_candidate",
]
