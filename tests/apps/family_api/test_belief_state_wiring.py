"""AIFAMILY-WM-005B PART P: single-connection BeliefState wiring.

Proves `build_belief_state_query_service()` actually assembles a real
FamilyBeliefState from all three durable stores using one connection —
not that the three repositories merely exist.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import MetaData

from backend.apps.family_api.belief_state_wiring import build_belief_state_query_service
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.postgres_world_state_repository import (
    PostgresWorldStateRepository,
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
        "subject_ids": ("child-1",),
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


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_wired_query_service_reads_atoms_within_single_connection() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        family_scope = scope()

        atom = WorldStateAtom(
            atom_id="wiring-atom-1",
            scope=family_scope,
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
        )

        async with engine.begin() as connection:
            world_repo = PostgresWorldStateRepository(connection)
            await world_repo.append_atom(
                atom, source_ref="conversation:child", source_version="v1", projection_version="w1"
            )

        async with (
            engine.begin() as connection,
            build_belief_state_query_service(connection) as service,
        ):
            belief_state = await service.get_current_belief_state(
                scope=family_scope, snapshot_ref="wiring-snapshot-1", read_at=NOW
            )

        assert {a.atom_id for a in belief_state.self_reports} == {atom.atom_id}
