"""AIFAMILY-FIC-002A acceptance tests for the Family World State Kernel.

Three required scenarios (multi-perspective, hypothesis boundary, unknown as
first-class object) plus the kernel's structural invariants.
"""

from datetime import UTC, datetime

import pytest

from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    ContextScopeError,
    DataClass,
)
from backend.intelligence.context_engine.world_state import (
    FamilyWorldStateSnapshot,
    UnknownState,
    UnknownStatus,
    WorldStateActorType,
    WorldStateAtom,
    WorldStateAtomStatus,
    WorldStateEpistemicKind,
    WorldStateProposal,
    promote_proposal_to_atom,
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
        "predicate": "statement",
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


# --- Scenario 1: multiple family members, no silent consensus -------------


def test_multi_perspective_scenario_never_produces_a_fact() -> None:
    family_scope = scope()

    child_observation = atom(
        atom_id="obs-child-1",
        scope=family_scope,
        subject_ids=("child-1",),
        epistemic_kind=WorldStateEpistemicKind.SELF_REPORT,
        predicate="statement",
        value_ref="妈妈每天都在逼我",
        asserted_by="child-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
    )
    mother_perspective = atom(
        atom_id="persp-mother-1",
        scope=family_scope,
        subject_ids=("child-1", "mother-1"),
        epistemic_kind=WorldStateEpistemicKind.PERSPECTIVE,
        predicate="assessment",
        value_ref="孩子完全没有自律",
        asserted_by="mother-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
        source_refs=("conversation:mother-2026-09-13",),
    )
    father_observation = atom(
        atom_id="obs-father-1",
        scope=family_scope,
        subject_ids=("child-1", "mother-1", "father-1"),
        epistemic_kind=WorldStateEpistemicKind.OTHER_REPORT,
        predicate="statement",
        value_ref="她们最近总因为学习争吵",
        asserted_by="father-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
    )

    snapshot = FamilyWorldStateSnapshot(
        snapshot_ref="snapshot-1",
        scope=family_scope,
        as_of=NOW,
        generated_at=NOW,
        atoms=(child_observation, mother_perspective, father_observation),
    )

    assert {a.epistemic_kind for a in snapshot.atoms} == {
        WorldStateEpistemicKind.SELF_REPORT,
        WorldStateEpistemicKind.PERSPECTIVE,
        WorldStateEpistemicKind.OTHER_REPORT,
    }
    # The mother's characterization never becomes a FACT anywhere in the
    # snapshot — it stays attributed to her as a PERSPECTIVE.
    assert not any(a.epistemic_kind is WorldStateEpistemicKind.FACT for a in snapshot.atoms)
    fact_like = [a for a in snapshot.atoms if a.value_ref == "孩子完全没有自律"]
    assert all(a.epistemic_kind is WorldStateEpistemicKind.PERSPECTIVE for a in fact_like)


# --- Scenario 2: hypothesis stays a hypothesis without enough evidence -----


def test_hypothesis_without_evidence_is_rejected_not_silently_upgraded() -> None:
    with pytest.raises(ContextContractError, match="DERIVED_STATE_REQUIRES_EVIDENCE"):
        atom(
            atom_id="hyp-1",
            epistemic_kind=WorldStateEpistemicKind.HYPOTHESIS,
            value_ref="近期冲突可能与学习压力相关",
            asserted_by="ai:family-principal",
            attributed_actor_type=WorldStateActorType.AI,
            source_refs=(),
            evidence_refs=(),
        )


def test_hypothesis_with_evidence_remains_a_hypothesis_never_a_fact() -> None:
    hypothesis = atom(
        atom_id="hyp-2",
        epistemic_kind=WorldStateEpistemicKind.HYPOTHESIS,
        value_ref="近期冲突可能与学习压力相关",
        asserted_by="ai:family-principal",
        attributed_actor_type=WorldStateActorType.AI,
        evidence_refs=("obs-child-1", "obs-father-1"),
    )
    assert hypothesis.epistemic_kind is WorldStateEpistemicKind.HYPOTHESIS
    # There is no method on WorldStateAtom that mutates epistemic_kind — the
    # dataclass is frozen, so "becoming a fact" is structurally impossible
    # without minting a brand-new FACT atom, which AI is not permitted to do.
    with pytest.raises(AttributeError):
        hypothesis.epistemic_kind = WorldStateEpistemicKind.FACT  # type: ignore[misc]


def test_ai_cannot_create_a_fact_directly() -> None:
    with pytest.raises(ContextContractError, match="AI_CANNOT_ASSERT_THIS_EPISTEMIC_KIND"):
        atom(
            atom_id="fake-fact-1",
            epistemic_kind=WorldStateEpistemicKind.FACT,
            asserted_by="ai:family-principal",
            attributed_actor_type=WorldStateActorType.AI,
        )


def test_ai_proposal_cannot_target_fact_or_report_kinds() -> None:
    for forbidden_kind in (
        WorldStateEpistemicKind.FACT,
        WorldStateEpistemicKind.OBSERVATION,
        WorldStateEpistemicKind.SELF_REPORT,
        WorldStateEpistemicKind.OTHER_REPORT,
    ):
        with pytest.raises(ContextContractError, match="AI_PROPOSAL_CANNOT_TARGET_THIS_KIND"):
            WorldStateProposal(
                proposal_id="proposal-1",
                scope=scope(),
                subject_ids=("child-1",),
                proposed_kind=forbidden_kind,
                statement="孩子完全没有自律",
                evidence_refs=("obs-1",),
                confidence=0.9,
            )


def test_promoting_a_valid_proposal_yields_a_hypothesis_atom_not_a_fact() -> None:
    proposal = WorldStateProposal(
        proposal_id="proposal-2",
        scope=scope(),
        subject_ids=("child-1",),
        proposed_kind=WorldStateEpistemicKind.HYPOTHESIS,
        statement="近期冲突可能与学习压力相关",
        evidence_refs=("obs-child-1", "obs-father-1"),
        confidence=0.58,
    )
    promoted = promote_proposal_to_atom(
        proposal,
        atom_id="hyp-promoted-1",
        provenance="model-gateway:family-principal:v1",
        observed_at=NOW,
        recorded_at=NOW,
        valid_from=NOW,
    )
    assert promoted.epistemic_kind is WorldStateEpistemicKind.HYPOTHESIS
    assert promoted.attributed_actor_type is WorldStateActorType.AI


# --- Scenario 3: Unknown is a first-class object, never null/false --------


def test_unknown_is_a_first_class_object() -> None:
    unknown = UnknownState(
        unknown_id="unk-1",
        scope=scope(),
        subject_ids=("child-1",),
        question="学校最近是否发生了同伴关系变化？",
        why_it_matters="影响冲突假设的置信度",
    )
    assert unknown.status is UnknownStatus.OPEN
    assert unknown.question
    # Explicitly not representable as a boolean/null sentinel.
    assert not isinstance(unknown, bool)
    assert unknown.resolution_refs == ()


def test_resolved_unknown_requires_resolution_refs() -> None:
    with pytest.raises(ContextContractError, match="RESOLVED_UNKNOWN_REQUIRES_RESOLUTION_REFS"):
        UnknownState(
            unknown_id="unk-2",
            scope=scope(),
            subject_ids=("child-1",),
            question="学校最近是否发生了同伴关系变化？",
            why_it_matters="影响冲突假设的置信度",
            status=UnknownStatus.RESOLVED,
        )


def test_snapshot_carries_unknowns_alongside_atoms() -> None:
    family_scope = scope()
    unknown = UnknownState(
        unknown_id="unk-3",
        scope=family_scope,
        subject_ids=("child-1",),
        question="学校最近是否发生了同伴关系变化？",
        why_it_matters="影响冲突假设的置信度",
        source_refs=("obs-father-1",),
    )
    snapshot = FamilyWorldStateSnapshot(
        snapshot_ref="snapshot-2",
        scope=family_scope,
        as_of=NOW,
        generated_at=NOW,
        unknowns=(unknown,),
    )
    assert snapshot.unknowns == (unknown,)
    assert "obs-father-1" in snapshot.source_refs


# --- Temporal contract (supersession, not mutation) ------------------------


def test_superseding_atom_references_predecessor_without_mutating_it() -> None:
    original = atom(
        atom_id="pref-v1",
        epistemic_kind=WorldStateEpistemicKind.SELF_REPORT,
        value_ref="讨厌数学",
        asserted_by="child-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
        valid_from=datetime(2026, 6, 1, tzinfo=UTC),
        valid_until=datetime(2026, 9, 1, tzinfo=UTC),
    )
    updated = atom(
        atom_id="pref-v2",
        epistemic_kind=WorldStateEpistemicKind.SELF_REPORT,
        value_ref="现在其实挺喜欢数学",
        asserted_by="child-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
        valid_from=datetime(2026, 9, 1, tzinfo=UTC),
        supersedes=original.atom_id,
    )
    assert original.status is WorldStateAtomStatus.ACTIVE
    assert original.value_ref == "讨厌数学"
    assert updated.supersedes == original.atom_id


def test_valid_until_must_follow_valid_from() -> None:
    with pytest.raises(ContextContractError, match="valid_until must follow valid_from"):
        atom(valid_from=NOW, valid_until=NOW)


# --- Scope enforcement -------------------------------------------------


def test_atom_subject_must_be_within_scope() -> None:
    with pytest.raises(ContextScopeError, match="WORLD_STATE_SUBJECT_OUT_OF_SCOPE"):
        atom(subject_ids=("stranger-1",))


def test_atom_not_readable_across_family_boundary() -> None:
    family_a = atom(scope=scope(family_id="family-1"))
    other_family_scope = scope(family_id="family-2", subject_ids=("child-9",))
    with pytest.raises(ContextScopeError, match="CROSS_FAMILY_WORLD_STATE_READ"):
        family_a.assert_readable_by(other_family_scope)


def test_snapshot_rejects_atom_outside_its_own_scope() -> None:
    family_scope = scope()
    foreign_scope = scope(family_id="family-2", subject_ids=("child-9",))
    foreign_atom = atom(scope=foreign_scope, subject_ids=("child-9",))
    with pytest.raises(ContextScopeError, match="CROSS_FAMILY_WORLD_STATE_READ"):
        FamilyWorldStateSnapshot(
            snapshot_ref="snapshot-3",
            scope=family_scope,
            as_of=NOW,
            generated_at=NOW,
            atoms=(foreign_atom,),
        )
