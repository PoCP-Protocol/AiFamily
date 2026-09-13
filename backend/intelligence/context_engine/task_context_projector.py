"""Deterministic Task Context Projector (AIFAMILY-WM-005B, PART E/F/G/H).

    FamilyBeliefState
        -> TaskContextSpec
        -> scope check
        -> predicate filter
        -> epistemic-kind filter
        -> current relevance filter (already true of FamilyBeliefState itself)
        -> deterministic bounded selection
        -> FamilyTaskContext

No `ModelGateway`, no LLM, and no semantic-similarity ranking of any kind
anywhere in this module — Task Context Projection is governance and
information trimming, not reasoning (PART E1). The caller
(`TaskContextSpec`) decides what a task is allowed to read; the model never
does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from .belief_state import FamilyBeliefState
from .contracts import ContextContractError
from .task_context import (
    FamilyContextConflict,
    FamilyContextItem,
    FamilyContextUnknown,
    FamilyTaskContext,
)
from .world_state import WorldStateAtom, WorldStateEpistemicKind

#: A fixed total order used only as a *tiebreaker* dimension in deterministic
#: sorting (PART F) — never a claim about which epistemic kind is "more
#: true". FACT sorts first only because it is the kind least likely to need
#: re-reading once truncation happens; this has no bearing on R9.
_EPISTEMIC_KIND_SORT_ORDER = {
    WorldStateEpistemicKind.FACT: 0,
    WorldStateEpistemicKind.OBSERVATION: 1,
    WorldStateEpistemicKind.SELF_REPORT: 2,
    WorldStateEpistemicKind.OTHER_REPORT: 3,
    WorldStateEpistemicKind.PERSPECTIVE: 4,
    WorldStateEpistemicKind.HYPOTHESIS: 5,
}


@dataclass(frozen=True, slots=True)
class TaskContextSpec:
    """What a given task is allowed to read — decided by the caller, never
    inferred by a model (PART E)."""

    use_case: str
    allowed_predicates: tuple[str, ...]
    allowed_epistemic_kinds: tuple[WorldStateEpistemicKind, ...] = (
        WorldStateEpistemicKind.FACT,
        WorldStateEpistemicKind.OBSERVATION,
        WorldStateEpistemicKind.SELF_REPORT,
        WorldStateEpistemicKind.OTHER_REPORT,
        WorldStateEpistemicKind.PERSPECTIVE,
        WorldStateEpistemicKind.HYPOTHESIS,
    )
    include_conflicts: bool = True
    include_unknowns: bool = True
    max_items: int = 50
    expires_in: timedelta = field(default_factory=lambda: timedelta(minutes=30))

    def __post_init__(self) -> None:
        if not self.use_case.strip():
            raise ContextContractError("TASK_CONTEXT_SPEC_USE_CASE_REQUIRED")
        if not self.allowed_predicates:
            raise ContextContractError("TASK_CONTEXT_SPEC_REQUIRES_ALLOWED_PREDICATES")
        if self.max_items <= 0:
            raise ContextContractError("TASK_CONTEXT_SPEC_MAX_ITEMS_MUST_BE_POSITIVE")
        if self.expires_in.total_seconds() <= 0:
            raise ContextContractError("TASK_CONTEXT_SPEC_EXPIRES_IN_MUST_BE_POSITIVE")


def _sort_key(atom: WorldStateAtom, spec: TaskContextSpec) -> tuple[int, int, str, str]:
    predicate_rank = (
        spec.allowed_predicates.index(atom.predicate)
        if atom.predicate in spec.allowed_predicates
        else len(spec.allowed_predicates)
    )
    kind_rank = _EPISTEMIC_KIND_SORT_ORDER.get(atom.epistemic_kind, 99)
    return (predicate_rank, kind_rank, atom.recorded_at.isoformat(), atom.atom_id)


def _item_from_atom(atom: WorldStateAtom, *, selection_reason: str) -> FamilyContextItem:
    return FamilyContextItem(
        item_ref=atom.atom_id,
        subject_ids=atom.subject_ids,
        predicate=atom.predicate,
        epistemic_kind=atom.epistemic_kind,
        value_ref=atom.value_ref,
        asserted_by=atom.asserted_by,
        attributed_actor_type=atom.attributed_actor_type,
        source_refs=atom.source_refs,
        evidence_refs=atom.evidence_refs,
        provenance=atom.provenance,
        recorded_at=atom.recorded_at,
        support_level=atom.support_level.value if atom.support_level else None,
        contradiction_level=atom.contradiction_level.value if atom.contradiction_level else None,
        uncertainty=atom.uncertainty.value if atom.uncertainty else None,
        selection_reason=selection_reason,
    )


def project_task_context(
    belief_state: FamilyBeliefState,
    spec: TaskContextSpec,
    *,
    context_ref: str,
    provenance: str,
) -> FamilyTaskContext:
    """Pure function, no I/O, no model call — same `(belief_state, spec)`
    always yields the same selected refs in the same order (PART F)."""

    belief_state.snapshot.scope.assert_active()

    allowed_predicates = set(spec.allowed_predicates)
    allowed_kinds = set(spec.allowed_epistemic_kinds)

    candidate_atoms = [
        atom
        for atom in belief_state.snapshot.atoms
        if atom.predicate in allowed_predicates and atom.epistemic_kind in allowed_kinds
    ]
    candidate_atoms.sort(key=lambda a: _sort_key(a, spec))
    selected_atoms = candidate_atoms[: spec.max_items]
    selected_ids = {a.atom_id for a in selected_atoms}

    items = tuple(
        _item_from_atom(atom, selection_reason=f"matched_predicate:{atom.predicate}")
        for atom in selected_atoms
    )

    conflicts: tuple[FamilyContextConflict, ...] = ()
    if spec.include_conflicts:
        included_conflicts = []
        for conflict in belief_state.effective_open_conflicts:
            # PART G: a conflict pair is either both included or both
            # excluded — never split, even under max_items truncation.
            if set(conflict.atom_ids).issubset(selected_ids):
                pair = (conflict.atom_ids[0], conflict.atom_ids[1])
                included_conflicts.append(
                    FamilyContextConflict(
                        conflict_ref=conflict.conflict_id,
                        predicate=conflict.predicate,
                        atom_item_refs=pair,
                        conflict_type=conflict.conflict_type.value,
                    )
                )
        conflicts = tuple(included_conflicts)

    unknowns: tuple[FamilyContextUnknown, ...] = ()
    if spec.include_unknowns:
        included_unknowns = []
        for unknown in belief_state.effective_open_unknowns:
            if (
                unknown.target_predicate is not None
                and unknown.target_predicate not in allowed_predicates
            ):
                continue
            included_unknowns.append(
                FamilyContextUnknown(
                    unknown_ref=unknown.unknown_id,
                    question=unknown.question,
                    why_it_matters=unknown.why_it_matters,
                    target_predicate=unknown.target_predicate,
                    priority=unknown.priority,
                    blocking_refs=unknown.blocking_refs,
                    preferred_source=unknown.preferred_source,
                )
            )
        unknowns = tuple(included_unknowns)

    source_refs = tuple(
        dict.fromkeys(ref for item in items for ref in (*item.source_refs, *item.evidence_refs))
    )

    read_at = belief_state.snapshot.as_of
    return FamilyTaskContext(
        context_ref=context_ref,
        scope=belief_state.snapshot.scope,
        use_case=spec.use_case,
        read_at=read_at,
        expires_at=read_at + spec.expires_in,
        items=items,
        conflicts=conflicts,
        unknowns=unknowns,
        source_refs=source_refs,
        provenance=provenance,
    )


__all__ = ["TaskContextSpec", "project_task_context"]
