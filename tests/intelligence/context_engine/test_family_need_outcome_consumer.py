from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.domains.family_need.application.ports import NeedEvent
from backend.intelligence.context_engine.async_port import AsyncContextBrokerAdapter
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.family_need_outcome_consumer import (
    FamilyNeedOutcomeReflectionConsumer,
)
from backend.intelligence.context_engine.outcome_reflection import OutcomeReflectionContextWriter
from backend.intelligence.context_engine.store import ContextBroker


class Reader:
    def __init__(self, outcome):
        self.outcome = outcome

    async def get_outcome(self, **kwargs):
        return self.outcome

    async def list_events(self, **kwargs):
        return getattr(self, "events", ())


class Writer:
    def __init__(self):
        self.calls = []

    async def record_family_need_outcome(self, outcome, *, scope):
        self.calls.append((outcome, scope))


def _scope():
    return ContextScope(
        tenant_id="t", region_id="CN", family_id="f", subject_ids=("c",),
        purpose="growth", consent_version="v1", consent_granted=True,
        data_class=DataClass.MINOR_PERSONAL_DATA, locale="zh-CN", deletion_ref="d",
        correlation_id="c", causation_id="x",
    )


def _event():
    return NeedEvent(
        event_name="family_need.outcome_confirmed", aggregate_id="o1",
        tenant_id="t", family_id="f", version=1, correlation_id=None,
        occurred_at=datetime.now(UTC), purpose="growth", idempotency_key="k1",
    )


@pytest.mark.asyncio
async def test_consumer_projects_once_and_is_idempotent():
    outcome = SimpleNamespace(outcome_id="o1")
    writer = Writer()
    consumer = FamilyNeedOutcomeReflectionConsumer(Reader(outcome), writer)
    assert await consumer.consume(_event(), scope=_scope()) is True
    assert await consumer.consume(_event(), scope=_scope()) is True
    assert len(writer.calls) == 1


@pytest.mark.asyncio
async def test_consumer_ignores_other_events():
    writer = Writer()
    consumer = FamilyNeedOutcomeReflectionConsumer(Reader(None), writer)
    event = _event()
    event = NeedEvent(**{**event.__dict__, "event_name": "family_need.created"})
    assert await consumer.consume(event, scope=_scope()) is False
    assert writer.calls == []


@pytest.mark.asyncio
async def test_consumer_rejects_event_scope_drift_before_reading_outcome():
    writer = Writer()
    reader = Reader(SimpleNamespace(outcome_id="o1"))
    consumer = FamilyNeedOutcomeReflectionConsumer(reader, writer)
    event = NeedEvent(
        event_name="family_need.outcome_confirmed", aggregate_id="o1",
        tenant_id="other-tenant", family_id="f", version=1,
        correlation_id=None, occurred_at=datetime.now(UTC),
    )
    with pytest.raises(ValueError, match="event scope"):
        await consumer.consume(event, scope=_scope())
    assert writer.calls == []


@pytest.mark.asyncio
async def test_consumer_rejects_reader_aggregate_mismatch():
    writer = Writer()
    consumer = FamilyNeedOutcomeReflectionConsumer(
        Reader(SimpleNamespace(outcome_id="different")), writer
    )
    with pytest.raises(ValueError, match="aggregate mismatch"):
        await consumer.consume(_event(), scope=_scope())
    assert writer.calls == []


@pytest.mark.asyncio
async def test_consumer_rejects_purpose_drift():
    writer = Writer()
    consumer = FamilyNeedOutcomeReflectionConsumer(
        Reader(SimpleNamespace(outcome_id="o1")), writer
    )
    event = NeedEvent(
        event_name="family_need.outcome_confirmed", aggregate_id="o1",
        tenant_id="t", family_id="f", version=1, correlation_id=None,
        occurred_at=datetime.now(UTC), purpose="other-purpose",
    )
    with pytest.raises(ValueError, match="purpose mismatch"):
        await consumer.consume(event, scope=_scope())


@pytest.mark.asyncio
async def test_new_consumer_instance_replays_against_durable_projection_key():
    context = SimpleNamespace(
        tenant_id="t", family_id="f", subject_person_ids=("c",), consent_version="v1",
        deletion_ref="d",
    )
    outcome = SimpleNamespace(
        outcome_id="o1", need_id="n1", fulfillment_ref="a1", decision="HELPED",
        confirmed_by="g1", confirmed_at=datetime.now(UTC), context=context, family_note=None,
    )
    class DurableReplayProbe(ContextBroker):
        durability_mode = "DURABLE"

    broker = AsyncContextBrokerAdapter(DurableReplayProbe())
    event = _event()
    first = FamilyNeedOutcomeReflectionConsumer(
        Reader(outcome), OutcomeReflectionContextWriter(broker)
    )
    second = FamilyNeedOutcomeReflectionConsumer(
        Reader(outcome), OutcomeReflectionContextWriter(broker)
    )
    await first.consume(event, scope=_scope())
    await second.consume(event, scope=_scope())
    snapshot = await broker.snapshot(scope=_scope())
    assert len(snapshot.observations) == 1


@pytest.mark.asyncio
async def test_consume_pending_reads_bounded_outcome_event_batch():
    reader = Reader(SimpleNamespace(outcome_id="o1"))
    reader.events = (_event(),)
    writer = Writer()
    consumer = FamilyNeedOutcomeReflectionConsumer(reader, writer)
    assert await consumer.consume_pending(scope=_scope(), limit=10) == 1
    assert len(writer.calls) == 1
