from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.apps.family_api.production_vertical_family_growth_wiring import (
    ProductionVerticalFamilyGrowthComposition,
    build_sql_production_vertical_family_growth_composition,
)
from backend.intelligence.agi_vertical_durable import (
    DurableVerticalGrowthRuntime,
    DurableVerticalLedgerAdapter,
)
from backend.intelligence.agi_vertical_feedback import CombinedFeedbackPort
from backend.intelligence.agi_vertical_runtime import EvaluationLedger, VerticalFamilyGrowthRuntime
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.experience.run_http import RunScope


class _Port:
    durability_mode = "DURABLE"

    async def read(self, **kwargs):
        raise AssertionError("not called")


class _Context:
    durability_mode = "DURABLE"

    async def append(self, observation):
        raise AssertionError("not called")

    async def snapshot(self, *args, **kwargs):
        raise AssertionError("not called")

    async def read(self, *args, **kwargs):
        raise AssertionError("not called")

    async def delete_subject(self, *args, **kwargs):
        raise AssertionError("not called")


class _FeedbackLedger:
    async def feedback_refs(self, *, scope, family_need_id):
        return (f"decision:{scope.family_id}:{family_need_id}",)


class _InMemoryContext:
    durability_mode = "IN_MEMORY"

    async def append(self, observation):
        raise AssertionError("not called")

    async def snapshot(self, *args, **kwargs):
        raise AssertionError("not called")

    async def read(self, *args, **kwargs):
        raise AssertionError("not called")

    async def delete_subject(self, *args, **kwargs):
        raise AssertionError("not called")


def _runtime_with_context(context) -> VerticalFamilyGrowthRuntime:
    return VerticalFamilyGrowthRuntime(
        gateway=_Port(),
        context=context,
        knowledge=_Port(),
        feedback=_Port(),
        ledger=EvaluationLedger(),
    )


def _runtime() -> VerticalFamilyGrowthRuntime:
    return VerticalFamilyGrowthRuntime(
        gateway=_Port(),
        context=_Port(),
        knowledge=_Port(),
        feedback=_Port(),
        ledger=EvaluationLedger(),
    )


def _session_factory():
    return async_sessionmaker()


def _scope_factory(family_id: str) -> RunScope:
    return RunScope(family_id, family_id, (f"subject:{family_id}",))


def test_production_composition_requires_durable_context() -> None:
    with pytest.raises(ValueError, match="durable Context Broker"):
        ProductionVerticalFamilyGrowthComposition(
            environment="production",
            session_factory=_session_factory(),
            runtime=_runtime(),
            context_broker=_InMemoryContext(),
            durable_ledger=DurableVerticalLedgerAdapter(_Port()),
            scope_factory=_scope_factory,
        )


def test_production_composition_rejects_runtime_with_in_memory_context() -> None:
    with pytest.raises(ValueError, match="durable Context Port"):
        ProductionVerticalFamilyGrowthComposition(
            environment="production",
            session_factory=_session_factory(),
            runtime=_runtime_with_context(_InMemoryContext()),
            context_broker=_Context(),
            durable_ledger=DurableVerticalLedgerAdapter(_Port()),
            scope_factory=_scope_factory,
        )


def test_production_composition_installs_explicit_bundle() -> None:
    composition = ProductionVerticalFamilyGrowthComposition(
        environment="production",
        session_factory=_session_factory(),
        runtime=_runtime(),
        context_broker=_Context(),
        durable_ledger=DurableVerticalLedgerAdapter(_Port()),
        scope_factory=_scope_factory,
    )
    application = SimpleNamespace(state=SimpleNamespace())

    composition.install(application)

    assert isinstance(
        application.state.vertical_family_growth_runtime,
        DurableVerticalGrowthRuntime,
    )
    assert application.state.vertical_family_growth_runtime is not composition.runtime
    assert application.state.vertical_family_growth_context_broker is composition.context_broker


def test_sql_production_builder_injects_durable_family_growth_context_port() -> None:
    broker = _Context()
    ledger = DurableVerticalLedgerAdapter(_Port())

    def scope(family_id: str) -> ContextScope:
        return ContextScope(
            tenant_id=family_id,
            region_id="CN",
            family_id=family_id,
            subject_ids=(f"subject:{family_id}",),
            purpose="family-growth-understanding",
            consent_version="v1",
            consent_granted=True,
            data_class=DataClass.SYNTHETIC,
            locale="zh-CN",
            deletion_ref=f"delete:{family_id}",
            correlation_id="corr",
            causation_id="cause",
        )

    composition = build_sql_production_vertical_family_growth_composition(
        environment="production",
        session_factory=_session_factory(),
        gateway=_Port(),
        knowledge=_Port(),
        feedback=_Port(),
        ledger=EvaluationLedger(),
        durable_ledger=ledger,
        context_broker=broker,
        scope_factory=scope,
    )

    assert composition.runtime.context_durability_mode == "DURABLE"
    assert composition.runtime.context_port.broker is broker


@pytest.mark.asyncio
async def test_sql_production_builder_injects_durable_feedback_port() -> None:
    broker = _Context()
    durable_ledger = DurableVerticalLedgerAdapter(_FeedbackLedger())

    def scope(family_id: str) -> ContextScope:
        return ContextScope(
            tenant_id=family_id,
            region_id="CN",
            family_id=family_id,
            subject_ids=(f"subject:{family_id}",),
            purpose="family-growth-understanding",
            consent_version="v1",
            consent_granted=True,
            data_class=DataClass.SYNTHETIC,
            locale="zh-CN",
            deletion_ref=f"delete:{family_id}",
            correlation_id="corr",
            causation_id="cause",
        )

    composition = build_sql_production_vertical_family_growth_composition(
        environment="production",
        session_factory=_session_factory(),
        gateway=_Port(),
        knowledge=_Port(),
        feedback=_Port(),
        ledger=EvaluationLedger(),
        durable_ledger=durable_ledger,
        context_broker=broker,
        scope_factory=scope,
    )

    assert isinstance(composition.runtime.feedback_port, CombinedFeedbackPort)
    assert await composition.runtime.feedback_port.latest(family_need_id="need-1") == (
        "decision:need-1:need-1",
    )
