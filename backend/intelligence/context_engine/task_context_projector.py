"""Deterministic Task Context Projector (AIFAMILY-WM-005B/C).

    FamilyBeliefState
        -> TaskContextSpec
        -> scope check
        -> predicate allowlist
        -> epistemic-kind allowlist
        -> effective conflict graph (connected-component atomicity)
        -> construct atomic selection bundles
        -> deterministic sort
        -> max_items budgeting by bundle
        -> FamilyTaskContext

No `ModelGateway`, no LLM, and no semantic-similarity ranking of any kind
anywhere in this module — Task Context Projection is governance and
information trimming, not reasoning. The caller (`TaskContextSpec`) decides
what a task is allowed to read; the model never does.

AIFAMILY-WM-005C fixes a real defect in the WM-005B version of this module:
it truncated `candidate_atoms` to `max_items` *before* checking whether a
conflict's two atoms both survived, so a budget boundary could keep one
side of a family disagreement and silently drop the other — the single
worst failure mode this kernel exists to prevent. The unit of selection is
now a *bundle*: either a connected conflict component (every atom any
effective conflict transitively links, e.g. A-B and B-C makes {A, B, C}
one bundle) or a single non-conflicting atom. A bundle is included or
excluded as a whole, never split by either the predicate/epistemic-kind
policy filter or by `max_items` budgeting.
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
#: sorting — never a claim about which epistemic kind is "more true". FACT
#: sorts first only because it is the kind least likely to need re-reading
#: once truncation happens; this has no bearing on R9.
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
    inferred by a model."""

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


@dataclass(frozen=True, slots=True)
class _Bundle:
    """An atomic selection unit: a connected conflict component, or a
    single non-conflicting atom. `conflict_ids` is empty for a singleton."""

    atoms: tuple[WorldStateAtom, ...]
    conflict_ids: tuple[str, ...]


def _predicate_rank(predicate: str, spec: TaskContextSpec) -> int:
    return (
        spec.allowed_predicates.index(predicate)
        if predicate in spec.allowed_predicates
        else len(spec.allowed_predicates)
    )


def _bundle_sort_key(
    bundle: _Bundle, spec: TaskContextSpec
) -> tuple[int, int, str, tuple[str, ...]]:
    predicate_rank = min(_predicate_rank(a.predicate, spec) for a in bundle.atoms)
    kind_rank = min(_EPISTEMIC_KIND_SORT_ORDER.get(a.epistemic_kind, 99) for a in bundle.atoms)
    earliest_recorded_at = min(a.recorded_at.isoformat() for a in bundle.atoms)
    canonical_ids = tuple(sorted(a.atom_id for a in bundle.atoms))
    return (predicate_rank, kind_rank, earliest_recorded_at, canonical_ids)


def _passes_policy(atom: WorldStateAtom, allowed_predicates: set[str], allowed_kinds: set) -> bool:
    return atom.predicate in allowed_predicates and atom.epistemic_kind in allowed_kinds


def _build_bundles(
    belief_state: FamilyBeliefState,
    *,
    allowed_predicates: set[str],
    allowed_kinds: set,
    include_conflicts: bool,
) -> tuple[list[_Bundle], dict[str, list[str]]]:
    """Union-find over `effective_open_conflicts`' atom pairs, producing one
    bundle per connected component plus one bundle per atom that is not
    part of any effective conflict. `item_conflict_ids` maps an atom_id to
    the conflict_ids of every effective conflict it participates in — used
    later to build `selection_reason` for items that survive as part of a
    preserved component.
    """

    atoms_by_id = {a.atom_id: a for a in belief_state.snapshot.atoms}
    parent: dict[str, str] = {}
    item_conflict_ids: dict[str, list[str]] = {}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        parent.setdefault(x, x)
        parent.setdefault(y, y)
        root_x, root_y = find(x), find(y)
        if root_x != root_y:
            parent[root_y] = root_x

    conflicts = belief_state.effective_open_conflicts if include_conflicts else ()
    conflict_atom_ids: set[str] = set()
    for conflict in conflicts:
        a_id, b_id = conflict.atom_ids
        conflict_atom_ids.add(a_id)
        conflict_atom_ids.add(b_id)
        union(a_id, b_id)
        item_conflict_ids.setdefault(a_id, []).append(conflict.conflict_id)
        item_conflict_ids.setdefault(b_id, []).append(conflict.conflict_id)

    components: dict[str, list[str]] = {}
    for atom_id in conflict_atom_ids:
        components.setdefault(find(atom_id), []).append(atom_id)

    bundles: list[_Bundle] = []
    for member_ids in components.values():
        member_atoms = [atoms_by_id[i] for i in sorted(member_ids) if i in atoms_by_id]
        if len(member_atoms) != len(member_ids):
            # A conflict referenced an atom no longer in the current
            # snapshot — `effective_open_conflicts` already guarantees this
            # cannot happen (it only includes conflicts whose atom_ids are
            # a subset of the current snapshot), so this is defensive, not
            # reachable in practice.
            continue
        component_conflict_ids = sorted(
            {cid for member_id in member_ids for cid in item_conflict_ids.get(member_id, [])}
        )
        bundles.append(
            _Bundle(atoms=tuple(member_atoms), conflict_ids=tuple(component_conflict_ids))
        )

    for atom in belief_state.snapshot.atoms:
        if atom.atom_id not in conflict_atom_ids:
            bundles.append(_Bundle(atoms=(atom,), conflict_ids=()))

    # PART C: a bundle is admitted to policy filtering only if EVERY atom in
    # it individually passes — one non-conforming member excludes the whole
    # bundle, never just that member.
    admitted = [
        b
        for b in bundles
        if all(_passes_policy(a, allowed_predicates, allowed_kinds) for a in b.atoms)
    ]
    return admitted, item_conflict_ids


def _item_from_atom(atom: WorldStateAtom, *, conflict_ids: tuple[str, ...]) -> FamilyContextItem:
    if conflict_ids:
        selection_reason = f"conflict_component_preserved:{','.join(conflict_ids)}"
    else:
        selection_reason = f"matched_predicate:{atom.predicate}"
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
    always yields the same selected bundles, refs, and order.

    Budgeting (PART D): bundles are considered in deterministic sort order;
    a bundle is included only if it fits *entirely* within the remaining
    `max_items` budget. A bundle that does not fit is skipped — not
    truncated — and later, smaller bundles are still considered (the
    caller's budget is a hard governance boundary, never auto-expanded to
    fit a bundle that overflows it).
    """

    belief_state.snapshot.scope.assert_active()

    allowed_predicates = set(spec.allowed_predicates)
    allowed_kinds = set(spec.allowed_epistemic_kinds)

    bundles, item_conflict_ids = _build_bundles(
        belief_state,
        allowed_predicates=allowed_predicates,
        allowed_kinds=allowed_kinds,
        include_conflicts=spec.include_conflicts,
    )
    bundles.sort(key=lambda b: _bundle_sort_key(b, spec))

    selected_bundles: list[_Bundle] = []
    remaining_budget = spec.max_items
    for bundle in bundles:
        if len(bundle.atoms) <= remaining_budget:
            selected_bundles.append(bundle)
            remaining_budget -= len(bundle.atoms)

    items: list[FamilyContextItem] = []
    conflicts: list[FamilyContextConflict] = []
    seen_conflict_ids: set[str] = set()
    for bundle in selected_bundles:
        for atom in bundle.atoms:
            items.append(
                _item_from_atom(atom, conflict_ids=tuple(item_conflict_ids.get(atom.atom_id, ())))
            )
        for conflict_id in bundle.conflict_ids:
            if conflict_id in seen_conflict_ids:
                continue
            seen_conflict_ids.add(conflict_id)
            source_conflict = next(
                c for c in belief_state.effective_open_conflicts if c.conflict_id == conflict_id
            )
            conflicts.append(
                FamilyContextConflict(
                    conflict_ref=source_conflict.conflict_id,
                    predicate=source_conflict.predicate,
                    atom_item_refs=(source_conflict.atom_ids[0], source_conflict.atom_ids[1]),
                    conflict_type=source_conflict.conflict_type.value,
                )
            )

    unknowns: list[FamilyContextUnknown] = []
    if spec.include_unknowns:
        for unknown in belief_state.effective_open_unknowns:
            if (
                unknown.target_predicate is not None
                and unknown.target_predicate not in allowed_predicates
            ):
                continue
            unknowns.append(
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
        items=tuple(items),
        conflicts=tuple(conflicts),
        unknowns=tuple(unknowns),
        source_refs=source_refs,
        provenance=provenance,
    )


__all__ = ["TaskContextSpec", "project_task_context"]
