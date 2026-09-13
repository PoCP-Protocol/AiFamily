"""Multi-Perspective Conflict Engine (AIFAMILY-WM-004A).

Deterministic conflict *detection* only — per ADR-0172, generative models
enter the World Model at WM-004B (Belief Engine), never here. This module
does not decide who is right; it makes disagreement a first-class, durable
object instead of silently averaging or picking a winner between family
members' accounts.

V1 scope (deliberately narrow, matching what the project owner specified for
WM-004A): detects `PERSPECTIVE_CONFLICT` — two atoms about an overlapping
subject/predicate/time window, asserted by different actors, with different
`value_ref`. `SOURCE_DISAGREEMENT`, `TEMPORAL_CONFLICT` and `FACT_CONFLICT`
are declared as valid `ConflictType` values (per the project owner's
taxonomy) but this module does not yet classify into them — inventing
detection heuristics for cases not in the WM-004A spec would be guessing,
not implementing. See `KNOWN_GAPS` in the completion report.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .contracts import ContextContractError, ContextScope
from .world_state import WorldStateAtom, WorldStateEpistemicKind

#: Kinds that represent someone's account of the world, as opposed to a
#: settled authoritative FACT. Conflict detection only considers pairs where
#: at least the disagreement is about what people said/observed — FACT
#: atoms come from a single authoritative source per predicate today, so a
#: FACT-vs-FACT disagreement would indicate a Truth Plane bug, not a family
#: disagreement, and is out of scope for this detector (see KNOWN_GAPS).
_ACCOUNT_KINDS = frozenset(
    {
        WorldStateEpistemicKind.SELF_REPORT,
        WorldStateEpistemicKind.OTHER_REPORT,
        WorldStateEpistemicKind.PERSPECTIVE,
        WorldStateEpistemicKind.OBSERVATION,
    }
)


class ConflictType(StrEnum):
    SOURCE_DISAGREEMENT = "SOURCE_DISAGREEMENT"
    TEMPORAL_CONFLICT = "TEMPORAL_CONFLICT"
    FACT_CONFLICT = "FACT_CONFLICT"
    PERSPECTIVE_CONFLICT = "PERSPECTIVE_CONFLICT"


class ConflictStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ACCEPTED_AMBIGUITY = "ACCEPTED_AMBIGUITY"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class WorldStateConflict:
    """A durable record that two accounts of the same thing disagree.

    Holding both atom refs (never collapsing them into one) is the point —
    a family's differing perspectives are real data about the family
    system, not noise to be resolved away by this layer.
    """

    conflict_id: str
    scope: ContextScope
    predicate: str
    atom_ids: tuple[str, str]
    conflict_type: ConflictType
    detected_at: datetime
    status: ConflictStatus = ConflictStatus.OPEN
    resolution_note: str | None = None

    def __post_init__(self) -> None:
        if not self.conflict_id.strip():
            raise ContextContractError("conflict_id_required")
        if not self.predicate.strip():
            raise ContextContractError("predicate_required")
        if len(self.atom_ids) != 2 or self.atom_ids[0] == self.atom_ids[1]:
            raise ContextContractError("conflict_requires_two_distinct_atom_ids")
        if self.detected_at.tzinfo is None:
            raise ContextContractError("detected_at_requires_timezone")
        if self.status is ConflictStatus.RESOLVED and not self.resolution_note:
            raise ContextContractError("RESOLVED_CONFLICT_REQUIRES_RESOLUTION_NOTE")


def _valid_windows_overlap(a: WorldStateAtom, b: WorldStateAtom) -> bool:
    a_end = a.valid_until or datetime.max.replace(tzinfo=a.valid_from.tzinfo)
    b_end = b.valid_until or datetime.max.replace(tzinfo=b.valid_from.tzinfo)
    return a.valid_from < b_end and b.valid_from < a_end


def _conflict_id(a: WorldStateAtom, b: WorldStateAtom) -> str:
    first, second = sorted((a.atom_id, b.atom_id))
    return f"conflict:{first}:{second}"


def detect_conflicts(
    atoms: tuple[WorldStateAtom, ...],
    *,
    detected_at: datetime,
) -> tuple[WorldStateConflict, ...]:
    """Detect `PERSPECTIVE_CONFLICT` candidates among `atoms`.

    Two atoms conflict when they share the same family, predicate, and at
    least one overlapping subject; their valid-time windows overlap; they
    were asserted by different actors; and their `value_ref` differs. This
    is pure comparison over already-persisted atoms — no model call, no
    judgment about which account is correct.
    """

    conflicts: list[WorldStateConflict] = []
    for i, atom_a in enumerate(atoms):
        for atom_b in atoms[i + 1 :]:
            if atom_a.scope.family_id != atom_b.scope.family_id:
                continue
            if atom_a.predicate != atom_b.predicate:
                continue
            if not (set(atom_a.subject_ids) & set(atom_b.subject_ids)):
                continue
            if atom_a.epistemic_kind not in _ACCOUNT_KINDS:
                continue
            if atom_b.epistemic_kind not in _ACCOUNT_KINDS:
                continue
            if atom_a.asserted_by == atom_b.asserted_by:
                continue
            if atom_a.value_ref == atom_b.value_ref:
                continue
            if not _valid_windows_overlap(atom_a, atom_b):
                continue

            conflicts.append(
                WorldStateConflict(
                    conflict_id=_conflict_id(atom_a, atom_b),
                    scope=atom_a.scope,
                    predicate=atom_a.predicate,
                    atom_ids=tuple(sorted((atom_a.atom_id, atom_b.atom_id))),
                    conflict_type=ConflictType.PERSPECTIVE_CONFLICT,
                    detected_at=detected_at,
                )
            )
    return tuple(conflicts)


__all__ = [
    "ConflictStatus",
    "ConflictType",
    "WorldStateConflict",
    "detect_conflicts",
]
