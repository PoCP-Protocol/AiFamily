"""Application layer for `FamilyExperienceSignal`: record + the "小红书-style"
similar-problem search aggregation.

No `ActorContext` is threaded through `record_family_experience_signal` for
the same reason `record_improvement_candidate` carries none — see
`improvement_candidate.py`'s module docstring. The caller
(`family_need`'s `confirm_family_outcome` route) still authenticates and
authorizes the family-side request through its own actor; this module only
ever receives already-de-identified fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.family_experience_signal import (
    ComponentShape,
    FamilyExperienceSignal,
    InterventionTierLabel,
    NeedCategoryLabel,
    OutcomeDecision,
)

# Below this many signals, `helped_rate` is one or two families' outcome
# dressed up as a percentage — the small-sample-false-consensus failure mode
# that de-identified social-proof surfaces (小红书-style "种草") are prone to.
# A parent-facing renderer must not show `helped_rate` as a confident stat
# when `total_count` is under this floor.
MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE = 5


@dataclass(frozen=True, slots=True)
class ComponentExperienceSummary:
    """Aggregated "did this help families like mine" stats for one
    component within one category — the row a parent's search result
    renders."""

    component_id: str
    category: NeedCategoryLabel
    helped_count: int
    partially_helped_count: int
    did_not_help_count: int
    total_count: int
    helped_rate: float

    @property
    def is_low_confidence(self) -> bool:
        """True when `total_count` is too small for `helped_rate` to mean
        anything — the renderer must show this instead of the raw rate."""

        return self.total_count < MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE


class FamilyExperienceSignalRepository(Protocol):
    async def save_family_experience_signal(self, signal: FamilyExperienceSignal) -> None: ...

    async def list_family_experience_signals(self) -> tuple[FamilyExperienceSignal, ...]: ...

    async def summarize_by_component(
        self, *, category: NeedCategoryLabel
    ) -> tuple[ComponentExperienceSummary, ...]:
        """Group signals in `category` by `component_id` and return the
        helped/partially-helped/did-not-help counts and helped rate for
        each — the aggregation behind "families with a problem like mine
        tried these, and this many said it helped"."""
        ...


async def record_family_experience_signal(
    repo: FamilyExperienceSignalRepository,
    *,
    component_id: str,
    component_shape: ComponentShape,
    decision: OutcomeDecision,
    category: NeedCategoryLabel,
    intervention_tier: InterventionTierLabel,
) -> FamilyExperienceSignal:
    """Write one de-identified "did this help" data point, for any verdict.

    Every keyword argument here is already de-identified by the caller — see
    the domain module's docstring; this function does not accept, and must
    never be changed to accept, anything that could name a family.
    """

    signal = FamilyExperienceSignal.record(
        component_id=component_id,
        component_shape=component_shape,
        decision=decision,
        category=category,
        intervention_tier=intervention_tier,
    )
    await repo.save_family_experience_signal(signal)
    return signal


async def list_family_experience_signals(
    repo: FamilyExperienceSignalRepository,
) -> tuple[FamilyExperienceSignal, ...]:
    return await repo.list_family_experience_signals()


async def summarize_family_experience_by_component(
    repo: FamilyExperienceSignalRepository,
    *,
    category: NeedCategoryLabel,
) -> tuple[ComponentExperienceSummary, ...]:
    """ "Search for a similar problem" query: every component tried by
    families whose need fell under `category`, with how many said it
    helped."""

    return await repo.summarize_by_component(category=category)


__all__ = [
    "ComponentExperienceSummary",
    "FamilyExperienceSignalRepository",
    "list_family_experience_signals",
    "record_family_experience_signal",
    "summarize_family_experience_by_component",
]
