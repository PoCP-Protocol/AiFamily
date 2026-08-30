from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.context_engine.async_port import (
    AsyncContextBrokerAdapter,
    AsyncContextBrokerPort,
)
from backend.intelligence.context_engine.contracts import (
    ContextScope,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.store import ContextBroker

NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)


def _scope(*, family_id: str = "family-1") -> ContextScope:
    return ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id=family_id,
        subject_ids=("child-1",),
        purpose="family-image-summary",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=DataClass.OPERATIONAL_TEXT,
        locale="zh-CN",
        deletion_ref="delete:1",
        correlation_id="corr:1",
        causation_id="cause:1",
    )


def _observation() -> StateObservation:
    return StateObservation(
        observation_id="observation-1",
        tenant_id="tenant-1",
        family_id="family-1",
        subject_id="child-1",
        dimension="expression",
        observed_value="calm",
        evidence_refs=("media:1",),
        provenance="test",
        observed_at=NOW,
        data_class=DataClass.OPERATIONAL_TEXT,
        purpose="family-image-summary",
        consent_version="consent.v1",
        consent_granted=True,
        deletion_ref="delete:1",
        correlation_id="corr:1",
        causation_id="cause:1",
        expires_at=NOW + timedelta(hours=1),
        retention_policy="test-1h",
    )


@pytest.mark.asyncio
async def test_async_adapter_is_a_non_blocking_port_and_preserves_snapshot_contract() -> None:
    adapter = AsyncContextBrokerAdapter(ContextBroker())
    assert isinstance(adapter, AsyncContextBrokerPort)

    await adapter.append(_observation())
    snapshot = await adapter.snapshot(scope=_scope(), now=NOW)
    replay = await adapter.read(snapshot.snapshot_ref, _scope(), now=NOW)

    assert snapshot.snapshot_ref == replay.snapshot_ref
    assert replay.source_refs == ("media:1",)
    assert adapter.durability_mode == "IN_MEMORY"


@pytest.mark.asyncio
async def test_async_adapter_keeps_scope_and_expiry_fail_closed() -> None:
    adapter = AsyncContextBrokerAdapter(ContextBroker())
    snapshot = await adapter.snapshot(scope=_scope(), now=NOW, snapshot_ttl=timedelta(minutes=1))

    with pytest.raises(ValueError, match="CROSS_FAMILY"):
        await adapter.read(snapshot.snapshot_ref, _scope(family_id="family-2"), now=NOW)
    with pytest.raises(ValueError, match="EXPIRED"):
        await adapter.read(snapshot.snapshot_ref, _scope(), now=NOW + timedelta(minutes=1))


@pytest.mark.asyncio
async def test_async_adapter_delete_subject_removes_future_reads() -> None:
    adapter = AsyncContextBrokerAdapter(ContextBroker())
    await adapter.append(_observation())
    snapshot = await adapter.snapshot(scope=_scope(), now=NOW)

    assert await adapter.delete_subject("tenant-1", "child-1") == 1
    with pytest.raises(ValueError, match="NOT_FOUND"):
        await adapter.read(snapshot.snapshot_ref, _scope(), now=NOW)
