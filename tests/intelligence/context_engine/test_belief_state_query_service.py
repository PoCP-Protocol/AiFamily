"""AIFAMILY-WM-005 acceptance tests: BeliefStateQueryService (real Postgres).

Proves the assembly actually works against the three durable stores (Atom
Store, Conflict Store, Unknown Store), not just against in-memory objects.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import MetaData

from backend.intelligence.context_engine.belief_state_query_service import (
    BeliefStateQueryService,
)
from backend.intelligence.context_engine.conflict_engine import detect_conflicts
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.postgres_conflict_repository import (
    PostgresConflictRepository,
)
from backend.intelligence.context_engine.postgres_unknown_repository import (
    PostgresUnknownRepository,
)
from backend.intelligence.context_engine.postgres_world_state_repository import (
    PostgresWorldStateRepository,
)
from backend.intelligence.context_engine.unknown_identity import build_unknown_key
from backend.intelligence.context_engine.world_state import (
    UnknownState,
    UnknownStatus,
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

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


def mother_atom() -> WorldStateAtom:
    return WorldStateAtom(
        atom_id="qs-mother-persp-1",
        scope=scope(),
        subject_ids=("child-1", "mother-1"),
        epistemic_kind=WorldStateEpistemicKind.PERSPECTIVE,
        predicate="child.parent_communication",
        value_ref="妈妈认为孩子不愿意沟通",
        asserted_by="mother-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
        provenance="conversation:mother",
        observed_at=NOW,
        recorded_at=NOW,
        valid_from=NOW,
        source_refs=("conversation:mother",),
    )


def child_atom() -> WorldStateAtom:
    return WorldStateAtom(
        atom_id="qs-child-self-1",
        scope=scope(),
        subject_ids=("child-1",),
        epistemic_kind=WorldStateEpistemicKind.SELF_REPORT,
        predicate="child.parent_communication",
        value_ref="孩子说自己愿意沟通",
        asserted_by="child-1",
        attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
        provenance="conversation:child",
        observed_at=NOW,
        recorded_at=NOW,
        valid_from=NOW,
        source_refs=("conversation:child",),
    )


def open_unknown() -> UnknownState:
    family_scope = scope()
    subject_ids = ("child-1",)
    target_predicate = "child.parent_communication"
    blocking_refs = ("qs-mother-persp-1",)
    return UnknownState(
        unknown_id="qs-unknown-1",
        scope=family_scope,
        subject_ids=subject_ids,
        question="孩子自己怎么看？",
        why_it_matters="需要直接了解孩子的看法",
        target_predicate=target_predicate,
        decision_impact="HIGH",
        answerability="MEDIUM",
        urgency="MEDIUM",
        blocking_refs=blocking_refs,
        unknown_key=build_unknown_key(
            tenant_id=family_scope.tenant_id,
            family_id=family_scope.family_id,
            subject_ids=subject_ids,
            target_predicate=target_predicate,
            blocking_refs=blocking_refs,
            unknown_contract_version="world-model-unknown-engine/v1",
        ),
        source_refs=blocking_refs,
        priority="HIGH",
        status=UnknownStatus.OPEN,
        created_at=NOW,
    )


async def _apply_migrations(engine) -> None:
    def _run_upgrade(sync_connection, migration_module) -> None:
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
        with Operations.context(context):
            migration_module.upgrade()

    for name in (
        "0080_ai_family_world_atoms",
        "0081_ai_family_world_conflicts",
        "0082_ai_family_world_atoms_projection_identity",
        "0083_ai_family_world_atoms_belief_metadata",
        "0084_ai_family_world_unknowns",
    ):
        module = importlib.import_module(f"database.migrations.versions.{name}")
        async with engine.begin() as connection:
            await connection.run_sync(lambda c, m=module: _run_upgrade(c, m))


pytestmark = pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)


async def test_belief_state_assembled_from_three_real_stores() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()

        mother = mother_atom()
        child = child_atom()
        conflicts = detect_conflicts((mother, child), detected_at=NOW)
        assert conflicts  # sanity: the fixture actually produces a conflict

        async with engine.begin() as connection:
            world_repo = PostgresWorldStateRepository(connection)
            conflict_repo = PostgresConflictRepository(connection)
            unknown_repo = PostgresUnknownRepository(connection)

            await world_repo.append_atom(
                mother,
                source_ref="conversation:mother",
                source_version="v1",
                projection_version="qs-v1",
            )
            await world_repo.append_atom(
                child,
                source_ref="conversation:child",
                source_version="v1",
                projection_version="qs-v1",
            )
            for c in conflicts:
                await conflict_repo.append_conflict(c)
            await unknown_repo.create(open_unknown())

        async with engine.begin() as fresh_connection:
            service = BeliefStateQueryService(
                world_state_repository=PostgresWorldStateRepository(fresh_connection),
                conflict_repository=PostgresConflictRepository(fresh_connection),
                unknown_repository=PostgresUnknownRepository(fresh_connection),
            )
            belief_state = await service.get_current_belief_state(
                scope=family_scope,
                snapshot_ref="qs-snapshot-1",
                read_at=NOW,
            )

        assert {a.atom_id for a in belief_state.perspectives} == {mother.atom_id}
        assert {a.atom_id for a in belief_state.self_reports} == {child.atom_id}
        assert len(belief_state.open_conflicts) >= 1
        assert {u.unknown_id for u in belief_state.open_unknowns} == {"qs-unknown-1"}


async def test_belief_state_isolates_cross_family_data() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_a_scope = scope(family_id="family-1")
        family_b_scope = scope(family_id="family-2", subject_ids=("child-9",))

        other_family_atom = WorldStateAtom(
            atom_id="qs-other-family-atom-1",
            scope=family_b_scope,
            subject_ids=("child-9",),
            epistemic_kind=WorldStateEpistemicKind.SELF_REPORT,
            predicate="child.parent_communication",
            value_ref="another family's data",
            asserted_by="child-9",
            attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
            provenance="conversation:other",
            observed_at=NOW,
            recorded_at=NOW,
            valid_from=NOW,
        )

        async with engine.begin() as connection:
            world_repo = PostgresWorldStateRepository(connection)
            await world_repo.append_atom(
                other_family_atom,
                source_ref="conversation:other",
                source_version="v1",
                projection_version="qs-v1",
            )

        async with engine.begin() as fresh_connection:
            service = BeliefStateQueryService(
                world_state_repository=PostgresWorldStateRepository(fresh_connection),
                conflict_repository=PostgresConflictRepository(fresh_connection),
                unknown_repository=PostgresUnknownRepository(fresh_connection),
            )
            belief_state = await service.get_current_belief_state(
                scope=family_a_scope,
                snapshot_ref="qs-snapshot-2",
                read_at=NOW,
            )

        assert belief_state.self_reports == ()
        assert belief_state.snapshot.atoms == ()


async def test_future_atom_excluded_from_current_read() -> None:
    """AIFAMILY-WM-005B PART A/O: an atom whose valid_from is after read_at
    must not appear in a current belief-state read — a single read_at
    resolves both valid_at and known_at, so this also proves the two are
    not independently defaulted to different `datetime.now()` calls."""

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()
        future_moment = NOW + timedelta(days=1)

        future_atom = WorldStateAtom(
            atom_id="qs-future-atom-1",
            scope=family_scope,
            subject_ids=("child-1",),
            epistemic_kind=WorldStateEpistemicKind.SELF_REPORT,
            predicate="child.parent_communication",
            value_ref="not yet valid",
            asserted_by="child-1",
            attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
            provenance="conversation:future",
            observed_at=future_moment,
            recorded_at=future_moment,
            valid_from=future_moment,
        )

        async with engine.begin() as connection:
            world_repo = PostgresWorldStateRepository(connection)
            await world_repo.append_atom(
                future_atom,
                source_ref="conversation:future",
                source_version="v1",
                projection_version="qs-v1",
            )

        async with engine.begin() as fresh_connection:
            service = BeliefStateQueryService(
                world_state_repository=PostgresWorldStateRepository(fresh_connection),
                conflict_repository=PostgresConflictRepository(fresh_connection),
                unknown_repository=PostgresUnknownRepository(fresh_connection),
            )
            belief_state = await service.get_current_belief_state(
                scope=family_scope,
                snapshot_ref="qs-snapshot-future",
                read_at=NOW,
            )

        assert belief_state.snapshot.atoms == ()

        async with engine.begin() as later_connection:
            service = BeliefStateQueryService(
                world_state_repository=PostgresWorldStateRepository(later_connection),
                conflict_repository=PostgresConflictRepository(later_connection),
                unknown_repository=PostgresUnknownRepository(later_connection),
            )
            later_belief_state = await service.get_current_belief_state(
                scope=family_scope,
                snapshot_ref="qs-snapshot-later",
                read_at=future_moment + timedelta(minutes=1),
            )

        assert {a.atom_id for a in later_belief_state.snapshot.atoms} == {future_atom.atom_id}
