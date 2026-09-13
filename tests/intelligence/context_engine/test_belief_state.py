"""AIFAMILY-WM-005 acceptance tests: FamilyBeliefState (pure assembly).

No model, no I/O — `assemble_belief_state()` only composes objects the
caller already fetched. Real-Postgres assembly (via the three durable
stores) is covered by `test_belief_state_query_service.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.intelligence.context_engine.belief_state import assemble_belief_state
from backend.intelligence.context_engine.conflict_engine import (
    ConflictStatus,
    ConflictType,
    WorldStateConflict,
)
from backend.intelligence.context_engine.contracts import ContextScope, ContextScopeError, DataClass
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
        "predicate": "family.member_statement",
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


def unknown(**overrides: object) -> UnknownState:
    values: dict[str, object] = {
        "unknown_id": "unk-1",
        "scope": scope(),
        "subject_ids": ("child-1",),
        "question": "q",
        "why_it_matters": "w",
        "status": UnknownStatus.OPEN,
    }
    values.update(overrides)
    return UnknownState(**values)  # type: ignore[arg-type]


def conflict(**overrides: object) -> WorldStateConflict:
    values: dict[str, object] = {
        "conflict_id": "conflict-1",
        "scope": scope(),
        "predicate": "family.member_statement",
        "atom_ids": ("atom-a", "atom-b"),
        "conflict_type": ConflictType.PERSPECTIVE_CONFLICT,
        "detected_at": NOW,
        "status": ConflictStatus.OPEN,
    }
    values.update(overrides)
    return WorldStateConflict(**values)  # type: ignore[arg-type]


def snapshot(**overrides: object) -> FamilyWorldStateSnapshot:
    values: dict[str, object] = {
        "snapshot_ref": "snapshot-1",
        "scope": scope(),
        "as_of": NOW,
        "generated_at": NOW,
    }
    values.update(overrides)
    return FamilyWorldStateSnapshot(**values)  # type: ignore[arg-type]


def test_partitions_atoms_by_epistemic_kind() -> None:
    fact = atom(atom_id="a-fact", epistemic_kind=WorldStateEpistemicKind.FACT)
    observation = atom(atom_id="a-obs", epistemic_kind=WorldStateEpistemicKind.OBSERVATION)
    self_report = atom(atom_id="a-self", epistemic_kind=WorldStateEpistemicKind.SELF_REPORT)
    other_report = atom(atom_id="a-other", epistemic_kind=WorldStateEpistemicKind.OTHER_REPORT)
    perspective = atom(
        atom_id="a-persp",
        epistemic_kind=WorldStateEpistemicKind.PERSPECTIVE,
        source_refs=("conversation:2026-09-13",),
    )
    hypothesis = atom(
        atom_id="a-hyp",
        epistemic_kind=WorldStateEpistemicKind.HYPOTHESIS,
        asserted_by="ai:test",
        attributed_actor_type=WorldStateActorType.AI,
        evidence_refs=("a-self",),
        support_level=BeliefBand.MODERATE,
        contradiction_level=BeliefBand.NONE,
        uncertainty=UncertaintyBand.HIGH,
    )

    state = assemble_belief_state(
        snapshot(atoms=(fact, observation, self_report, other_report, perspective, hypothesis))
    )

    assert state.facts == (fact,)
    assert state.observations == (observation,)
    assert state.self_reports == (self_report,)
    assert state.other_reports == (other_report,)
    assert state.perspectives == (perspective,)
    assert state.hypotheses == (hypothesis,)


def test_open_unknowns_excludes_resolved_and_dismissed() -> None:
    open_one = unknown(unknown_id="unk-open", status=UnknownStatus.OPEN)
    resolved_one = unknown(
        unknown_id="unk-resolved", status=UnknownStatus.RESOLVED, resolution_refs=("atom-x",)
    )
    dismissed_one = unknown(unknown_id="unk-dismissed", status=UnknownStatus.DISMISSED)

    state = assemble_belief_state(snapshot(unknowns=(open_one, resolved_one, dismissed_one)))

    assert state.open_unknowns == (open_one,)


def test_open_conflicts_excludes_resolved() -> None:
    open_conflict = conflict(conflict_id="c-open", status=ConflictStatus.OPEN)
    resolved_conflict = conflict(
        conflict_id="c-resolved", status=ConflictStatus.RESOLVED, resolution_note="clarified"
    )

    state = assemble_belief_state(snapshot(), conflicts=(open_conflict, resolved_conflict))

    assert state.open_conflicts == (open_conflict,)


def test_rejects_conflict_from_a_different_family() -> None:
    foreign_conflict = conflict(scope=scope(family_id="family-2"))

    with pytest.raises(ContextScopeError, match="CROSS_FAMILY_WORLD_STATE_READ"):
        assemble_belief_state(snapshot(), conflicts=(foreign_conflict,))


def test_rejects_conflict_from_a_different_tenant() -> None:
    foreign_conflict = conflict(scope=scope(tenant_id="tenant-2"))

    with pytest.raises(ContextScopeError, match="CROSS_TENANT_WORLD_STATE_READ"):
        assemble_belief_state(snapshot(), conflicts=(foreign_conflict,))
