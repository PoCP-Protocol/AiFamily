from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.domains.family_need.application.ports import NeedEvent
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.family_need_outcome_poller import (
    FamilyNeedOutcomeReflectionPoller,
)


class Reader:
    def __init__(self, event, outcome):
        self.events = (event,)
        self.outcome = outcome

    async def list_events(self, **kwargs):
        return self.events

    async def get_outcome(self, **kwargs):
        return self.outcome


class Writer:
    def __init__(self):
        self.calls = 0

    async def record_family_need_outcome(self, outcome, *, scope):
        self.calls += 1


class Resolver:
    async def resolve(self, *, tenant_id, family_id):
        return ContextScope(
            tenant_id=tenant_id, region_id="CN", family_id=family_id,
            subject_ids=("c",), purpose="growth", consent_version="v1",
            consent_granted=True, data_class=DataClass.MINOR_PERSONAL_DATA,
            locale="zh-CN", deletion_ref="d", correlation_id="c", causation_id="x",
        )


def _event():
    return NeedEvent(
        event_name="family_need.outcome_confirmed", aggregate_id="o1",
        tenant_id="t", family_id="f", version=1, correlation_id=None,
        occurred_at=datetime.now(UTC), purpose="growth", idempotency_key="k",
    )


@pytest.mark.asyncio
async def test_poller_runs_one_bounded_pass():
    writer = Writer()
    poller = FamilyNeedOutcomeReflectionPoller(
        Reader(_event(), SimpleNamespace(outcome_id="o1")),
        writer,
        Resolver(),
    )
    result = await poller.poll_once(tenant_id="t", family_id="f", limit=10)
    assert result.inspected == 1
    assert result.projected == 1
    assert result.empty is False
    assert result.has_unprojected is False
    assert writer.calls == 1


@pytest.mark.asyncio
async def test_poller_rejects_blank_scope_identity():
    poller = FamilyNeedOutcomeReflectionPoller(Reader(_event(), None), Writer(), Resolver())
    with pytest.raises(ValueError, match="tenant and family"):
        await poller.poll_once(tenant_id=" ", family_id="f")


@pytest.mark.asyncio
async def test_poller_rejects_invalid_limit_before_scope_resolution():
    class ExplodingResolver:
        async def resolve(self, **kwargs):
            raise AssertionError("scope must not be resolved")

    poller = FamilyNeedOutcomeReflectionPoller(
        Reader(_event(), SimpleNamespace(outcome_id="o1")), Writer(), ExplodingResolver()
    )
    with pytest.raises(ValueError, match="event limit"):
        await poller.poll_once(tenant_id="t", family_id="f", limit=0)


@pytest.mark.asyncio
async def test_poller_rejects_resolver_scope_drift():
    class DriftedResolver:
        async def resolve(self, **kwargs):
            scope = await Resolver().resolve(tenant_id="t", family_id="f")
            return ContextScope(
                tenant_id="other", region_id=scope.region_id, family_id=scope.family_id,
                subject_ids=scope.subject_ids, purpose=scope.purpose,
                consent_version=scope.consent_version, consent_granted=True,
                data_class=scope.data_class, locale=scope.locale,
                deletion_ref=scope.deletion_ref, correlation_id=scope.correlation_id,
                causation_id=scope.causation_id,
            )

    poller = FamilyNeedOutcomeReflectionPoller(
        Reader(_event(), SimpleNamespace(outcome_id="o1")), Writer(), DriftedResolver()
    )
    with pytest.raises(ValueError, match="resolved scope"):
        await poller.poll_once(tenant_id="t", family_id="f")


@pytest.mark.asyncio
async def test_poller_rejects_invalid_scope_type():
    class InvalidResolver:
        async def resolve(self, **kwargs):
            return object()

    poller = FamilyNeedOutcomeReflectionPoller(
        Reader(_event(), SimpleNamespace(outcome_id="o1")), Writer(), InvalidResolver()
    )
    with pytest.raises(TypeError, match="ContextScope"):
        await poller.poll_once(tenant_id="t", family_id="f")
