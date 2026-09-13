"""AIFAMILY-WM-003.6 acceptance tests: Source Identity, Semantic Fingerprint,
Idempotent Projection (T1-T10 per task spec).

Real PostgreSQL required — no SQLite substitute per task §12.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import MetaData

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.postgres_world_state_repository import (
    AppendAtomOutcome,
    PostgresWorldStateRepository,
    ProjectionIdentityConflictError,
)
from backend.intelligence.context_engine.projection_identity import (
    build_projection_key,
    build_semantic_fingerprint,
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


def atom(**overrides: object) -> WorldStateAtom:
    values: dict[str, object] = {
        "atom_id": "atom-1",
        "scope": scope(),
        "subject_ids": ("child-1",),
        "epistemic_kind": WorldStateEpistemicKind.FACT,
        "predicate": "family.confirmed_growth_intent",
        "value_ref": "改善晚间沟通方式",
        "asserted_by": "mother-1",
        "attributed_actor_type": WorldStateActorType.FAMILY_GUARDIAN,
        "provenance": "growth-intent-confirmation:idem-1",
        "observed_at": NOW,
        "recorded_at": NOW,
        "valid_from": NOW,
    }
    values.update(overrides)
    return WorldStateAtom(**values)  # type: ignore[arg-type]


async def _apply_world_state_migration(engine) -> None:
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

    async with engine.begin() as connection:
        await connection.run_sync(lambda c: _run_upgrade(c, atoms_migration))
        await connection.run_sync(lambda c: _run_upgrade(c, projection_identity_migration))


# --- T1: same source, different atom_id -------------------------------------


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_t1_same_source_different_atom_id_yields_one_row() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            first = atom(atom_id="A")
            second = atom(atom_id="B")

            first_result = await repository.append_atom(
                first,
                source_ref="growth-intent-confirmation:idem-1",
                source_version="1",
                projection_version="v1",
            )
            second_result = await repository.append_atom(
                second,
                source_ref="growth-intent-confirmation:idem-1",
                source_version="1",
                projection_version="v1",
            )

            assert first_result.outcome is AppendAtomOutcome.INSERTED
            assert second_result.outcome is AppendAtomOutcome.IDEMPOTENT_REPLAY
            assert second_result.atom_id == "A"  # points back at the canonical row

            family_scope = scope()
            state = await repository.get_state(scope=family_scope)
            assert len(state) == 1


# --- T2/T3: same adapter called twice (Growth Intent / Outcome) ------------


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_t2_growth_intent_projected_twice_yields_one_semantic_atom() -> None:
    from backend.domains.growth.application.growth_intent_confirmation import (
        ValidatedConfirmationBinding,
    )
    from backend.intelligence.context_engine.source_adapters.growth_source_adapter import (
        GROWTH_INTENT_PROJECTION_VERSION,
        confirmed_growth_intent_atom,
        growth_intent_source_identity,
    )

    class _CommandLike:
        def __init__(self, **kwargs: object) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    uid_a = "11111111-1111-1111-1111-111111111111"
    uid_b = "22222222-2222-2222-2222-222222222222"
    uid_c = "33333333-3333-3333-3333-333333333333"
    uid_d = "44444444-4444-4444-4444-444444444444"
    binding = ValidatedConfirmationBinding.from_command(
        _CommandLike(
            tenant_id=uid_a,
            family_id=uid_b,
            actor_id=uid_c,
            subject_person_id=uid_a,
            signal_ref="signal-1",
            signal_version=1,
            scope_ref=f"family://{uid_a}/{uid_b}/assessment",
            reviewed_draft_ref="draft-1",
            draft_version=1,
            provenance_ref="provenance-1",
            human_gate_receipt_ref="receipt-1",
            need_type="COMMUNICATION",
            goal_text="改善晚间沟通方式",
            required_capability_keys=("family_communication_coaching",),
            evidence_refs=(uid_d,),
            correlation_id="corr-1",
            idempotency_key="idem-fixed-1",
        )
    )

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            family_scope = scope(tenant_id=uid_a, family_id=uid_b, subject_ids=(uid_a,))
            source_ref, source_version = growth_intent_source_identity(binding)

            for atom_id in ("attempt-1", "attempt-2"):
                projected = confirmed_growth_intent_atom(
                    binding,
                    scope=family_scope,
                    atom_id=atom_id,
                    confirmed_at=NOW,
                    confirmer_actor_type=WorldStateActorType.FAMILY_GUARDIAN,
                )
                await repository.append_atom(
                    projected,
                    source_ref=source_ref,
                    source_version=source_version,
                    projection_version=GROWTH_INTENT_PROJECTION_VERSION,
                )

            state = await repository.get_state(scope=family_scope)
            assert len(state) == 1


# --- T3: FamilyConfirmedOutcome projected twice yields one semantic atom --


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_t3_family_confirmed_outcome_projected_twice_yields_one_semantic_atom() -> None:
    from backend.domains.family_need.domain.entities import FamilyConfirmedOutcome
    from backend.domains.family_need.domain.value_objects import (
        ActorType,
        FamilyOutcomeDecision,
        NeedContext,
    )
    from backend.domains.family_need.domain.value_objects import DataClass as NeedDataClass
    from backend.intelligence.context_engine.source_adapters.family_need_outcome_source_adapter import (  # noqa: E501
        FAMILY_CONFIRMED_OUTCOME_PROJECTION_VERSION,
        family_confirmed_outcome_atom,
        family_confirmed_outcome_source_identity,
    )

    context = NeedContext(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_person_ids=("child-1",),
        purpose="FAMILY_NEED",
        consent_version="consent-v1",
        data_class=NeedDataClass.MINOR_PERSONAL_DATA,
        actor_id="mother-1",
        actor_type=ActorType.FAMILY_GUARDIAN,
        correlation_id="corr-1",
    )
    outcome = FamilyConfirmedOutcome.confirm(
        context=context,
        need_id="need-1",
        fulfillment_ref="booking-service-record:booking-1",
        decision=FamilyOutcomeDecision.HELPED,
        confirmed_by="mother-1",
        outcome_id="outcome-fixed-1",
        confirmed_at=NOW,
    )

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            source_ref, source_version = family_confirmed_outcome_source_identity(outcome)

            for atom_id in ("outcome-attempt-1", "outcome-attempt-2"):
                projected = family_confirmed_outcome_atom(outcome, atom_id=atom_id)
                await repository.append_atom(
                    projected,
                    source_ref=source_ref,
                    source_version=source_version,
                    projection_version=FAMILY_CONFIRMED_OUTCOME_PROJECTION_VERSION,
                )

            state = await repository.get_state(
                scope=scope(
                    tenant_id="tenant-1",
                    family_id="family-1",
                    subject_ids=("child-1",),
                    purpose="FAMILY_NEED",
                    consent_version="consent-v1",
                )
            )
            assert len(state) == 1


# --- T4: conflicting replay must fail closed --------------------------------


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_t4_same_identity_different_semantics_fails_closed() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            original = atom(atom_id="A", value_ref="改善晚间沟通方式")
            await repository.append_atom(
                original,
                source_ref="growth-intent-confirmation:idem-2",
                source_version="1",
                projection_version="v1",
            )

            mutated = atom(atom_id="B", value_ref="完全不同的内容")
            with pytest.raises(ProjectionIdentityConflictError):
                await repository.append_atom(
                    mutated,
                    source_ref="growth-intent-confirmation:idem-2",
                    source_version="1",
                    projection_version="v1",
                )

            # The original row must be untouched — no overwrite happened.
            family_scope = scope()
            state = await repository.get_state(scope=family_scope)
            assert len(state) == 1
            assert state[0].value_ref == "改善晚间沟通方式"


# --- T5: new source version produces a distinct projection identity --------


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_t5_new_source_version_yields_a_new_atom() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            v1 = atom(atom_id="A")
            v2 = atom(atom_id="B")

            await repository.append_atom(
                v1,
                source_ref="growth-intent-confirmation:idem-3",
                source_version="1",
                projection_version="v1",
            )
            result_v2 = await repository.append_atom(
                v2,
                source_ref="growth-intent-confirmation:idem-3",
                source_version="2",
                projection_version="v1",
            )

            assert result_v2.outcome is AppendAtomOutcome.INSERTED
            family_scope = scope()
            state = await repository.get_state(scope=family_scope)
            assert len(state) == 2


# --- T6: restart durability (fresh connection replays as idempotent) ------


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_t6_replay_after_restart_is_idempotent_not_a_new_row() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)

        # "Process A" inserts.
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            await repository.append_atom(
                atom(atom_id="A"),
                source_ref="growth-intent-confirmation:idem-restart",
                source_version="1",
                projection_version="v1",
            )

        # "Process B" — a brand-new connection, nothing cached in-process —
        # replays the same source with a different atom_id.
        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            result = await repository.append_atom(
                atom(atom_id="B"),
                source_ref="growth-intent-confirmation:idem-restart",
                source_version="1",
                projection_version="v1",
            )
            assert result.outcome is AppendAtomOutcome.IDEMPOTENT_REPLAY
            assert result.atom_id == "A"

            state = await repository.get_state(scope=scope())
            assert len(state) == 1


# --- T7: concurrent insert of the same source -------------------------------


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_t7_concurrent_replay_yields_exactly_one_row() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_world_state_migration(engine)

        async def _append(atom_id: str) -> str:
            async with engine.begin() as connection:
                repository = PostgresWorldStateRepository(connection)
                result = await repository.append_atom(
                    atom(atom_id=atom_id),
                    source_ref="growth-intent-confirmation:idem-concurrent",
                    source_version="1",
                    projection_version="v1",
                )
                return result.outcome.value

        outcomes = await asyncio.gather(_append("A"), _append("B"))
        assert sorted(outcomes) == ["IDEMPOTENT_REPLAY", "INSERTED"]

        async with engine.begin() as connection:
            repository = PostgresWorldStateRepository(connection)
            state = await repository.get_state(scope=scope())
            assert len(state) == 1


# --- T8: semantic fingerprint stability (order-independence) --------------


def test_t8_semantic_fingerprint_is_stable_regardless_of_input_order() -> None:
    a = build_semantic_fingerprint(
        family_id="family-1",
        subject_ids=("child-1", "mother-1"),
        predicate="family.confirmed_growth_intent",
        epistemic_kind="FACT",
        value_ref="v",
        asserted_by="mother-1",
        valid_from=NOW,
        valid_until=None,
        source_refs=("ref-2", "ref-1"),
        evidence_refs=("ev-2", "ev-1"),
        data_class="FAMILY_PRIVATE_TEXT",
        projection_version="v1",
    )
    b = build_semantic_fingerprint(
        family_id="family-1",
        subject_ids=("mother-1", "child-1"),
        predicate="family.confirmed_growth_intent",
        epistemic_kind="FACT",
        value_ref="v",
        asserted_by="mother-1",
        valid_from=NOW,
        valid_until=None,
        source_refs=("ref-1", "ref-2"),
        evidence_refs=("ev-1", "ev-2"),
        data_class="FAMILY_PRIVATE_TEXT",
        projection_version="v1",
    )
    assert a == b


# --- T9: different family never collides ------------------------------------


def test_t9_different_family_never_collides() -> None:
    key_a = build_projection_key(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ids=("child-1",),
        predicate="family.confirmed_growth_intent",
        epistemic_kind="FACT",
        source_ref="growth-intent-confirmation:idem-shared",
        source_version="1",
        projection_version="v1",
    )
    key_b = build_projection_key(
        tenant_id="tenant-1",
        family_id="family-2",
        subject_ids=("child-9",),
        predicate="family.confirmed_growth_intent",
        epistemic_kind="FACT",
        source_ref="growth-intent-confirmation:idem-shared",
        source_version="1",
        projection_version="v1",
    )
    assert key_a != key_b


# --- T10: atom_id must never enter the canonical hash input -----------------


def test_t10_projection_key_and_fingerprint_builders_do_not_accept_atom_id() -> None:
    import inspect

    for builder in (build_projection_key, build_semantic_fingerprint):
        params = inspect.signature(builder).parameters
        assert "atom_id" not in params, f"{builder.__name__} must not accept atom_id"
