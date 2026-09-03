"""In-memory `FamilyExperienceSignalRepository` — dev/test wiring.

Mirrors `InMemoryImprovementCandidateRepository`'s "one process-local dict"
shape. No tenant/family scoping exists here by design — see
`domain/family_experience_signal.py`'s privacy invariant: this aggregate is
cross-family and carries no family/tenant identity to scope by.

`summarize_by_component` aggregates in Python rather than SQL because this
repository's whole dataset is a dev/test-sized in-memory dict; the real
GROUP BY aggregation lives in
`family_experience_signal_postgres_repository.py`, which is what production
and the gated round-trip test actually exercise.
"""

from __future__ import annotations

from collections import defaultdict

from ..application.family_experience_signal import ComponentExperienceSummary
from ..domain.family_experience_signal import FamilyExperienceSignal, NeedCategoryLabel


class InMemoryFamilyExperienceSignalRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, FamilyExperienceSignal] = {}

    async def save_family_experience_signal(self, signal: FamilyExperienceSignal) -> None:
        self._by_id[signal.signal_id] = signal

    async def list_family_experience_signals(self) -> tuple[FamilyExperienceSignal, ...]:
        return tuple(sorted(self._by_id.values(), key=lambda item: item.recorded_at, reverse=True))

    async def summarize_by_component(
        self, *, category: NeedCategoryLabel
    ) -> tuple[ComponentExperienceSummary, ...]:
        counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"HELPED": 0, "PARTIALLY_HELPED": 0, "DID_NOT_HELP": 0}
        )
        for signal in self._by_id.values():
            if signal.category != category:
                continue
            counts[signal.component_id][signal.decision] += 1

        summaries = []
        for component_id, tally in counts.items():
            helped = tally["HELPED"]
            partially = tally["PARTIALLY_HELPED"]
            did_not_help = tally["DID_NOT_HELP"]
            total = helped + partially + did_not_help
            summaries.append(
                ComponentExperienceSummary(
                    component_id=component_id,
                    category=category,
                    helped_count=helped,
                    partially_helped_count=partially,
                    did_not_help_count=did_not_help,
                    total_count=total,
                    helped_rate=(helped / total) if total > 0 else 0.0,
                )
            )
        return tuple(sorted(summaries, key=lambda item: item.total_count, reverse=True))


__all__ = ["InMemoryFamilyExperienceSignalRepository"]
