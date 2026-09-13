"""AIFAMILY-WM-004C.1 acceptance tests: Unknown Resolution Evidence Gate.

`resolve_unknown()` is the only path allowed to move an Unknown from OPEN to
RESOLVED — every test here goes through it, never through
`PostgresUnknownRepository.mark_resolved()` directly (that primitive is
deliberately policy-free; see its docstring).
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import MetaData

from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    ContextScopeError,
    DataClass,
)
from backend.intelligence.context_engine.postgres_unknown_repository import (
    PostgresUnknownRepository,
)
from backend.intelligence.context_engine.postgres_world_state_repository import (
    PostgresWorldStateRepository,
)
from backend.intelligence.context_engine.unknown_identity import build_unknown_key
from backend.intelligence.context_engine.unknown_resolution import resolve_unknown
from backend.intelligence.context_engine.world_state import (
    BeliefBand,
    UncertaintyBand,
    UnknownState,
    UnknownStatus,
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

NOW = datetime(2026, 9, 13, tzinfo=UTC)
BEFORE_UNKNOWN = NOW - timedelta(days=1)
AFTER_UNKNOWN = NOW + timedelta(hours=1)

TARGET_PREDICATE = "child.parent_communication"


def scope(**overrides: object) -> ContextScope:
    values: dict[str, object] = {
        "tenant_id": "tenant-1",
        "region_id": "CN",
        "family_id": "family-1",
        "subject_ids": ("child-1", "mother-1"),
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


def evidence_atom(**overrides: object) -> WorldStateAtom:
    family_scope = overrides.get("scope", scope())
    values: dict[str, object] = {
        "atom_id": "evidence-1",
        "scope": family_scope,
        "subject_ids": ("child-1",),
        "epistemic_kind": WorldStateEpistemicKind.OTHER_REPORT,
        "predicate": TARGET_PREDICATE,
        "value_ref": "妈妈说其他话题还会聊，主要是一谈学习就不愿聊",
        "asserted_by": "mother-1",
        "attributed_actor_type": WorldStateActorType.FAMILY_MEMBER,
        "provenance": "conversation:mother:2026-09-13",
        "observed_at": AFTER_UNKNOWN,
        "recorded_at": AFTER_UNKNOWN,
        "valid_from": AFTER_UNKNOWN,
        "source_refs": ("conversation:mother:2026-09-13",),
    }
    values.update(overrides)
    return WorldStateAtom(**values)  # type: ignore[arg-type]


def open_unknown(**overrides: object) -> UnknownState:
    family_scope = overrides.get("scope", scope())
    subject_ids = overrides.get("subject_ids", ("child-1",))
    target_predicate = overrides.get("target_predicate", TARGET_PREDICATE)
    blocking_refs = overrides.get("blocking_refs", ("hyp-1",))
    values: dict[str, object] = {
        "unknown_id": "unk-resolution-1",
        "scope": family_scope,
        "subject_ids": subject_ids,
        "question": "除了学习话题之外，孩子在其他话题上的交流是否也减少？",
        "why_it_matters": "区分沟通问题是全面的还是仅限于学习话题",
        "target_predicate": target_predicate,
        "decision_impact": "HIGH",
        "answerability": "MEDIUM",
        "urgency": "MEDIUM",
        "blocking_refs": blocking_refs,
        "unknown_key": build_unknown_key(
            tenant_id=family_scope.tenant_id,
            family_id=family_scope.family_id,
            subject_ids=subject_ids,
            target_predicate=target_predicate,
            blocking_refs=blocking_refs,
            unknown_contract_version="world-model-unknown-engine/v1",
        ),
        "source_refs": blocking_refs,
        "priority": "HIGH",
        "status": UnknownStatus.OPEN,
        "created_at": NOW,
    }
    values.update(overrides)
    return UnknownState(**values)  # type: ignore[arg-type]


async def _apply_migrations(engine) -> None:
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


pytestmark = pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)


async def test_real_new_family_evidence_resolves_unknown() -> None:
    """T1-T6: OPEN -> family provides an answer -> that answer is persisted
    as a real WorldStateAtom -> resolve_unknown() accepts it -> RESOLVED,
    and resolution_refs point at the persisted atom."""

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)

            await unknown_repo.create(open_unknown())
            answer_atom = evidence_atom()
            await world_repo.append_atom(
                answer_atom,
                source_ref="conversation:mother:2026-09-13",
                source_version="v1",
                projection_version="test-resolution-v1",
            )

            resolved = await resolve_unknown(
                unknown_repository=unknown_repo,
                world_state_repository=world_repo,
                unknown_id="unk-resolution-1",
                scope=family_scope,
                resolution_atom_ids=(answer_atom.atom_id,),
                resolved_at=NOW,
            )

            assert resolved.status is UnknownStatus.RESOLVED
            assert resolved.resolution_refs == (answer_atom.atom_id,)


async def test_nonexistent_resolution_atom_rejected() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)
            await unknown_repo.create(open_unknown())

            with pytest.raises(ContextContractError, match="UNKNOWN_RESOLUTION_EVIDENCE_NOT_FOUND"):
                await resolve_unknown(
                    unknown_repository=unknown_repo,
                    world_state_repository=world_repo,
                    unknown_id="unk-resolution-1",
                    scope=family_scope,
                    resolution_atom_ids=("fake-atom-999",),
                    resolved_at=NOW,
                )


async def test_preexisting_evidence_older_than_unknown_rejected() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)
            await unknown_repo.create(open_unknown())

            old_atom = evidence_atom(
                atom_id="old-evidence-1", observed_at=BEFORE_UNKNOWN, recorded_at=BEFORE_UNKNOWN
            )
            await world_repo.append_atom(
                old_atom,
                source_ref="conversation:mother:old",
                source_version="v1",
                projection_version="test-resolution-v1",
            )

            with pytest.raises(ContextContractError, match="UNKNOWN_RESOLUTION_EVIDENCE_NOT_NEW"):
                await resolve_unknown(
                    unknown_repository=unknown_repo,
                    world_state_repository=world_repo,
                    unknown_id="unk-resolution-1",
                    scope=family_scope,
                    resolution_atom_ids=(old_atom.atom_id,),
                    resolved_at=NOW,
                )


async def test_ai_authored_evidence_rejected() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)
            await unknown_repo.create(open_unknown())

            ai_atom = evidence_atom(
                atom_id="ai-hypothesis-1",
                epistemic_kind=WorldStateEpistemicKind.HYPOTHESIS,
                asserted_by="ai:family-principal",
                attributed_actor_type=WorldStateActorType.AI,
                evidence_refs=("evidence-x",),
                support_level=BeliefBand.MODERATE,
                contradiction_level=BeliefBand.NONE,
                uncertainty=UncertaintyBand.HIGH,
            )
            await world_repo.append_atom(
                ai_atom,
                source_ref="ai:family-principal:1",
                source_version="v1",
                projection_version="test-resolution-v1",
            )

            with pytest.raises(ContextContractError, match="AI_CANNOT_RESOLVE_UNKNOWN"):
                await resolve_unknown(
                    unknown_repository=unknown_repo,
                    world_state_repository=world_repo,
                    unknown_id="unk-resolution-1",
                    scope=family_scope,
                    resolution_atom_ids=(ai_atom.atom_id,),
                    resolved_at=NOW,
                )


async def test_other_family_evidence_rejected() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_a_scope = scope(family_id="family-1")
        family_b_scope = scope(family_id="family-2", subject_ids=("child-9",))
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)
            await unknown_repo.create(open_unknown(scope=family_a_scope))

            other_family_atom = evidence_atom(
                atom_id="other-family-evidence-1",
                scope=family_b_scope,
                subject_ids=("child-9",),
                asserted_by="mother-9",
            )
            await world_repo.append_atom(
                other_family_atom,
                source_ref="conversation:family-2",
                source_version="v1",
                projection_version="test-resolution-v1",
            )

            with pytest.raises(ContextScopeError, match="CROSS_FAMILY_WORLD_STATE_READ"):
                await resolve_unknown(
                    unknown_repository=unknown_repo,
                    world_state_repository=world_repo,
                    unknown_id="unk-resolution-1",
                    scope=family_a_scope,
                    resolution_atom_ids=(other_family_atom.atom_id,),
                    resolved_at=NOW,
                )


async def test_other_tenant_evidence_rejected() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        tenant_a_scope = scope(tenant_id="tenant-a")
        tenant_b_scope = scope(tenant_id="tenant-b")
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)
            await unknown_repo.create(open_unknown(scope=tenant_a_scope))

            other_tenant_atom = evidence_atom(atom_id="tenant-b-evidence-1", scope=tenant_b_scope)
            await world_repo.append_atom(
                other_tenant_atom,
                source_ref="conversation:tenant-b",
                source_version="v1",
                projection_version="test-resolution-v1",
            )

            with pytest.raises(ContextScopeError, match="CROSS_TENANT_WORLD_STATE_READ"):
                await resolve_unknown(
                    unknown_repository=unknown_repo,
                    world_state_repository=world_repo,
                    unknown_id="unk-resolution-1",
                    scope=tenant_a_scope,
                    resolution_atom_ids=(other_tenant_atom.atom_id,),
                    resolved_at=NOW,
                )


async def test_unrelated_predicate_evidence_rejected() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)
            await unknown_repo.create(open_unknown(target_predicate=TARGET_PREDICATE))

            unrelated_atom = evidence_atom(
                atom_id="unrelated-evidence-1", predicate="child.sleep_pattern"
            )
            await world_repo.append_atom(
                unrelated_atom,
                source_ref="conversation:mother:unrelated",
                source_version="v1",
                projection_version="test-resolution-v1",
            )

            with pytest.raises(
                ContextContractError, match="UNKNOWN_RESOLUTION_TARGET_NOT_ADDRESSED"
            ):
                await resolve_unknown(
                    unknown_repository=unknown_repo,
                    world_state_repository=world_repo,
                    unknown_id="unk-resolution-1",
                    scope=family_scope,
                    resolution_atom_ids=(unrelated_atom.atom_id,),
                    resolved_at=NOW,
                )


async def test_non_ai_authored_hypothesis_still_rejected_as_evidence_kind() -> None:
    """3.5: HYPOTHESIS is never eligible resolution evidence, independent
    of who asserted it — the AI-authorship check (3.4) and the eligible-
    kind check (3.5) are separate invariants, so this constructs a
    HYPOTHESIS atom authored by a real family member to isolate the kind
    check from the authorship check."""

    from backend.intelligence.context_engine.world_state import BeliefBand, UncertaintyBand

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)
            await unknown_repo.create(open_unknown())

            non_ai_hypothesis = evidence_atom(
                atom_id="non-ai-hypothesis-1",
                epistemic_kind=WorldStateEpistemicKind.HYPOTHESIS,
                asserted_by="mother-1",
                attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
                evidence_refs=("evidence-x",),
                support_level=BeliefBand.MODERATE,
                contradiction_level=BeliefBand.NONE,
                uncertainty=UncertaintyBand.HIGH,
            )
            await world_repo.append_atom(
                non_ai_hypothesis,
                source_ref="conversation:mother:hypothesis",
                source_version="v1",
                projection_version="test-resolution-v1",
            )

            with pytest.raises(
                ContextContractError, match="UNKNOWN_RESOLUTION_EVIDENCE_KIND_NOT_ELIGIBLE"
            ):
                await resolve_unknown(
                    unknown_repository=unknown_repo,
                    world_state_repository=world_repo,
                    unknown_id="unk-resolution-1",
                    scope=family_scope,
                    resolution_atom_ids=(non_ai_hypothesis.atom_id,),
                    resolved_at=NOW,
                )


async def test_non_ai_perspective_is_eligible_evidence() -> None:
    """A real family member's PERSPECTIVE (not AI-authored) is eligible per
    the V1 kind list — the eligibility narrowing is about AI authorship,
    not about PERSPECTIVE as a kind."""

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)
            await unknown_repo.create(open_unknown())

            perspective_atom = evidence_atom(
                atom_id="perspective-evidence-1",
                epistemic_kind=WorldStateEpistemicKind.PERSPECTIVE,
                attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
            )
            await world_repo.append_atom(
                perspective_atom,
                source_ref="conversation:mother:perspective",
                source_version="v1",
                projection_version="test-resolution-v1",
            )

            resolved = await resolve_unknown(
                unknown_repository=unknown_repo,
                world_state_repository=world_repo,
                unknown_id="unk-resolution-1",
                scope=family_scope,
                resolution_atom_ids=(perspective_atom.atom_id,),
                resolved_at=NOW,
            )
            assert resolved.status is UnknownStatus.RESOLVED


async def test_resolve_unknown_requires_at_least_one_atom_id() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            unknown_repo = PostgresUnknownRepository(connection)
            world_repo = PostgresWorldStateRepository(connection)
            await unknown_repo.create(open_unknown())

            with pytest.raises(
                ContextContractError, match="RESOLVED_UNKNOWN_REQUIRES_RESOLUTION_REFS"
            ):
                await resolve_unknown(
                    unknown_repository=unknown_repo,
                    world_state_repository=world_repo,
                    unknown_id="unk-resolution-1",
                    scope=family_scope,
                    resolution_atom_ids=(),
                    resolved_at=NOW,
                )
