from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.apps.family_api.production_vertical_family_growth_wiring import (
    ProductionVerticalFamilyGrowthComposition,
    build_production_vertical_family_growth_durable_ledger,
)
from backend.intelligence.agi_vertical_durable import DurableVerticalLedgerAdapter
from backend.intelligence.agi_vertical_runtime import EvaluationLedger, VerticalFamilyGrowthRuntime
from backend.intelligence.context_engine.sql_store import build_sql_context_broker
from backend.intelligence.experience.run_http import RunScope
from backend.intelligence.experience.sql_run_ledger import SessionPerCallExperienceRunLedger


class _Port:
    durability_mode = "DURABLE"


def _runtime() -> VerticalFamilyGrowthRuntime:
    return VerticalFamilyGrowthRuntime(
        gateway=_Port(),
        context=_Port(),
        knowledge=_Port(),
        feedback=_Port(),
        ledger=EvaluationLedger(),
    )


def _scope_factory(family_id: str) -> RunScope:
    return RunScope(family_id, family_id, (f"subject:{family_id}",))


def test_production_composition_rejects_context_broker_from_other_session_factory() -> None:
    app_factory = async_sessionmaker()
    broker_factory = async_sessionmaker()
    broker = build_sql_context_broker(broker_factory)

    with pytest.raises(ValueError, match="session factory mismatch"):
        ProductionVerticalFamilyGrowthComposition(
            environment="production",
            session_factory=app_factory,
            runtime=_runtime(),
            context_broker=broker,
            durable_ledger=DurableVerticalLedgerAdapter(_Port()),
            scope_factory=_scope_factory,
        )


def test_production_composition_accepts_context_broker_from_same_session_factory() -> None:
    session_factory = async_sessionmaker()
    broker = build_sql_context_broker(session_factory)
    composition = ProductionVerticalFamilyGrowthComposition(
        environment="production",
        session_factory=session_factory,
        runtime=_runtime(),
        context_broker=broker,
        durable_ledger=DurableVerticalLedgerAdapter(_Port()),
        scope_factory=_scope_factory,
    )

    application = SimpleNamespace(state=SimpleNamespace())
    composition.install(application)
    assert application.state.vertical_family_growth_context_broker is broker


def test_production_durable_ledger_is_session_per_call() -> None:
    session_factory = async_sessionmaker()
    adapter = build_production_vertical_family_growth_durable_ledger(session_factory)

    assert isinstance(adapter._ledger, SessionPerCallExperienceRunLedger)
    assert adapter._ledger._session_factory is session_factory
