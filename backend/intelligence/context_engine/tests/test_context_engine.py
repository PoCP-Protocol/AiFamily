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


def context_scope(**overrides: object) -> ContextScope:
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
        "region_id": "CN",
        "locale": "zh-CN",
        "deletion_ref": "delete:obs-1",
        "correlation_id": "corr-1",
        "causation_id": "cause-1",
        "expires_at": datetime(2026, 1, 10, tzinfo=UTC),
        "retention_policy": "context.v1",
    }
    values.update(overrides)
    return StateObservation(**values)  # type: ignore[arg-type]


def test_snapshot_is_tenant_family_subject_and_purpose_scoped() -> None:
    broker = ContextBroker()
    broker.append(observation())
    broker.append(observation(observation_id="obs-2", tenant_id="other"))
    broker.append(observation(observation_id="obs-3", family_id="other-family"))
    broker.append(observation(observation_id="obs-4", purpose="other-purpose"))

    snapshot = broker.snapshot(scope=context_scope(), now=NOW)

    assert [item.observation_id for item in snapshot.observations] == ["obs-1"]
    assert snapshot.tenant_id == "tenant-1"
    assert snapshot.family_id == "family-1"
    assert snapshot.subject_ids == ("child-1",)
    assert snapshot.purpose == "family_growth_support"
    assert snapshot.snapshot_ref.startswith("context:tenant-1:family-1:")
    assert snapshot.source_refs == ("checkin-1",)


def test_snapshot_requires_complete_scope_and_rejects_mismatched_filters() -> None:
    broker = ContextBroker()
    broker.append(observation())
    with pytest.raises(ContextContractError, match="CONTEXT_SCOPE_REQUIRED"):
        broker.snapshot("tenant-1", "child-1", now=NOW)
    with pytest.raises(ContextScopeError, match="CROSS_TENANT_CONTEXT_QUERY"):
        broker.snapshot("tenant-2", scope=context_scope(), now=NOW)
    with pytest.raises(ContextScopeError, match="CONTEXT_SUBJECT_QUERY_DENIED"):
        broker.snapshot("tenant-1", "child-2", scope=context_scope(), now=NOW)


def test_minor_data_requires_explicit_retention_and_expiry() -> None:
    with pytest.raises(ContextContractError, match="expiry"):
        observation(expires_at=None)
    with pytest.raises(ContextContractError, match="retention_policy"):
        observation(retention_policy=None)


def test_observation_rejects_missing_scope_envelope_and_revoked_consent() -> None:
    with pytest.raises(ContextContractError, match="family_id"):
        observation(family_id="")
    with pytest.raises(ContextContractError, match="CONSENT_REVOKED"):
        observation(consent_granted=False)
    with pytest.raises(ContextContractError, match="CONSENT_REVOKED"):
        context_scope(consent_granted=False)


def test_expired_observations_are_excluded_and_expired_snapshot_is_rejected() -> None:
    broker = ContextBroker()
    broker.append(
        observation(
            observation_id="obs-expired",
            expires_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    snapshot = broker.snapshot(scope=context_scope(), now=NOW)
    assert snapshot.observations == ()

    fresh = broker.snapshot(
        scope=context_scope(),
        now=NOW,
        snapshot_ttl=timedelta(seconds=1),
    )
    with pytest.raises(ContextContractError, match="CONTEXT_SNAPSHOT_EXPIRED"):
        broker.read(fresh.snapshot_ref, context_scope(), now=NOW + timedelta(seconds=2))


def test_snapshot_projection_is_immutable_and_contains_no_unscoped_fields() -> None:
    broker = ContextBroker()
    broker.append(observation())
    snapshot = broker.snapshot(scope=context_scope(), now=NOW)
    projection = snapshot.read_only_projection

    assert projection["tenant_id"] == "tenant-1"
    assert projection["deletion_ref"] == "delete:family-1"
    assert projection["observations"][0]["subject_id"] == "child-1"
    with pytest.raises(TypeError):
        projection["tenant_id"] = "other"  # type: ignore[index]


def test_snapshot_read_rejects_cross_tenant_family_subject_and_deleted_scope() -> None:
    broker = ContextBroker()
    broker.append(observation())
    snapshot = broker.snapshot(scope=context_scope(), now=NOW)

    with pytest.raises(ContextScopeError, match="CROSS_TENANT_CONTEXT_SNAPSHOT"):
        broker.read(snapshot.snapshot_ref, context_scope(tenant_id="tenant-2"), now=NOW)
    with pytest.raises(ContextScopeError, match="CROSS_FAMILY_CONTEXT_SNAPSHOT"):
        broker.read(snapshot.snapshot_ref, context_scope(family_id="family-2"), now=NOW)
    with pytest.raises(ContextScopeError, match="CROSS_SUBJECT_CONTEXT_SNAPSHOT"):
        broker.read(snapshot.snapshot_ref, context_scope(subject_ids=("child-2",)), now=NOW)
    deleted_scope = replace(context_scope(), deletion_state="DELETED")
    with pytest.raises(ContextContractError, match="CONTEXT_DELETION_IN_PROGRESS"):
        broker.read(snapshot.snapshot_ref, deleted_scope, now=NOW)


def test_subject_erasure_removes_observations_and_snapshots() -> None:
    broker = ContextBroker()
    broker.append(observation())
    snapshot = broker.snapshot(scope=context_scope(), now=NOW)

    assert broker.delete_subject("tenant-1", "child-1") == 1
    assert broker.snapshot(scope=context_scope(), now=NOW).observations == ()
    with pytest.raises(ContextContractError, match="CONTEXT_SNAPSHOT_NOT_FOUND"):
        broker.read(snapshot.snapshot_ref, context_scope(), now=NOW)


def test_duplicate_observation_ids_are_tenant_scoped() -> None:
    broker = ContextBroker()
    broker.append(observation())
    broker.append(observation(tenant_id="tenant-2"))
    with pytest.raises(ContextContractError, match="OBSERVATION_ID_ALREADY_EXISTS"):
        broker.append(observation())
