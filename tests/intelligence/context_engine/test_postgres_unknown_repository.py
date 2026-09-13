"""Real-Postgres tests for `PostgresUnknownRepository` (AIFAMILY-WM-004C, B10-B12).

Follows the schema-scoped-engine pattern from
`test_postgres_world_state_repository.py`: every test is skipped unless
`AIFAMILY_TEST_DATABASE_URL` is set.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import MetaData

from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    ContextScopeError,
    DataClass,
)
from backend.intelligence.context_engine.postgres_unknown_repository import (
    AiSelfResolutionRejectedError,
    PostgresUnknownRepository,
)
from backend.intelligence.context_engine.unknown_identity import build_unknown_key
from backend.intelligence.context_engine.world_state import UnknownState, UnknownStatus
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


def unknown(**overrides: object) -> UnknownState:
    family_scope = overrides.get("scope", scope())
    subject_ids = overrides.get("subject_ids", ("child-1",))
    target_predicate = overrides.get("target_predicate", "child.school_engagement")
    blocking_refs = overrides.get("blocking_refs", ("hyp-1",))
    values: dict[str, object] = {
        "unknown_id": "unk-1",
        "scope": family_scope,
        "subject_ids": subject_ids,
        "question": "学校最近有没有变化？",
        "why_it_matters": "区分学校适应问题和其他原因",
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


async def _apply_unknown_migration(engine) -> None:
    atoms_migration = importlib.import_module(
        "database.migrations.versions.0080_ai_family_world_atoms"
    )
    unknowns_migration = importlib.import_module(
        "database.migrations.versions.0084_ai_family_world_unknowns"
    )

    async with engine.begin() as connection:
        await connection.run_sync(lambda c: _run_upgrade(c, atoms_migration))
        await connection.run_sync(lambda c: _run_upgrade(c, unknowns_migration))


def _run_upgrade(sync_connection, migration_module) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
    with Operations.context(context):
        migration_module.upgrade()


pytestmark = pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)


async def test_create_and_get_round_trips_through_real_postgres() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            repository = PostgresUnknownRepository(connection)
            created = await repository.create(unknown(scope=family_scope))
            assert created.status is UnknownStatus.OPEN

            loaded = await repository.get("unk-1", scope=family_scope)
            assert loaded is not None
            assert loaded.question == created.question
            assert loaded.target_predicate == "child.school_engagement"


async def test_unknown_survives_restart_readback() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        family_scope = scope()
        async with engine.begin() as write_connection:
            writer = PostgresUnknownRepository(write_connection)
            await writer.create(unknown(scope=family_scope))

        async with engine.begin() as fresh_connection:
            reader = PostgresUnknownRepository(fresh_connection)
            loaded = await reader.get("unk-1", scope=family_scope)
            assert loaded is not None
            assert loaded.unknown_key == unknown(scope=family_scope).unknown_key


async def test_same_semantic_unknown_different_wording_yields_one_row() -> None:
    """B9/B10: two proposals with the same tenant/family/subjects/
    target_predicate/blocking_refs but different question text must
    collapse into a single row — the UNIQUE(unknown_key) constraint, not
    just application-level dedup."""

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            repository = PostgresUnknownRepository(connection)
            first = await repository.create(
                unknown(unknown_id="unk-a", question="学校最近有没有变化？")
            )
            second = await repository.create(
                unknown(unknown_id="unk-b", question="最近学校方面是不是出了什么状况？")
            )
            assert first.unknown_key == second.unknown_key
            # The second create() must resolve to the FIRST row's identity,
            # not silently create a second row under a different unknown_id.
            assert second.unknown_id == "unk-a"

            open_unknowns = await repository.list_open(scope=family_scope)
            assert len(open_unknowns) == 1


async def test_concurrent_unknown_generation_yields_exactly_one_row() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        family_scope = scope()

        async def _create(unknown_id: str) -> None:
            async with engine.begin() as connection:
                repository = PostgresUnknownRepository(connection)
                await repository.create(unknown(unknown_id=unknown_id))

        import asyncio

        await asyncio.gather(_create("unk-race-a"), _create("unk-race-b"))

        async with engine.begin() as connection:
            repository = PostgresUnknownRepository(connection)
            open_unknowns = await repository.list_open(scope=family_scope)
            assert len(open_unknowns) == 1


async def test_cross_family_read_denied_at_repository_level() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresUnknownRepository(connection)
            family_a_scope = scope(family_id="family-1")
            await repository.create(unknown(unknown_id="a-only-1", scope=family_a_scope))

            family_b_scope = scope(family_id="family-2", subject_ids=("child-9",))
            with pytest.raises(ContextScopeError, match="CROSS_FAMILY_UNKNOWN_READ"):
                await repository.get("a-only-1", scope=family_b_scope)


async def test_cross_tenant_read_denied_at_repository_level() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresUnknownRepository(connection)
            tenant_a_scope = scope(tenant_id="tenant-a")
            await repository.create(unknown(unknown_id="tenant-a-only", scope=tenant_a_scope))

            tenant_b_scope = scope(tenant_id="tenant-b")
            with pytest.raises(ContextScopeError, match="CROSS_TENANT_UNKNOWN_READ"):
                await repository.get("tenant-a-only", scope=tenant_b_scope)


async def test_live_consent_gate_denies_read_after_consent_version_changes() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        original_scope = scope(consent_version="consent.v1")
        async with engine.begin() as connection:
            repository = PostgresUnknownRepository(connection)
            await repository.create(unknown(scope=original_scope))

            withdrawn_scope = scope(consent_version="consent.v2")
            with pytest.raises(ContextContractError, match="UNKNOWN_CONSENT_VERSION_MISMATCH"):
                await repository.get("unk-1", scope=withdrawn_scope)


async def test_ai_cannot_self_resolve_using_only_blocking_refs() -> None:
    """B11: citing the very evidence that was already insufficient to
    answer the question is not new information."""

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            repository = PostgresUnknownRepository(connection)
            await repository.create(unknown(blocking_refs=("hyp-1", "hyp-2")))

            with pytest.raises(AiSelfResolutionRejectedError):
                await repository.resolve(
                    "unk-1",
                    scope=family_scope,
                    resolution_refs=("hyp-1",),
                    resolved_at=NOW,
                )


async def test_resolution_requires_new_evidence_beyond_blocking_refs() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            repository = PostgresUnknownRepository(connection)
            await repository.create(unknown(blocking_refs=("hyp-1",)))

            resolved = await repository.resolve(
                "unk-1",
                scope=family_scope,
                resolution_refs=("parent-interview-2026-09-14",),
                resolved_at=NOW,
            )
            assert resolved.status is UnknownStatus.RESOLVED
            assert resolved.resolution_refs == ("parent-interview-2026-09-14",)


async def test_resolution_requires_non_empty_refs() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_unknown_migration(engine)
        family_scope = scope()
        async with engine.begin() as connection:
            repository = PostgresUnknownRepository(connection)
            await repository.create(unknown())

            with pytest.raises(
                ContextContractError, match="RESOLVED_UNKNOWN_REQUIRES_RESOLUTION_REFS"
            ):
                await repository.resolve(
                    "unk-1", scope=family_scope, resolution_refs=(), resolved_at=NOW
                )
