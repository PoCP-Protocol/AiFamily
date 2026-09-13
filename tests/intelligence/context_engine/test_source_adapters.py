"""AIFAMILY-WM-002 acceptance tests: authoritative domain → WorldStateAtom.

Pure transform tests (no I/O) plus one end-to-end test proving the adapted
atom actually persists through `PostgresWorldStateRepository`.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import MetaData

from backend.domains.family.domain.entities import (
    FamilyMember,
    FamilyRelationship,
)
from backend.domains.family_need.domain.entities import FamilyNeed, NeedSignal
from backend.domains.family_need.domain.value_objects import (
    ActorType,
    NeedCategory,
    NeedContext,
    NeedSignalSource,
)
from backend.domains.family_need.domain.value_objects import (
    DataClass as NeedDataClass,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.postgres_world_state_repository import (
    PostgresWorldStateRepository,
)
from backend.intelligence.context_engine.source_adapters.family_need_source_adapter import (
    family_need_atom,
)
from backend.intelligence.context_engine.source_adapters.family_source_adapter import (
    family_member_atom,
    family_relationship_atom,
)
from backend.intelligence.context_engine.world_state import (
    WorldStateActorType,
    WorldStateEpistemicKind,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

NAIVE_NOW = datetime(2026, 9, 13, 12, 0, 0)


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


def _family_member() -> FamilyMember:
    return FamilyMember(
        person_id="child-1",
        family_id="family-1",
        person_type="CHILD",
        display_name="孩子",
        created_at=NAIVE_NOW,
        updated_at=NAIVE_NOW,
    )


def _family_relationship() -> FamilyRelationship:
    return FamilyRelationship(
        relationship_id="rel-1",
        family_id="family-1",
        person_a_id="child-1",
        person_b_id="mother-1",
        relationship_type="PARENT_CHILD",
        created_at=NAIVE_NOW,
    )


def _family_need() -> FamilyNeed:
    context = NeedContext(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_person_ids=("child-1",),
        purpose="FAMILY_NEED",
        consent_version="consent-v1",
        data_class=NeedDataClass.MINOR_PERSONAL_DATA,
        actor_id="mother-1",
        actor_type=ActorType.FAMILY_GUARDIAN,
        provenance_ref="family-expression-1",
        correlation_id="corr-1",
    )
    signal = NeedSignal.capture(
        context=context,
        source=NeedSignalSource.FAMILY_EXPRESSED,
        raw_text="孩子最近不愿意上学",
        signal_id="signal-wm002-1",
    )
    return FamilyNeed.from_signal(
        signal,
        statement="孩子最近不愿意上学",
        desired_outcome="理解原因并逐步恢复上学意愿",
        category=NeedCategory.EDUCATION,
        need_id="need-wm002-1",
    )


# --- Pure adapter tests (no I/O) --------------------------------------------


def test_family_member_adapter_produces_a_fact_atom() -> None:
    atom = family_member_atom(_family_member(), scope=scope(), atom_id="member-atom-1")
    assert atom.epistemic_kind is WorldStateEpistemicKind.FACT
    assert atom.attributed_actor_type is WorldStateActorType.SYSTEM
    assert atom.predicate == "family.member_of"
    assert atom.subject_ids == ("child-1",)
    assert atom.value_ref == "family-1"


def test_family_relationship_adapter_produces_a_fact_atom() -> None:
    atom = family_relationship_atom(
        _family_relationship(), scope=scope(), atom_id="relationship-atom-1"
    )
    assert atom.epistemic_kind is WorldStateEpistemicKind.FACT
    assert atom.predicate == "family.relationship"
    assert set(atom.subject_ids) == {"child-1", "mother-1"}
    assert atom.value_ref == "PARENT_CHILD"


def test_family_need_adapter_projects_active_need_before_confirmation() -> None:
    need = _family_need()
    atom = family_need_atom(need, scope=scope(subject_ids=("child-1",)), atom_id="need-atom-1")
    assert atom.predicate == "family.active_need"
    assert atom.epistemic_kind is WorldStateEpistemicKind.FACT
    assert atom.value_ref == "孩子最近不愿意上学"


def test_family_need_adapter_projects_confirmed_need_after_confirmation() -> None:
    need = _family_need().start_clarification().confirm("mother-1")
    atom = family_need_atom(need, scope=scope(subject_ids=("child-1",)), atom_id="need-atom-2")
    assert atom.predicate == "family.confirmed_need"


def test_adapter_never_produces_ai_attribution() -> None:
    """A domain-projection adapter has no AI actor concept at all — this test
    exists to make that omission explicit rather than accidental."""

    atom = family_member_atom(_family_member(), scope=scope(), atom_id="member-atom-2")
    assert atom.attributed_actor_type is not WorldStateActorType.AI


# --- End-to-end: real domain object -> adapter -> Postgres ----------------


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_adapted_family_need_atom_persists_through_real_postgres() -> None:
    import importlib

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    atoms_migration = importlib.import_module(
        "database.migrations.versions.0080_ai_family_world_atoms"
    )
    projection_identity_migration = importlib.import_module(
        "database.migrations.versions.0082_ai_family_world_atoms_projection_identity"
    )

    def _run_upgrade(sync_connection, migration_module) -> None:
        context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
        with Operations.context(context):
            migration_module.upgrade()

    async with postgres_schema_engine(MetaData()) as engine:
        async with engine.begin() as connection:
            await connection.run_sync(lambda c: _run_upgrade(c, atoms_migration))
            await connection.run_sync(lambda c: _run_upgrade(c, projection_identity_migration))

        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            family_scope = scope(subject_ids=("child-1",))
            need = _family_need()
            atom = family_need_atom(need, scope=family_scope, atom_id="need-atom-e2e-1")

            await repository.append_atom(
                atom,
                source_ref=f"family-need-domain:family_needs:{need.need_id}",
                source_version="1",
                projection_version="test-fixture/v1",
            )
            loaded = await repository.get_atom("need-atom-e2e-1", scope=family_scope)
            assert loaded is not None
            assert loaded.predicate == "family.active_need"
            assert loaded.provenance == f"family-need-domain:family_needs:{need.need_id}"
