"""FamilyBeliefState (AIFAMILY-WM-005).

Composes the pieces WM-001~004C already built into the one object an Agent
actually reads: `Atom Store -> Belief Engine -> FamilyBeliefState -> Task
Context Projector -> ContextSnapshot -> Agent` (Agents never read the Atom
Store directly).

`FamilyBeliefState` wraps the existing `FamilyWorldStateSnapshot` (WM-001)
rather than duplicating its scope/consent/temporal contract — it adds the
two things that snapshot alone doesn't carry: detected conflicts (WM-004A)
and a categorical breakdown by epistemic kind, so a caller does not have to
re-filter `snapshot.atoms` by hand every time.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conflict_engine import ConflictStatus, WorldStateConflict
from .contracts import ContextScopeError
from .world_state import (
    FamilyWorldStateSnapshot,
    UnknownStatus,
    WorldStateEpistemicKind,
)


@dataclass(frozen=True, slots=True)
class FamilyBeliefState:
    """ "As of this moment, given current evidence, scope and detected
    disagreements, this is what we believe about this family" — the
    Belief Engine's actual output object, not a synonym for the raw
    snapshot."""

    snapshot: FamilyWorldStateSnapshot
    conflicts: tuple[WorldStateConflict, ...] = ()

    def __post_init__(self) -> None:
        for conflict in self.conflicts:
            if conflict.scope.family_id != self.snapshot.scope.family_id:
                raise ContextScopeError("CROSS_FAMILY_WORLD_STATE_READ")
            if conflict.scope.tenant_id != self.snapshot.scope.tenant_id:
                raise ContextScopeError("CROSS_TENANT_WORLD_STATE_READ")

    @property
    def facts(self):
        return self._by_kind(WorldStateEpistemicKind.FACT)

    @property
    def observations(self):
        return self._by_kind(WorldStateEpistemicKind.OBSERVATION)

    @property
    def self_reports(self):
        return self._by_kind(WorldStateEpistemicKind.SELF_REPORT)

    @property
    def other_reports(self):
        return self._by_kind(WorldStateEpistemicKind.OTHER_REPORT)

    @property
    def perspectives(self):
        return self._by_kind(WorldStateEpistemicKind.PERSPECTIVE)

    @property
    def hypotheses(self):
        return self._by_kind(WorldStateEpistemicKind.HYPOTHESIS)

    @property
    def open_unknowns(self):
        return tuple(u for u in self.snapshot.unknowns if u.status is UnknownStatus.OPEN)

    @property
    def open_conflicts(self):
        return tuple(c for c in self.conflicts if c.status is ConflictStatus.OPEN)

    def _by_kind(self, kind: WorldStateEpistemicKind):
        return tuple(a for a in self.snapshot.atoms if a.epistemic_kind is kind)


def assemble_belief_state(
    snapshot: FamilyWorldStateSnapshot,
    conflicts: tuple[WorldStateConflict, ...] = (),
) -> FamilyBeliefState:
    """Pure assembly — no I/O. The caller (query_service.py) is responsible
    for actually fetching the snapshot's atoms/unknowns and the conflicts
    from their respective repositories; this function only composes what
    it is handed."""

    return FamilyBeliefState(snapshot=snapshot, conflicts=conflicts)


__all__ = ["FamilyBeliefState", "assemble_belief_state"]
