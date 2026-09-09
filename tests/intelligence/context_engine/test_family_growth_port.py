from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.context_engine.contracts import (
    ContextScope,
    ContextSnapshot,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.family_growth_port import (
    FAMILY_GROWTH_UNDERSTANDING_DIMENSIONS,
    SqlFamilyGrowthContextPort,
)

NOW = datetime(2026, 9, 9, tzinfo=UTC)


def scope(family_id: str = "family-a") -> ContextScope:
    return ContextScope(
        tenant_id="tenant-a", region_id="CN", family_id=family_id,
        subject_ids=("child-a",), purpose="family-growth-understanding",
        consent_version="consent.v1", consent_granted=True,
        data_class=DataClass.OPERATIONAL_TEXT, locale="zh-CN",
        deletion_ref="delete:a", correlation_id="corr:a", causation_id="cause:a",
    )


class Broker:
    durability_mode = "DURABLE"

    async def read(self, snapshot_ref, requested_scope):
        assert requested_scope == scope()
        observation = StateObservation(
            observation_id="obs:a", tenant_id="tenant-a", family_id="family-a",
            subject_id="child-a", dimension="focus", observed_value="作业启动",
            evidence_refs=("evidence:a",), provenance="test", observed_at=NOW,
            expires_at=NOW + timedelta(hours=1), data_class=DataClass.OPERATIONAL_TEXT,
            purpose=requested_scope.purpose, consent_version="consent.v1",
            consent_granted=True, deletion_ref="delete:a", correlation_id="corr:a",
            causation_id="cause:a", retention_policy="test",
        )
        return ContextSnapshot(
            snapshot_ref=snapshot_ref, scope=requested_scope, generated_at=NOW,
            observations=(observation,), expires_at=NOW + timedelta(minutes=5),
            provenance="context-broker:sql", deletion_ref="delete:a",
        )


@pytest.mark.asyncio
async def test_projects_durable_snapshot_to_family_growth_context() -> None:
    port = SqlFamilyGrowthContextPort(Broker(), scope)
    result = await port.read(family_id="family-a", context_snapshot_ref="context:run-a")
    assert result.family_id == "family-a"
    assert result.values["focus"] == "作业启动"
    assert result.values["data_class"] == "OPERATIONAL_TEXT"
    assert result.context_snapshot_ref == "context:run-a"
    assert result.values["required_dimensions"] == FAMILY_GROWTH_UNDERSTANDING_DIMENSIONS


@pytest.mark.asyncio
async def test_rejects_broker_result_that_is_not_canonical_snapshot() -> None:
    class InvalidBroker(Broker):
        async def read(self, snapshot_ref, requested_scope):
            return {"family_id": requested_scope.family_id}

    port = SqlFamilyGrowthContextPort(InvalidBroker(), scope)
    with pytest.raises(ValueError, match="CONTEXT_SNAPSHOT_INVALID"):
        await port.read(family_id="family-a", context_snapshot_ref="context:run-a")


@pytest.mark.asyncio
async def test_rejects_snapshot_with_scope_different_from_server_scope() -> None:
    class CrossFamilyBroker(Broker):
        async def read(self, snapshot_ref, requested_scope):
            snapshot = await super().read(snapshot_ref, requested_scope)
            return ContextSnapshot(
                snapshot_ref=snapshot.snapshot_ref,
                scope=scope("family-other"),
                generated_at=snapshot.generated_at,
                observations=(),
                expires_at=snapshot.expires_at,
                provenance=snapshot.provenance,
                deletion_ref="delete:a",
            )

    port = SqlFamilyGrowthContextPort(CrossFamilyBroker(), scope)
    with pytest.raises(ValueError, match="CONTEXT_SCOPE_MISMATCH"):
        await port.read(family_id="family-a", context_snapshot_ref="context:run-a")


def test_rejects_in_memory_broker() -> None:
    class InMemory(Broker):
        durability_mode = "IN_MEMORY"

    with pytest.raises(ValueError, match="durable broker"):
        SqlFamilyGrowthContextPort(InMemory(), scope)
