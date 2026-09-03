"""In-memory `ImprovementCandidateRepository` — dev/test wiring.

Mirrors `InMemoryCourseContentRepository`'s "one process-local dict" shape.
No tenant/family scoping exists here by design — see
`domain/improvement_candidate.py`'s privacy invariant: this aggregate is
cross-family and carries no family/tenant identity to scope by.
"""

from __future__ import annotations

from ..domain.improvement_candidate import ImprovementCandidate


class InMemoryImprovementCandidateRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, ImprovementCandidate] = {}

    async def save_improvement_candidate(self, candidate: ImprovementCandidate) -> None:
        self._by_id[candidate.candidate_id] = candidate

    async def list_improvement_candidates(self) -> tuple[ImprovementCandidate, ...]:
        return tuple(sorted(self._by_id.values(), key=lambda item: item.recorded_at, reverse=True))


__all__ = ["InMemoryImprovementCandidateRepository"]
