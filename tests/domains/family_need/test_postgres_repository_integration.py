"""Real-Postgres tests for :class:`SqlAlchemyFamilyNeedRepository`.

Follows the opt-in gated pattern from
``tests/domains/journey/test_postgres_transaction_integration.py``: every test
is skipped unless ``AIFAMILY_TEST_DATABASE_URL`` is set (see
``tests/support/postgres.py`` and ``docker-compose.dev.yml``). This module
was authored and syntax/type checked in an environment with no local
PostgreSQL/Docker available, so it has **not** been run against a real
database yet — a developer with the dev-compose Postgres running must execute
it once to confirm the migration's schema and this adapter's SQL agree.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.domains.family_need.application.ports import NeedEvent
from backend.domains.family_need.domain.entities import (
    AssignmentPlan,
    FamilyConfirmedOutcome,
    FamilyNeed,
    NeedSignal,
)
from backend.domains.family_need.domain.errors import FamilyNeedConflictError
from backend.domains.family_need.domain.value_objects import (
    DataClass,
    FamilyOutcomeDecision,
    NeedContext,
    NeedSignalSource,
    SolutionComponentRef,
    SupplyShape,
)
from backend.domains.family_need.infrastructure.postgres_repository import (
    SqlAlchemyFamilyNeedRepository,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


def _context(**overrides) -> NeedContext:
    values = {
        "tenant_id": "tenant-1",
        "family_id": "family-1",
        "purpose": "FAMILY_NEED",
        "consent_version": "v1",
        "data_class": DataClass.MINOR_PERSONAL_DATA,
        "subject_person_ids": ("child-1",),
        "actor_id": "guardian-1",
    }
    values.update(overrides)
    return NeedContext(**values)


async def _apply_family_need_migration(engine) -> None:
    """Run just the family_need tables inside the test schema's search_path.

    The full Alembic history includes the 151-table legacy baseline, which is
    out of scope for a per-test disposable schema; instead this replays the
    0055 migration's `upgrade()` directly against the schema-scoped engine,
    matching how ``postgres_schema_engine`` already runs `metadata.create_all`
    for other domains' repository tests.
    """

    import importlib

    family_need_migration = importlib.import_module(
        "database.migrations.versions.0055_family_need_domain"
    )

    assignment_outcome_migration = importlib.import_module(
        "database.migrations.versions.0058_family_need_assignment_and_outcome"
    )

    assignment_resolution_migration = importlib.import_module(
        "database.migrations.versions.0059_family_need_assignment_plan_resolution"
    )

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_conn: _run_upgrade(sync_conn, family_need_migration))
        await connection.run_sync(
            lambda sync_conn: _run_upgrade(sync_conn, assignment_outcome_migration)
        )
        await connection.run_sync(
            lambda sync_conn: _run_upgrade(sync_conn, assignment_resolution_migration)
        )


def _run_upgrade(sync_connection, migration_module) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
    with Operations.context(context):
        migration_module.upgrade()


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_save_and_get_signal_round_trips_through_real_postgres() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_family_need_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyFamilyNeedRepository(connection)
            signal = NeedSignal.capture(
                context=_context(),
                source=NeedSignalSource.FAMILY_EXPRESSED,
                raw_text="孩子最近写作业总拖延，想找一个能一起坚持的小方法",
            )
            await repository.save_signal(signal)
            loaded = await repository.get_signal(
                tenant_id="tenant-1", family_id="family-1", signal_id=signal.signal_id
            )
            assert loaded == signal


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_save_need_rejects_version_regression() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_family_need_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyFamilyNeedRepository(connection)
            signal = NeedSignal.capture(
                context=_context(),
                source=NeedSignalSource.FAMILY_EXPRESSED,
                raw_text="孩子最近写作业总拖延，想找一个能一起坚持的小方法",
            )
            await repository.save_signal(signal)
            need = FamilyNeed.from_signal(
                signal,
                statement="家庭需要一个可持续的学习陪伴方法",
                desired_outcome="今晚能完成一个十分钟的共同小行动",
            )
            await repository.save_need(need)
            confirmed = need.confirm("guardian-1")
            await repository.save_need(confirmed)

            with pytest.raises(FamilyNeedConflictError):
                await repository.save_need(need)


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_append_event_enforces_idempotency_uniqueness() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_family_need_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyFamilyNeedRepository(connection)
            event = NeedEvent(
                event_name="NeedSignalCaptured",
                aggregate_id="signal-1",
                tenant_id="tenant-1",
                family_id="family-1",
                version=1,
                correlation_id="corr-1",
                occurred_at=datetime.now(UTC),
                idempotency_key="idem-1",
            )
            await repository.append_event(event)
            with pytest.raises(FamilyNeedConflictError):
                await repository.append_event(event)

            found = await repository.find_by_idempotency_key(
                tenant_id="tenant-1", family_id="family-1", idempotency_key="idem-1"
            )
            assert found is not None
            assert found.aggregate_id == "signal-1"


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_save_and_get_assignment_plan_round_trips_through_real_postgres() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_family_need_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyFamilyNeedRepository(connection)
            plan = AssignmentPlan.create(
                tenant_id="tenant-1",
                family_id="family-1",
                need_id="need-1",
                draft_id="draft-1",
                component_refs=(
                    SolutionComponentRef(
                        component_id="component-1", shape=SupplyShape.SERVICE, version="v1"
                    ),
                ),
                authorization_basis="family_confirmed_draft:draft-1",
            )
            await repository.save_assignment_plan(plan)
            loaded = await repository.get_assignment_plan(
                tenant_id="tenant-1", family_id="family-1", plan_id=plan.plan_id
            )
            assert loaded == plan

            other_tenant = await repository.get_assignment_plan(
                tenant_id="tenant-2", family_id="family-1", plan_id=plan.plan_id
            )
            assert other_tenant is None


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_resolved_assignment_plan_round_trips_through_real_postgres() -> None:
    """N4: once fulfilment succeeds, `AssignmentPlan.resolve()` must persist
    real resolution facts (not merely the original authorization), and a
    second `save_assignment_plan` call for the same `plan_id` must update the
    existing row rather than reject it as a replay mismatch."""

    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_family_need_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyFamilyNeedRepository(connection)
            plan = AssignmentPlan.create(
                tenant_id="tenant-1",
                family_id="family-1",
                need_id="need-1",
                draft_id="draft-1",
                component_refs=(
                    SolutionComponentRef(
                        component_id="component-1", shape=SupplyShape.SERVICE, version="v1"
                    ),
                ),
                authorization_basis="family_confirmed_draft:draft-1",
            )
            await repository.save_assignment_plan(plan)

            resolved = plan.resolve(
                resolved_slot_id="slot-real-1",
                resolved_booking_ref="booking-real-1",
            )
            await repository.save_assignment_plan(resolved)

            loaded = await repository.get_assignment_plan(
                tenant_id="tenant-1", family_id="family-1", plan_id=plan.plan_id
            )
            assert loaded == resolved
            assert loaded.resolved_slot_id == "slot-real-1"
            assert loaded.resolved_booking_ref == "booking-real-1"
            assert loaded.resolved_order_intent_ref is None
            # The authorization fact this plan started with must not have
            # been overwritten by resolving it.
            assert loaded.authorization_basis == "family_confirmed_draft:draft-1"


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_save_and_get_outcomes_for_need_round_trips_multiple_through_real_postgres() -> None:
    from sqlalchemy import MetaData

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_family_need_migration(engine)
        async with engine.begin() as connection:
            repository = SqlAlchemyFamilyNeedRepository(connection)
            first = FamilyConfirmedOutcome.confirm(
                context=_context(),
                need_id="need-1",
                fulfillment_ref="booking-service-record:booking-1",
                decision=FamilyOutcomeDecision.PARTIALLY_HELPED,
                confirmed_by="guardian-1",
                family_note="有一点帮助，还想再观察一下",
            )
            second = FamilyConfirmedOutcome.confirm(
                context=_context(),
                need_id="need-1",
                fulfillment_ref="course-completion:course-1",
                decision=FamilyOutcomeDecision.HELPED,
                confirmed_by="guardian-1",
                draft_id="draft-1",
            )
            await repository.save_outcome(first)
            await repository.save_outcome(second)

            loaded = await repository.get_outcomes_for_need(
                tenant_id="tenant-1", family_id="family-1", need_id="need-1"
            )
            assert loaded == (first, second)

            other_tenant = await repository.get_outcomes_for_need(
                tenant_id="tenant-2", family_id="family-1", need_id="need-1"
            )
            assert other_tenant == ()
