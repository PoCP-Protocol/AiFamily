"""AIFAMILY-WM-005B acceptance tests: TaskContextSpec + project_task_context().

Pure, deterministic, no model call anywhere in this file — Task Context
Projection is governance/trimming, not reasoning.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.context_engine.belief_state import assemble_belief_state
from backend.intelligence.context_engine.conflict_engine import (
    ConflictStatus,
    ConflictType,
    WorldStateConflict,
)
from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    DataClass,
)
from backend.intelligence.context_engine.task_context_projector import (
    TaskContextSpec,
    project_task_context,
)
from backend.intelligence.context_engine.world_state import (
    BeliefBand,
    FamilyWorldStateSnapshot,
    UncertaintyBand,
    UnknownState,
    UnknownStatus,
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def scope(**overrides: object) -> ContextScope:
    values: dict[str, object] = {
        "tenant_id": "tenant-1",
        "region_id": "CN",
        "family_id": "family-1",
        "subject_ids": ("child-1", "mother-1", "father-1"),
        "purpose": "family_growth_support",
        "consent_version": "consent.v1",
        "consent_granted": True,
        "data_class": DataClass.FAMILY_PRIVATE_TEXT,
        "locale": "zh-CN",
        "deletion_ref": "delete:family-1",
        "correlation_id": "corr-1",
        "causation_id": "cause-1",
    }
    values.update(overrides)
    return ContextScope(**values)  # type: ignore[arg-type]


def atom(**overrides: object) -> WorldStateAtom:
    values: dict[str, object] = {
        "atom_id": "atom-1",
        "scope": scope(),
        "subject_ids": ("child-1",),
        "epistemic_kind": WorldStateEpistemicKind.SELF_REPORT,
        "predicate": "child.parent_communication",
        "value_ref": "child said something",
        "asserted_by": "child-1",
        "attributed_actor_type": WorldStateActorType.FAMILY_MEMBER,
        "provenance": "conversation:2026-09-13",
        "observed_at": NOW,
        "recorded_at": NOW,
        "valid_from": NOW,
    }
    values.update(overrides)
    return WorldStateAtom(**values)  # type: ignore[arg-type]


def conflict(**overrides: object) -> WorldStateConflict:
    values: dict[str, object] = {
        "conflict_id": "conflict-1",
        "scope": scope(),
        "predicate": "child.parent_communication",
        "atom_ids": ("atom-a", "atom-b"),
        "conflict_type": ConflictType.PERSPECTIVE_CONFLICT,
        "detected_at": NOW,
        "status": ConflictStatus.OPEN,
    }
    values.update(overrides)
    return WorldStateConflict(**values)  # type: ignore[arg-type]


def unknown(**overrides: object) -> UnknownState:
    values: dict[str, object] = {
        "unknown_id": "unk-1",
        "scope": scope(),
        "subject_ids": ("child-1",),
        "question": "q",
        "why_it_matters": "w",
        "target_predicate": "child.parent_communication",
        "priority": "HIGH",
        "status": UnknownStatus.OPEN,
    }
    values.update(overrides)
    return UnknownState(**values)  # type: ignore[arg-type]


def snapshot(**overrides: object) -> FamilyWorldStateSnapshot:
    values: dict[str, object] = {
        "snapshot_ref": "snapshot-1",
        "scope": scope(),
        "as_of": NOW,
        "generated_at": NOW,
    }
    values.update(overrides)
    return FamilyWorldStateSnapshot(**values)  # type: ignore[arg-type]


def default_spec(**overrides: object) -> TaskContextSpec:
    values: dict[str, object] = {
        "use_case": "family.communication_understanding",
        "allowed_predicates": ("child.parent_communication",),
    }
    values.update(overrides)
    return TaskContextSpec(**values)  # type: ignore[arg-type]


def test_predicate_and_epistemic_kind_filter() -> None:
    matching = atom(atom_id="a-match", predicate="child.parent_communication")
    wrong_predicate = atom(atom_id="a-wrong-pred", predicate="child.sleep_pattern")

    belief_state = assemble_belief_state(snapshot(atoms=(matching, wrong_predicate)))
    context = project_task_context(
        belief_state, default_spec(), context_ref="ctx-1", provenance="test"
    )

    assert {i.item_ref for i in context.items} == {"a-match"}


def test_hypothesis_epistemic_kind_and_belief_metadata_preserved() -> None:
    hypothesis = atom(
        atom_id="a-hyp",
        epistemic_kind=WorldStateEpistemicKind.HYPOTHESIS,
        asserted_by="ai:test",
        attributed_actor_type=WorldStateActorType.AI,
        evidence_refs=("a-evidence",),
        support_level=BeliefBand.MODERATE,
        contradiction_level=BeliefBand.WEAK,
        uncertainty=UncertaintyBand.HIGH,
    )
    belief_state = assemble_belief_state(snapshot(atoms=(hypothesis,)))
    context = project_task_context(
        belief_state, default_spec(), context_ref="ctx-2", provenance="test"
    )

    assert len(context.items) == 1
    item = context.items[0]
    assert item.epistemic_kind is WorldStateEpistemicKind.HYPOTHESIS
    assert item.epistemic_kind is not WorldStateEpistemicKind.FACT
    assert item.support_level == "MODERATE"
    assert item.contradiction_level == "WEAK"
    assert item.uncertainty == "HIGH"


def test_conflict_pair_included_only_when_both_atoms_selected() -> None:
    atom_a = atom(atom_id="atom-a", predicate="child.parent_communication")
    atom_b = atom(atom_id="atom-b", predicate="child.parent_communication", asserted_by="mother-1")
    pair_conflict = conflict(conflict_id="c-pair", atom_ids=("atom-a", "atom-b"))

    belief_state = assemble_belief_state(
        snapshot(atoms=(atom_a, atom_b)), conflicts=(pair_conflict,)
    )
    context = project_task_context(
        belief_state, default_spec(), context_ref="ctx-3", provenance="test"
    )

    assert len(context.conflicts) == 1
    assert set(context.conflicts[0].atom_item_refs) == {"atom-a", "atom-b"}


def test_conflict_pair_excluded_wholesale_when_max_items_truncates_one_side() -> None:
    """PART G: never include only one side of a conflict pair."""

    atom_a = atom(atom_id="atom-a", predicate="child.parent_communication", recorded_at=NOW)
    atom_b = atom(
        atom_id="atom-b",
        predicate="child.parent_communication",
        asserted_by="mother-1",
        recorded_at=NOW + timedelta(seconds=1),
    )
    pair_conflict = conflict(conflict_id="c-pair", atom_ids=("atom-a", "atom-b"))

    belief_state = assemble_belief_state(
        snapshot(atoms=(atom_a, atom_b)), conflicts=(pair_conflict,)
    )
    context = project_task_context(
        belief_state, default_spec(max_items=1), context_ref="ctx-4", provenance="test"
    )

    assert len(context.items) == 1
    assert context.conflicts == ()


def test_resolved_unknown_excluded() -> None:
    open_one = unknown(unknown_id="unk-open", status=UnknownStatus.OPEN)
    resolved_one = unknown(
        unknown_id="unk-resolved", status=UnknownStatus.RESOLVED, resolution_refs=("atom-x",)
    )

    belief_state = assemble_belief_state(snapshot(unknowns=(open_one, resolved_one)))
    context = project_task_context(
        belief_state, default_spec(), context_ref="ctx-5", provenance="test"
    )

    assert {u.unknown_ref for u in context.unknowns} == {"unk-open"}


def test_unknown_with_unrelated_target_predicate_excluded() -> None:
    matching = unknown(unknown_id="unk-match", target_predicate="child.parent_communication")
    unrelated = unknown(unknown_id="unk-unrelated", target_predicate="child.sleep_pattern")

    belief_state = assemble_belief_state(snapshot(unknowns=(matching, unrelated)))
    context = project_task_context(
        belief_state, default_spec(), context_ref="ctx-6", provenance="test"
    )

    assert {u.unknown_ref for u in context.unknowns} == {"unk-match"}


def test_same_belief_state_and_spec_yields_identical_ordered_context() -> None:
    atoms = tuple(
        atom(atom_id=f"a-{i}", predicate="child.parent_communication", asserted_by=f"actor-{i}")
        for i in range(5)
    )
    belief_state = assemble_belief_state(snapshot(atoms=atoms))
    spec = default_spec()

    first = project_task_context(belief_state, spec, context_ref="ctx-7a", provenance="test")
    second = project_task_context(belief_state, spec, context_ref="ctx-7b", provenance="test")

    assert [i.item_ref for i in first.items] == [i.item_ref for i in second.items]


def test_structured_payload_retains_evidence_and_epistemic_kind() -> None:
    hypothesis = atom(
        atom_id="a-hyp-payload",
        epistemic_kind=WorldStateEpistemicKind.HYPOTHESIS,
        asserted_by="ai:test",
        attributed_actor_type=WorldStateActorType.AI,
        evidence_refs=("a-evidence-1",),
        support_level=BeliefBand.STRONG,
        contradiction_level=BeliefBand.NONE,
        uncertainty=UncertaintyBand.LOW,
    )
    belief_state = assemble_belief_state(snapshot(atoms=(hypothesis,)))
    context = project_task_context(
        belief_state, default_spec(), context_ref="ctx-8", provenance="test"
    )
    payload = context.to_structured_payload()

    assert payload["items"][0]["epistemic_kind"] == "HYPOTHESIS"
    assert payload["items"][0]["evidence_refs"] == ["a-evidence-1"]
    assert payload["items"][0]["support_level"] == "STRONG"
    assert "a-evidence-1" in context.source_refs


def test_explain_item_returns_structured_record_not_generated_text() -> None:
    matching = atom(atom_id="a-explain", predicate="child.parent_communication")
    belief_state = assemble_belief_state(snapshot(atoms=(matching,)))
    context = project_task_context(
        belief_state, default_spec(), context_ref="ctx-9", provenance="test"
    )

    record = context.explain_item("a-explain")
    assert record["item_ref"] == "a-explain"
    assert record["predicate"] == "child.parent_communication"
    assert "selection_reason" in record


def test_spec_requires_at_least_one_allowed_predicate() -> None:
    with pytest.raises(ContextContractError, match="TASK_CONTEXT_SPEC_REQUIRES_ALLOWED_PREDICATES"):
        TaskContextSpec(use_case="test", allowed_predicates=())


def test_consent_revoked_scope_cannot_reach_projection() -> None:
    """A revoked-consent scope fails closed at `ContextScope.__post_init__`
    itself — there is no code path that lets a caller build one and then
    separately decide whether to allow projection."""

    with pytest.raises(ContextContractError, match="CONSENT_REVOKED"):
        scope(consent_granted=False)
