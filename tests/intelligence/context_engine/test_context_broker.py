from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    ContextScopeError,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.store import ContextBroker

NOW = datetime(2026, 1, 3, tzinfo=UTC)


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


def observation(**overrides: object) -> StateObservation:
    values: dict[str, object] = {
        "observation_id": "obs-1",
        "tenant_id": "tenant-1",
        "family_id": "family-1",
        "subject_id": "child-1",
        "dimension": "habit",
        "observed_value": "reads nightly",
        "evidence_refs": ("checkin-1",),
        "provenance": "user_report",
        "observed_at": datetime(2026, 1, 1, tzinfo=UTC),
        "data_class": DataClass.FAMILY_PRIVATE_TEXT,
        "purpose": "family_growth_support",
        "consent_version": "consent.v1",
        "consent_granted": True,
        "deletion_ref": "delete:obs-1",
        "correlation_id": "corr-1",
        "causation_id": "cause-1",
        "expires_at": datetime(2026, 1, 10, tzinfo=UTC),
        "retention_policy": "context.v1",
    }
    values.update(overrides)
    return StateObservation(**values)  # type: ignore[arg-type]


def test_broker_returns_minimal_scope_bound_projection() -> None:
    broker = ContextBroker()
    broker.append(observation())
    broker.append(observation(observation_id="foreign", tenant_id="tenant-2"))
    broker.append(observation(observation_id="other-purpose", purpose="other"))

    snapshot = broker.snapshot(scope=scope(), now=NOW)

    assert snapshot.tenant_id == "tenant-1"
    assert snapshot.family_id == "family-1"
    assert snapshot.subject_ids == ("child-1",)
    assert snapshot.purpose == "family_growth_support"
    assert [item.observation_id for item in snapshot.observations] == ["obs-1"]
    assert snapshot.read_only_projection["deletion_ref"] == "delete:family-1"
    with pytest.raises(TypeError):
        snapshot.read_only_projection["tenant_id"] = "tenant-2"  # type: ignore[index]


def test_broker_requires_complete_scope_and_rejects_cross_tenant_query() -> None:
    broker = ContextBroker()
    with pytest.raises(ContextContractError, match="CONTEXT_SCOPE_REQUIRED"):
        broker.snapshot("tenant-1", "child-1", now=NOW)
    with pytest.raises(ContextScopeError, match="CROSS_TENANT_CONTEXT_QUERY"):
        broker.snapshot("tenant-2", scope=scope(), now=NOW)


def test_context_read_rejects_cross_scope_expiry_revoke_and_delete() -> None:
    broker = ContextBroker()
    broker.append(observation())
    snapshot = broker.snapshot(scope=scope(), now=NOW)

    with pytest.raises(ContextScopeError, match="CROSS_TENANT_CONTEXT_SNAPSHOT"):
        broker.read(snapshot.snapshot_ref, scope(tenant_id="tenant-2"), now=NOW)
    with pytest.raises(ContextContractError, match="CONTEXT_SNAPSHOT_EXPIRED"):
        broker.read(
            snapshot.snapshot_ref,
            scope(),
            now=snapshot.expires_at + timedelta(seconds=1),
        )
    with pytest.raises(ContextContractError, match="CONSENT_REVOKED"):
        scope(consent_granted=False)
    with pytest.raises(ContextContractError, match="CONTEXT_DELETION_IN_PROGRESS"):
        broker.read(snapshot.snapshot_ref, replace(scope(), deletion_state="DELETED"), now=NOW)


def test_subject_delete_removes_observations_and_snapshot() -> None:
    broker = ContextBroker()
    broker.append(observation())
    snapshot = broker.snapshot(scope=scope(), now=NOW)

    assert broker.delete_subject("tenant-1", "child-1") == 1
    assert broker.snapshot(scope=scope(), now=NOW).observations == ()
    with pytest.raises(ContextContractError, match="CONTEXT_SNAPSHOT_NOT_FOUND"):
        broker.read(snapshot.snapshot_ref, scope(), now=NOW)


def test_observation_requires_bounded_retention_and_provenance() -> None:
    with pytest.raises(ContextContractError, match="expiry"):
        observation(expires_at=None)
    with pytest.raises(ContextContractError, match="provenance"):
        observation(provenance="")
    with pytest.raises(ContextContractError, match="REGION_UNSUPPORTED"):
        observation(region_id="cn")
