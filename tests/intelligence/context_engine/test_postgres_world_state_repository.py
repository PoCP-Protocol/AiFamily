"""Real-Postgres tests for `PostgresWorldStateRepository` (AIFAMILY-WM-001).

Follows the schema-scoped-engine pattern from
`tests/domains/family_need/test_postgres_repository_integration.py`: every
test is skipped unless `AIFAMILY_TEST_DATABASE_URL` is set.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import MetaData

from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    ContextScopeError,
    DataClass,
)
from backend.intelligence.context_engine.postgres_world_state_repository import (
    PostgresWorldStateRepository,
)
from backend.intelligence.context_engine.predicate_registry import (
    PredicateRegistry,
    PredicateRegistryError,
)
from backend.intelligence.context_engine.world_state import (
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


async def _apply_world_state_migration(engine) -> None:
    import importlib

    migration = importlib.import_module("database.migrations.versions.0080_ai_family_world_atoms")

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_conn: _run_upgrade(sync_conn, migration))


def _run_upgrade(sync_connection, migration_module) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
    with Operations.context(context):
        migration_module.upgrade()


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_append_and_get_atom_round_trips_through_real_postgres() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            family_scope = scope()
            original = atom(scope=family_scope)
            await repository.append_atom(original)

            loaded = await repository.get_atom(original.atom_id, scope=family_scope)
            assert loaded is not None
            assert loaded.atom_id == original.atom_id
            assert loaded.epistemic_kind is WorldStateEpistemicKind.SELF_REPORT
            assert loaded.value_ref == original.value_ref
            assert loaded.subject_ids == original.subject_ids


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_append_rejects_ungoverned_predicate() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            rogue = atom(atom_id="rogue-1", predicate="child_is_lazy")
            with pytest.raises(PredicateRegistryError, match="PREDICATE_NOT_REGISTERED"):
                await repository.append_atom(rogue)


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_ai_asserted_fact_is_rejected_at_the_database_check_constraint() -> None:
    """Defence in depth: even if a caller bypassed the Python-level
    `AI_CANNOT_ASSERT_THIS_EPISTEMIC_KIND` guard, the CHECK constraint from
    migration 0080 must still refuse the row."""

    from sqlalchemy.exc import IntegrityError

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            connection_atom_dict = {
                "atom_id": "smuggled-fact-1",
                "tenant_id": "tenant-1",
                "family_id": "family-1",
                "subject_ids": "[]",
                "epistemic_kind": "FACT",
                "predicate": "family.member_statement",
                "value_ref": "smuggled",
                "asserted_by": "ai:family-principal",
                "attributed_actor_type": "AI",
                "provenance": "test",
                "source_refs": "[]",
                "evidence_refs": "[]",
                "observed_at": NOW,
                "valid_from": NOW,
                "valid_until": None,
                "recorded_at": NOW,
                "status": "ACTIVE",
                "supersedes": None,
                "purpose": "family_growth_support",
                "consent_version": "consent.v1",
                "data_class": "FAMILY_PRIVATE_TEXT",
            }
            from sqlalchemy import text

            with pytest.raises(IntegrityError):
                await connection.execute(
                    text(
                        """
                        INSERT INTO ai_family_world_atoms (
                            atom_id, tenant_id, family_id, subject_ids, epistemic_kind,
                            predicate, value_ref, asserted_by, attributed_actor_type,
                            provenance, source_refs, evidence_refs, observed_at,
                            valid_from, valid_until, recorded_at, status, supersedes,
                            purpose, consent_version, data_class
                        ) VALUES (
                            :atom_id, :tenant_id, :family_id, :subject_ids, :epistemic_kind,
                            :predicate, :value_ref, :asserted_by, :attributed_actor_type,
                            :provenance, :source_refs, :evidence_refs, :observed_at,
                            :valid_from, :valid_until, :recorded_at, :status, :supersedes,
                            :purpose, :consent_version, :data_class
                        )
                        """
                    ),
                    connection_atom_dict,
                )


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_get_state_is_bitemporal_valid_at_vs_known_at() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            family_scope = scope()

            # A claim that was true starting 2026-08-28, but AiFamily only
            # learned about it on 2026-09-10 (mother supplied sleep-device
            # records ten days after the fact).
            late_reported = atom(
                atom_id="late-reported-1",
                scope=family_scope,
                predicate="child.sleep_pattern",
                value_ref="平均凌晨1:30入睡",
                valid_from=datetime(2026, 8, 28, tzinfo=UTC),
                observed_at=datetime(2026, 8, 28, tzinfo=UTC),
                recorded_at=datetime(2026, 9, 10, tzinfo=UTC),
            )
            await repository.append_atom(late_reported)

            # known_at before the report existed: invisible.
            before_known = await repository.get_state(
                scope=family_scope,
                valid_at=datetime(2026, 9, 5, tzinfo=UTC),
                known_at=datetime(2026, 9, 5, tzinfo=UTC),
            )
            assert late_reported.atom_id not in {a.atom_id for a in before_known}

            # known_at after the report arrived, valid_at back in the window
            # it actually describes: visible.
            after_known = await repository.get_state(
                scope=family_scope,
                valid_at=datetime(2026, 9, 5, tzinfo=UTC),
                known_at=datetime(2026, 9, 12, tzinfo=UTC),
            )
            assert late_reported.atom_id in {a.atom_id for a in after_known}


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_get_state_excludes_atoms_outside_subject_scope() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            wide_scope = scope(subject_ids=("child-1", "mother-1"))
            about_mother_only = atom(
                atom_id="mother-only-1",
                scope=wide_scope,
                subject_ids=("mother-1",),
                predicate="family.member_statement",
            )
            await repository.append_atom(about_mother_only)

            child_only_scope = scope(subject_ids=("child-1",))
            visible = await repository.get_state(scope=child_only_scope)
            assert "mother-only-1" not in {a.atom_id for a in visible}


def test_predicate_registry_rejects_unregistered_predicate_before_any_db_call() -> None:
    registry = PredicateRegistry.from_yaml()
    with pytest.raises(PredicateRegistryError):
        registry.validate("family.total_score")


# --- WM-001 acceptance criteria (10 items) ---------------------------------


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_criterion_1_non_ai_actor_can_create_a_fact() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            family_scope = scope()
            fact = atom(
                atom_id="fact-1",
                scope=family_scope,
                epistemic_kind=WorldStateEpistemicKind.FACT,
                predicate="family.member_of",
                value_ref="family-1",
                asserted_by="system:family-domain",
                attributed_actor_type=WorldStateActorType.SYSTEM,
            )
            await repository.append_atom(fact)
            loaded = await repository.get_atom("fact-1", scope=family_scope)
            assert loaded is not None
            assert loaded.epistemic_kind is WorldStateEpistemicKind.FACT


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_criterion_5_opposing_perspectives_both_persist() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            family_scope = scope()
            mother_view = atom(
                atom_id="mother-view-1",
                scope=family_scope,
                subject_ids=("child-1", "mother-1"),
                epistemic_kind=WorldStateEpistemicKind.PERSPECTIVE,
                predicate="family.member_statement",
                value_ref="几乎每天都吵",
                asserted_by="mother-1",
                attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
                source_refs=("conversation:mother-1",),
            )
            child_view = atom(
                atom_id="child-view-1",
                scope=family_scope,
                subject_ids=("child-1", "mother-1"),
                epistemic_kind=WorldStateEpistemicKind.PERSPECTIVE,
                predicate="family.member_statement",
                value_ref="一个星期一两次",
                asserted_by="child-1",
                attributed_actor_type=WorldStateActorType.FAMILY_MEMBER,
                source_refs=("conversation:child-1",),
            )
            await repository.append_atom(mother_view)
            await repository.append_atom(child_view)

            state = await repository.get_state(scope=family_scope)
            ids = {a.atom_id for a in state}
            # Both contradictory perspectives coexist — neither one wins by
            # being "averaged" or silently dropped.
            assert {"mother-view-1", "child-view-1"}.issubset(ids)


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_criterion_7_superseded_atom_still_readable_at_its_own_known_at() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            family_scope = scope()
            original = atom(
                atom_id="dislike-math-v1",
                scope=family_scope,
                predicate="family.member_statement",
                value_ref="讨厌数学",
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                observed_at=datetime(2026, 6, 1, tzinfo=UTC),
                recorded_at=datetime(2026, 6, 1, tzinfo=UTC),
                valid_until=datetime(2026, 9, 1, tzinfo=UTC),
            )
            updated = atom(
                atom_id="likes-math-v2",
                scope=family_scope,
                predicate="family.member_statement",
                value_ref="现在其实挺喜欢数学",
                valid_from=datetime(2026, 9, 1, tzinfo=UTC),
                observed_at=datetime(2026, 9, 1, tzinfo=UTC),
                recorded_at=datetime(2026, 9, 1, tzinfo=UTC),
                supersedes=original.atom_id,
            )
            await repository.append_atom(original)
            await repository.append_atom(updated)

            # Historical query: what was true in July? The old version.
            july_state = await repository.get_state(
                scope=family_scope, valid_at=datetime(2026, 7, 1, tzinfo=UTC)
            )
            assert "dislike-math-v1" in {a.atom_id for a in july_state}
            assert "likes-math-v2" not in {a.atom_id for a in july_state}

            # get_atom by id must still resolve the old row directly —
            # supersession never deletes or mutates it.
            old_direct = await repository.get_atom("dislike-math-v1", scope=family_scope)
            assert old_direct is not None
            assert old_direct.value_ref == "讨厌数学"


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_criterion_8_persists_across_a_fresh_connection() -> None:
    """Stands in for "PostgreSQL restart readback": nothing in this kernel
    is process/connection-cached, so a brand-new engine/connection reading
    the same schema is the observable equivalent of a process restart."""

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        family_scope = scope()
        async with engine.begin() as write_connection:
            writer = PostgresWorldStateRepository(write_connection)
            await writer.append_atom(atom(atom_id="durable-1", scope=family_scope))

        async with engine.begin() as fresh_connection:
            reader = PostgresWorldStateRepository(fresh_connection)
            loaded = await reader.get_atom("durable-1", scope=family_scope)
            assert loaded is not None
            assert loaded.atom_id == "durable-1"


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_criterion_9_cross_family_read_denied_at_repository_level() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            family_a_scope = scope(family_id="family-1")
            await repository.append_atom(atom(atom_id="a-only-1", scope=family_a_scope))

            family_b_scope = scope(family_id="family-2", subject_ids=("child-9",))
            with pytest.raises(ContextScopeError, match="CROSS_FAMILY_WORLD_STATE_READ"):
                await repository.get_atom("a-only-1", scope=family_b_scope)


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_criterion_10_revoked_consent_scope_cannot_even_be_constructed() -> None:
    """`ContextScope.__post_init__` fails closed on `consent_granted=False`
    before any read is attempted — there is no code path in this kernel that
    accepts a revoked-consent scope and then separately decides to deny it."""

    with pytest.raises(ContextContractError, match="CONSENT_REVOKED"):
        scope(consent_granted=False)
