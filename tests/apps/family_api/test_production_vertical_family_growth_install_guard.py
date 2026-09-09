from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.apps.family_api.production_vertical_family_growth_wiring import (
    ProductionVerticalFamilyGrowthComposition,
)
from backend.intelligence.agi_vertical_durable import DurableVerticalLedgerAdapter
from backend.intelligence.agi_vertical_runtime import EvaluationLedger, VerticalFamilyGrowthRuntime


class _Port:
    durability_mode = "DURABLE"

    async def append(self, observation):
        raise AssertionError("not called")

    async def snapshot(self, *args, **kwargs):
        raise AssertionError("not called")

    async def read(self, *args, **kwargs):
        raise AssertionError("not called")

    async def delete_subject(self, *args, **kwargs):
        raise AssertionError("not called")


def _composition() -> ProductionVerticalFamilyGrowthComposition:
    runtime = VerticalFamilyGrowthRuntime(
        gateway=_Port(),
        context=_Port(),
        knowledge=_Port(),
        feedback=_Port(),
        ledger=EvaluationLedger(),
    )
    return ProductionVerticalFamilyGrowthComposition(
        environment="production",
        session_factory=async_sessionmaker(),
        runtime=runtime,
        context_broker=_Port(),
        durable_ledger=DurableVerticalLedgerAdapter(_Port()),
        scope_factory=lambda family_id: (family_id, family_id, (f"subject:{family_id}",)),
    )


def test_install_rejects_replacing_an_existing_runtime() -> None:
    composition = _composition()
    application = SimpleNamespace(state=SimpleNamespace())
    composition.install(application)

    other = _composition()
    with pytest.raises(RuntimeError, match="already configured"):
        other.install(application)


def test_install_is_idempotent_for_the_same_composition() -> None:
    composition = _composition()
    application = SimpleNamespace(state=SimpleNamespace())
    composition.install(application)
    first = application.state.vertical_family_growth_runtime

    composition.install(application)

    assert application.state.vertical_family_growth_runtime is first


def test_install_rejects_scope_factory_that_does_not_return_context_scope() -> None:
    composition = ProductionVerticalFamilyGrowthComposition(
        environment="production",
        session_factory=async_sessionmaker(),
        runtime=_composition().runtime,
        context_broker=_Port(),
        durable_ledger=DurableVerticalLedgerAdapter(_Port()),
        scope_factory=lambda family_id: (family_id, family_id, ("child",)),
    )
    application = SimpleNamespace(state=SimpleNamespace())
    composition.install(application)
    factory = application.state.vertical_family_growth_runtime._context_snapshot_factory

    import pytest

    async def invoke():
        await factory(family_id="family-a", run_id="run-a")

    with pytest.raises(ValueError, match="context scope mismatch"):
        import asyncio

        asyncio.run(invoke())
