"""FAMILY-SCENE-001 Golden Journey (AIFAMILY-WM-004C, PART C).

End-to-end structural proof that the three World Model components composed
in this increment — Conflict Engine (WM-004A), Belief Engine (WM-004B),
Unknown Engine (WM-004C) — actually chain together the way ADR-0172
describes: deterministic detection -> gated generative hypothesis ->
gated generative information-gap, with every step re-validated
deterministically before it becomes durable state.

Assertions are on STRUCTURE, not on the exact Chinese wording either
FakeProvider response uses — the wording is illustrative synthetic
dialogue, not the thing under test.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import MetaData

from backend.intelligence.context_engine.belief_engine import generate_hypothesis
from backend.intelligence.context_engine.belief_state import assemble_belief_state
from backend.intelligence.context_engine.conflict_engine import ConflictType, detect_conflicts
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.postgres_unknown_repository import (
    PostgresUnknownRepository,
)
from backend.intelligence.context_engine.postgres_world_state_repository import (
    PostgresWorldStateRepository,
)
from backend.intelligence.context_engine.predicate_registry import PredicateRegistry
from backend.intelligence.context_engine.task_context_projector import (
    TaskContextSpec,
    project_task_context,
)
from backend.intelligence.context_engine.unknown_engine import generate_unknown
from backend.intelligence.context_engine.unknown_resolution import resolve_unknown
from backend.intelligence.context_engine.world_state import (
    FamilyWorldStateSnapshot,
    UnknownStatus,
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.safety.runtime import SafetyRuntime
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

NOW = datetime(2026, 9, 13, tzinfo=UTC)

SCENE_TARGET_PREDICATE = "child.parent_communication"
SCENE_ALLOWED_PREDICATES = (SCENE_TARGET_PREDICATE, "child.school_engagement")


def scene_scope(**overrides: object) -> ContextScope:
    values: dict[str, object] = {
        "tenant_id": "tenant-scene-001",
        "region_id": "CN",
        "family_id": "family-scene-001",
        "subject_ids": ("child-1", "mother-1", "father-1"),
        "purpose": "family_growth_support",
        "consent_version": "consent.v1",
        "consent_granted": True,
        "data_class": DataClass.FAMILY_PRIVATE_TEXT,
        "locale": "zh-CN",
        "deletion_ref": "delete:family-scene-001",
        "correlation_id": "family-scene-001",
        "causation_id": "family-scene-001",
    }
    values.update(overrides)
    return ContextScope(**values)  # type: ignore[arg-type]


def _mother_perspective() -> WorldStateAtom:
    return WorldStateAtom(
        atom_id="scene-mother-persp-1",
        scope=scene_scope(),
        subject_ids=("child-1", "mother-1"),
        epistemic_kind=WorldStateEpistemicKind.PERSPECTIVE,
        predicate=SCENE_TARGET_PREDICATE,
        value_ref="妈妈认为孩子最近完全不愿意沟通，一问就回避",
        asserted_by="mother-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
        provenance="conversation:mother:2026-09-13",
        observed_at=NOW,
        recorded_at=NOW,
        valid_from=NOW,
        source_refs=("conversation:mother:2026-09-13",),
    )


def _child_self_report() -> WorldStateAtom:
    return WorldStateAtom(
        atom_id="scene-child-self-1",
        scope=scene_scope(),
        subject_ids=("child-1",),
        epistemic_kind=WorldStateEpistemicKind.SELF_REPORT,
        predicate=SCENE_TARGET_PREDICATE,
        value_ref="孩子说自己愿意聊，但觉得妈妈总是先批评再问原因",
        asserted_by="child-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
        provenance="conversation:child:2026-09-13",
        observed_at=NOW,
        recorded_at=NOW,
        valid_from=NOW,
        source_refs=("conversation:child:2026-09-13",),
    )


def _father_observation() -> WorldStateAtom:
    return WorldStateAtom(
        atom_id="scene-father-obs-1",
        scope=scene_scope(),
        subject_ids=("child-1", "mother-1", "father-1"),
        epistemic_kind=WorldStateEpistemicKind.OBSERVATION,
        predicate=SCENE_TARGET_PREDICATE,
        value_ref="爸爸观察到最近晚饭时母子交流明显变少",
        asserted_by="father-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
        provenance="conversation:father:2026-09-13",
        observed_at=NOW,
        recorded_at=NOW,
        valid_from=NOW,
        source_refs=("conversation:father:2026-09-13",),
    )


def _fake_gateway(responses: dict[str, dict[str, object]]) -> tuple[ModelGateway, str]:
    provider = FakeProvider(responses)
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="staging",
        registry=ProviderRegistry(
            (
                ProviderRecord(
                    provider_id=provider.provider_id,
                    vendor="aifamily-test",
                    model="fake",
                    model_version="1",
                    status="INTERNAL_APPROVED",
                    approved_environments=("staging",),
                    sub_delegates=False,
                    minor_data_allowed=True,
                    private_text_allowed=True,
                    security_assessment_ref="test",
                    processing_agreement_ref="test",
                    deletion_on_termination_committed=True,
                ),
            )
        ),
        safety_runtime=SafetyRuntime(),
    )
    return gateway, provider.provider_id


async def _apply_unknown_migration(engine) -> None:
    def _run_upgrade(sync_connection, migration_module) -> None:
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
        with Operations.context(context):
            migration_module.upgrade()

    for name in (
        "0080_ai_family_world_atoms",
        "0082_ai_family_world_atoms_projection_identity",
        "0083_ai_family_world_atoms_belief_metadata",
        "0084_ai_family_world_unknowns",
    ):
        module = importlib.import_module(f"database.migrations.versions.{name}")
        async with engine.begin() as connection:
            await connection.run_sync(lambda c, m=module: _run_upgrade(c, m))


@pytest.mark.asyncio
@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_family_scene_001_conflict_to_hypothesis_to_unknown() -> None:
    # --- Step 1: three family members' accounts, deliberately disagreeing ---
    mother = _mother_perspective()
    child = _child_self_report()
    father = _father_observation()

    # --- Step 2: Conflict Engine (deterministic, no model) -----------------
    conflicts = detect_conflicts((mother, child, father), detected_at=NOW)
    assert len(conflicts) >= 1
    assert all(c.conflict_type is ConflictType.PERSPECTIVE_CONFLICT for c in conflicts)
    conflicting_ids = {atom_id for c in conflicts for atom_id in c.atom_ids}
    assert mother.atom_id in conflicting_ids
    assert child.atom_id in conflicting_ids

    # No conflict is ever silently resolved into a consensus FACT — every
    # atom the conflict references remains exactly what it was.
    for c in conflicts:
        assert c.status.value == "OPEN"

    # --- Step 3: Belief Engine (gated generative -> HYPOTHESIS only) -------
    registry = PredicateRegistry.from_yaml()
    registry.validate(SCENE_TARGET_PREDICATE)  # sanity: predicate is governed

    belief_gateway, belief_provider_id = _fake_gateway(
        {
            "family_world_state.hypothesis_generation": {
                "statement": "母子沟通模式的分歧可能源于批评先于倾听的互动习惯",
                "support_level": "MODERATE",
                "contradiction_level": "WEAK",
                "uncertainty": "HIGH",
                "evidence_atom_ids": [mother.atom_id, child.atom_id, father.atom_id],
            }
        }
    )
    hypothesis = await generate_hypothesis(
        belief_gateway,
        provider_id=belief_provider_id,
        evidence_atoms=(mother, child, father),
        scope=scene_scope(),
        subject_ids=("child-1", "mother-1", "father-1"),
        context_snapshot_ref="family-scene-001-snapshot",
        proposal_id="scene-proposal-1",
        atom_id="scene-hypothesis-1",
        target_predicate=SCENE_TARGET_PREDICATE,
        now=NOW,
    )

    assert hypothesis.epistemic_kind is WorldStateEpistemicKind.HYPOTHESIS
    assert hypothesis.attributed_actor_type is WorldStateActorType.AI
    assert hypothesis.predicate == SCENE_TARGET_PREDICATE
    assert hypothesis.predicate in SCENE_ALLOWED_PREDICATES
    assert hypothesis.support_level is not None
    assert hypothesis.contradiction_level is not None
    assert hypothesis.uncertainty is not None
    real_evidence_ids = {mother.atom_id, child.atom_id, father.atom_id}
    assert set(hypothesis.evidence_refs) <= real_evidence_ids
    assert set(hypothesis.evidence_refs)  # non-empty: a real grounded hypothesis

    # --- Step 4: Unknown Engine (gated generative -> information gap) ------
    unknown_gateway, unknown_provider_id = _fake_gateway(
        {
            "family_world_state.unknown_generation": {
                "question": "孩子自己认为改善沟通最需要从哪一步开始？",
                "why_it_matters": "直接了解孩子的期待比第三方猜测互动模式更可靠",
                "target_predicate": SCENE_TARGET_PREDICATE,
                "decision_impact": "HIGH",
                "answerability": "MEDIUM",
                "urgency": "MEDIUM",
                "preferred_source": "PARENT_CHILD_INTERVIEW",
                "blocking_hypothesis_ids": [hypothesis.atom_id],
            }
        }
    )
    gap = await generate_unknown(
        unknown_gateway,
        provider_id=unknown_provider_id,
        hypotheses=(hypothesis,),
        allowed_target_predicates=SCENE_ALLOWED_PREDICATES,
        existing_unknowns=(),
        scope=scene_scope(),
        subject_ids=("child-1", "mother-1", "father-1"),
        context_snapshot_ref="family-scene-001-snapshot",
        unknown_id="scene-unknown-1",
        now=NOW,
    )

    assert gap is not None
    assert gap.status is UnknownStatus.OPEN
    assert gap.target_predicate in SCENE_ALLOWED_PREDICATES
    assert hypothesis.atom_id in gap.blocking_refs
    assert gap.decision_impact is not None
    assert gap.answerability is not None
    assert gap.urgency is not None
    assert gap.unknown_key is not None

    # --- Step 5: Unknown is durable, not just an in-memory artifact --------
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        async with engine.begin() as write_connection:
            unknown_repo = PostgresUnknownRepository(write_connection)
            await unknown_repo.create(gap)

        async with engine.begin() as fresh_connection:
            reader = PostgresUnknownRepository(fresh_connection)
            reloaded = await reader.get(gap.unknown_id, scope=scene_scope())
            assert reloaded is not None
            assert reloaded.unknown_key == gap.unknown_key
            assert reloaded.target_predicate == SCENE_TARGET_PREDICATE
            assert hypothesis.atom_id in reloaded.blocking_refs

        # --- Checkpoint 4: Clarification -> Resolution (AIFAMILY-WM-004C.1)
        # "I don't know" -> asks -> family answers -> "I now know more."
        # The mother's new answer is projected as a real OTHER_REPORT atom
        # (recorded strictly after the Unknown was created) before it is
        # ever accepted as resolution evidence.
        mother_clarification = WorldStateAtom(
            atom_id="scene-mother-clarification-1",
            scope=scene_scope(),
            subject_ids=("child-1", "mother-1"),
            epistemic_kind=WorldStateEpistemicKind.OTHER_REPORT,
            predicate=SCENE_TARGET_PREDICATE,
            value_ref="妈妈说其他话题其实还会说，主要是一谈学习就不愿聊",
            asserted_by="mother-1",
            attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
            provenance="conversation:mother:2026-09-14",
            observed_at=NOW + timedelta(days=1),
            recorded_at=NOW + timedelta(days=1),
            valid_from=NOW + timedelta(days=1),
            source_refs=("conversation:mother:2026-09-14",),
        )

        async with engine.begin() as write_connection:
            world_repo = PostgresWorldStateRepository(write_connection)
            await world_repo.append_atom(
                mother_clarification,
                source_ref="conversation:mother:2026-09-14",
                source_version="v1",
                projection_version="family-scene-001-checkpoint-4",
            )

        async with engine.begin() as resolve_connection:
            unknown_repo = PostgresUnknownRepository(resolve_connection)
            world_repo = PostgresWorldStateRepository(resolve_connection)
            resolved = await resolve_unknown(
                unknown_repository=unknown_repo,
                world_state_repository=world_repo,
                unknown_id=gap.unknown_id,
                scope=scene_scope(),
                resolution_atom_ids=(mother_clarification.atom_id,),
                resolved_at=NOW + timedelta(days=1, hours=1),
            )
            assert resolved.status is UnknownStatus.RESOLVED
            assert resolved.resolution_refs == (mother_clarification.atom_id,)

        # --- Checkpoint 5: FamilyBeliefState -> TaskContextProjector -------
        # (AIFAMILY-WM-005B PART J)
        belief_snapshot = FamilyWorldStateSnapshot(
            snapshot_ref="family-scene-001-belief-snapshot",
            scope=scene_scope(),
            as_of=NOW + timedelta(days=1, hours=1),
            generated_at=NOW + timedelta(days=1, hours=1),
            atoms=(mother, child, father, hypothesis, mother_clarification),
            unknowns=(resolved,),
        )
        belief_state = assemble_belief_state(belief_snapshot, conflicts=conflicts)

        task_spec = TaskContextSpec(
            use_case="family.communication_understanding",
            allowed_predicates=(SCENE_TARGET_PREDICATE,),
        )
        task_context = project_task_context(
            belief_state,
            task_spec,
            context_ref="family-scene-001-task-context-1",
            provenance="family-scene-001:checkpoint-5",
        )

        item_refs = {item.item_ref for item in task_context.items}
        assert mother.atom_id in item_refs  # mother's PERSPECTIVE retained
        assert child.atom_id in item_refs  # child's SELF_REPORT retained
        assert father.atom_id in item_refs  # father's OBSERVATION retained
        assert hypothesis.atom_id in item_refs  # AI HYPOTHESIS retained

        hypothesis_item = next(i for i in task_context.items if i.item_ref == hypothesis.atom_id)
        assert hypothesis_item.epistemic_kind is WorldStateEpistemicKind.HYPOTHESIS
        assert hypothesis_item.epistemic_kind is not WorldStateEpistemicKind.FACT
        assert hypothesis_item.support_level is not None

        # The original mother-vs-child conflict survived into the task
        # context as a whole pair, never split.
        assert any(
            set(c.atom_item_refs) == {mother.atom_id, child.atom_id} for c in task_context.conflicts
        )

        # The now-RESOLVED Unknown must not appear in the task context.
        assert task_context.unknowns == ()
