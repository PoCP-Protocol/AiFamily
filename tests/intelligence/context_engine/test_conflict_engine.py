"""AIFAMILY-WM-004A acceptance tests: Multi-Perspective Conflict Engine.

Pure detection tests (no I/O, no model call) — per ADR-0172, this layer must
stay deterministic; WM-004B (Belief Engine) is where generative reasoning
enters.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.intelligence.context_engine.conflict_engine import (
    ConflictStatus,
    ConflictType,
    WorldStateConflict,
    detect_conflicts,
)
from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    DataClass,
)
from backend.intelligence.context_engine.world_state import (
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
        "epistemic_kind": WorldStateEpistemicKind.PERSPECTIVE,
        "predicate": "family.member_statement",
        "value_ref": "statement",
        "asserted_by": "mother-1",
        "attributed_actor_type": WorldStateActorType.FAMILY_MEMBER,
        "provenance": "conversation:2026-09-13",
        "observed_at": NOW,
        "recorded_at": NOW,
        "valid_from": NOW,
        "source_refs": ("conversation:2026-09-13",),
    }
    values.update(overrides)
    return WorldStateAtom(**values)  # type: ignore[arg-type]


# --- Core scenario: mother/child disagree on conflict frequency ------------


def test_detects_perspective_conflict_between_mother_and_child() -> None:
    mother_statement = atom(
        atom_id="mother-1-statement",
        subject_ids=("child-1", "mother-1"),
        predicate="family.conflict_frequency",
        value_ref="几乎每天都吵",
        asserted_by="mother-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
    )
    child_statement = atom(
        atom_id="child-1-statement",
        subject_ids=("child-1", "mother-1"),
        predicate="family.conflict_frequency",
        value_ref="一个星期最多一次",
        asserted_by="child-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
    )

    conflicts = detect_conflicts((mother_statement, child_statement), detected_at=NOW)

    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.conflict_type is ConflictType.PERSPECTIVE_CONFLICT
    assert conflict.status is ConflictStatus.OPEN
    assert set(conflict.atom_ids) == {"mother-1-statement", "child-1-statement"}
    # Neither account is discarded, averaged, or picked as "the real one" —
    # detecting a conflict does not resolve it.


def test_does_not_average_or_pick_a_winner() -> None:
    """The detector's output is a conflict record referencing both atoms —
    there is no code path that produces a single merged/averaged value."""

    mother_statement = atom(
        atom_id="mother-2-statement",
        predicate="family.conflict_frequency",
        value_ref="几乎每天都吵",
        asserted_by="mother-1",
    )
    child_statement = atom(
        atom_id="child-2-statement",
        predicate="family.conflict_frequency",
        value_ref="一个星期最多一次",
        asserted_by="child-1",
    )
    conflicts = detect_conflicts((mother_statement, child_statement), detected_at=NOW)
    assert len(conflicts) == 1
    # WorldStateConflict has no "resolved_value"/"average" field at all.
    assert not hasattr(conflicts[0], "resolved_value")
    assert not hasattr(conflicts[0], "average")


# --- Negative cases: what must NOT be flagged as a conflict ----------------


def test_same_asserted_by_is_not_a_conflict() -> None:
    """The same person contradicting themselves over time is a candidate for
    supersession (WM-001), not a multi-perspective conflict."""

    first = atom(atom_id="mother-a", predicate="family.conflict_frequency", value_ref="每天")
    second = atom(atom_id="mother-b", predicate="family.conflict_frequency", value_ref="一周一次")
    assert detect_conflicts((first, second), detected_at=NOW) == ()


def test_different_predicate_is_not_a_conflict() -> None:
    first = atom(predicate="family.conflict_frequency", value_ref="每天", asserted_by="mother-1")
    second = atom(predicate="child.sleep_pattern", value_ref="正常", asserted_by="child-1")
    assert detect_conflicts((first, second), detected_at=NOW) == ()


def test_fact_atoms_are_never_flagged_as_conflicting() -> None:
    """FACT comes from a single authoritative source per predicate — a
    FACT-vs-FACT disagreement would be a Truth Plane bug, not a family
    disagreement, and is out of scope for this detector."""

    first = atom(
        epistemic_kind=WorldStateEpistemicKind.FACT,
        predicate="family.member_of",
        value_ref="family-1",
        asserted_by="system:family-domain",
        attributed_actor_type=WorldStateActorType.SYSTEM,
    )
    second = atom(
        epistemic_kind=WorldStateEpistemicKind.FACT,
        predicate="family.member_of",
        value_ref="family-2",
        asserted_by="system:other-domain",
        attributed_actor_type=WorldStateActorType.SYSTEM,
    )
    assert detect_conflicts((first, second), detected_at=NOW) == ()


def test_non_overlapping_valid_time_is_not_a_conflict() -> None:
    first = atom(
        predicate="family.conflict_frequency",
        value_ref="每天",
        asserted_by="mother-1",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2026, 3, 1, tzinfo=UTC),
    )
    second = atom(
        predicate="family.conflict_frequency",
        value_ref="一周一次",
        asserted_by="child-1",
        valid_from=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert detect_conflicts((first, second), detected_at=NOW) == ()


def test_no_subject_overlap_is_not_a_conflict() -> None:
    first = atom(
        subject_ids=("child-1",),
        predicate="family.conflict_frequency",
        value_ref="每天",
        asserted_by="mother-1",
    )
    second = atom(
        subject_ids=("father-1",),
        predicate="family.conflict_frequency",
        value_ref="一周一次",
        asserted_by="child-1",
    )
    assert detect_conflicts((first, second), detected_at=NOW) == ()


def test_identical_value_is_not_a_conflict() -> None:
    """Two different people agreeing is not a conflict."""

    first = atom(predicate="family.conflict_frequency", value_ref="每天", asserted_by="mother-1")
    second = atom(predicate="family.conflict_frequency", value_ref="每天", asserted_by="father-1")
    assert detect_conflicts((first, second), detected_at=NOW) == ()


# --- Conflict object invariants ---------------------------------------------


def test_conflict_status_supports_accepted_ambiguity() -> None:
    conflict = WorldStateConflict(
        conflict_id="conflict:a:b",
        scope=scope(),
        predicate="family.conflict_frequency",
        atom_ids=("a", "b"),
        conflict_type=ConflictType.PERSPECTIVE_CONFLICT,
        detected_at=NOW,
        status=ConflictStatus.ACCEPTED_AMBIGUITY,
    )
    assert conflict.status is ConflictStatus.ACCEPTED_AMBIGUITY


def test_resolved_conflict_requires_resolution_note() -> None:
    with pytest.raises(ContextContractError, match="RESOLVED_CONFLICT_REQUIRES_RESOLUTION_NOTE"):
        WorldStateConflict(
            conflict_id="conflict:a:b",
            scope=scope(),
            predicate="family.conflict_frequency",
            atom_ids=("a", "b"),
            conflict_type=ConflictType.PERSPECTIVE_CONFLICT,
            detected_at=NOW,
            status=ConflictStatus.RESOLVED,
        )


def test_conflict_id_is_deterministic_regardless_of_atom_order() -> None:
    mother_statement = atom(atom_id="mother-x", predicate="p", value_ref="a", asserted_by="m")
    child_statement = atom(atom_id="child-x", predicate="p", value_ref="b", asserted_by="c")

    forward = detect_conflicts((mother_statement, child_statement), detected_at=NOW)
    backward = detect_conflicts((child_statement, mother_statement), detected_at=NOW)

    assert forward[0].conflict_id == backward[0].conflict_id
