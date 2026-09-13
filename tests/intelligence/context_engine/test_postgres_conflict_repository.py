"""Real-Postgres tests for `PostgresConflictRepository` (AIFAMILY-WM-004A)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import MetaData

from backend.intelligence.context_engine.conflict_engine import (
    ConflictType,
    detect_conflicts,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.postgres_conflict_repository import (
    PostgresConflictRepository,
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
        "subject_ids": ("child-1", "mother-1"),
        "epistemic_kind": WorldStateEpistemicKind.PERSPECTIVE,
        "predicate": "family.conflict_frequency",
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


async def _apply_conflict_migration(engine) -> None:
    import importlib

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    atoms_migration = importlib.import_module(
        "database.migrations.versions.0080_ai_family_world_atoms"
    )
    conflicts_migration = importlib.import_module(
        "database.migrations.versions.0081_ai_family_world_conflicts"
    )

    def _run_upgrade(sync_connection, migration_module) -> None:
        context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
        with Operations.context(context):
            migration_module.upgrade()

    async with engine.begin() as connection:
        await connection.run_sync(lambda c: _run_upgrade(c, atoms_migration))
        await connection.run_sync(lambda c: _run_upgrade(c, conflicts_migration))


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_append_and_list_conflicts_round_trips_through_real_postgres() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_conflict_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresConflictRepository(connection)
            family_scope = scope()

            mother_statement = atom(
                atom_id="mother-statement-1", value_ref="每天", asserted_by="mother-1"
            )
            child_statement = atom(
                atom_id="child-statement-1", value_ref="一周一次", asserted_by="child-1"
            )
            (conflict,) = detect_conflicts((mother_statement, child_statement), detected_at=NOW)
            await repository.append_conflict(conflict)

            loaded = await repository.list_conflicts(scope=family_scope)
            assert len(loaded) == 1
            assert loaded[0].conflict_type is ConflictType.PERSPECTIVE_CONFLICT
            assert set(loaded[0].atom_ids) == {"mother-statement-1", "child-statement-1"}


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_appending_the_same_conflict_twice_is_idempotent() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_conflict_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresConflictRepository(connection)
            family_scope = scope()

            mother_statement = atom(
                atom_id="mother-statement-2", value_ref="每天", asserted_by="mother-1"
            )
            child_statement = atom(
                atom_id="child-statement-2", value_ref="一周一次", asserted_by="child-1"
            )
            (conflict,) = detect_conflicts((mother_statement, child_statement), detected_at=NOW)

            await repository.append_conflict(conflict)
            await repository.append_conflict(conflict)  # re-detected on a later run

            loaded = await repository.list_conflicts(scope=family_scope)
            assert len(loaded) == 1
