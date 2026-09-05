from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)
from backend.intelligence.experience.experiments import (
    ExperimentAllocator,
    ExperimentDefinition,
    ExperimentStatus,
)
from backend.intelligence.experience.features import (
    FeatureGranularity,
    FeatureKind,
    FeaturePurpose,
    FeatureSignal,
    InMemoryFeatureStore,
    RuntimeEnvironment,
)
from backend.platform.idempotency.keys import IdempotencyKey


def _scope(
    *,
    tenant_id: str = "tenant-a",
    family_id: str = "family-a",
    subjects: tuple[str, ...] = ("child-a",),
) -> ExperienceScope:
    return ExperienceScope(
        global_id=f"global-{tenant_id}-{family_id}",
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subjects,
        purpose="growth_support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("delete-feature", "feature.v1"),
        correlation_id="corr-feature",
        causation_id="cause-feature",
    )


def _provenance() -> ExperienceProvenance:
    return ExperienceProvenance(
        provenance_ref="provenance-feature",
        source_refs=("mobile:UI-05",),
        kind=ProvenanceKind.SYNTHETIC_TEST,
        policy_version="feature-policy.v1",
    )


def _signal(
    signal_id: str,
    kind: FeatureKind,
    value: str,
    *,
    purpose: FeaturePurpose,
    granularity: FeatureGranularity = FeatureGranularity.SESSION,
    scope: ExperienceScope | None = None,
) -> FeatureSignal:
    actual_scope = scope or _scope()
    return FeatureSignal(
        signal_id=signal_id,
        kind=kind,
        value=Decimal(value),
        scope=actual_scope,
        purpose=purpose,
        granularity=granularity,
        provenance=_provenance(),
        idempotency_key=IdempotencyKey(actual_scope.tenant_id, signal_id),
        source_ref=f"event:{signal_id}",
        environment=RuntimeEnvironment.TEST,
        observed_at=datetime.now(UTC),
    )


def test_feature_store_keeps_duration_and_amount_with_purpose_boundaries() -> None:
    store = InMemoryFeatureStore()
    duration = _signal(
        "duration-001",
        FeatureKind.VIEW_DURATION_SECONDS,
        "42",
        purpose=FeaturePurpose.UX_OPTIMIZATION,
    )
    amount = _signal(
        "amount-001",
        FeatureKind.TRANSACTION_AMOUNT_MINOR,
        "19900",
        purpose=FeaturePurpose.REVENUE_REPORTING,
    )
    assert store.append(duration) is duration
    assert store.append(duration) is duration
    store.append(amount)
    assert store.aggregate(_scope(), FeatureKind.VIEW_DURATION_SECONDS) == Decimal("42")
    assert store.read(_scope(), kind=FeatureKind.TRANSACTION_AMOUNT_MINOR) == (amount,)


def test_feature_policy_rejects_raw_recommendation_duration_and_invalid_values() -> None:
    with pytest.raises(ExperienceContractError, match="RAW_VIEW_DURATION"):
        _signal(
            "duration-raw",
            FeatureKind.VIEW_DURATION_SECONDS,
            "12",
            purpose=FeaturePurpose.RECOMMENDATION_TUNING,
            granularity=FeatureGranularity.EVENT,
        )
    with pytest.raises(ExperienceContractError, match="TRANSACTION_AMOUNT_PURPOSE"):
        _signal(
            "amount-bad",
            FeatureKind.TRANSACTION_AMOUNT_MINOR,
            "100",
            purpose=FeaturePurpose.RECOMMENDATION_TUNING,
        )
    with pytest.raises(ExperienceContractError, match="COMPLETION_RATE"):
        _signal(
            "completion-bad",
            FeatureKind.CONTENT_COMPLETION_RATE,
            "1.1",
            purpose=FeaturePurpose.UX_OPTIMIZATION,
        )


def test_feature_store_isolates_tenants_and_rejects_replay_conflicts() -> None:
    store = InMemoryFeatureStore()
    first = _signal(
        "same-id",
        FeatureKind.VIEW_DURATION_SECONDS,
        "5",
        purpose=FeaturePurpose.UX_OPTIMIZATION,
    )
    store.append(first)
    other_tenant = _signal(
        "same-id",
        FeatureKind.VIEW_DURATION_SECONDS,
        "7",
        purpose=FeaturePurpose.UX_OPTIMIZATION,
        scope=_scope(tenant_id="tenant-b", family_id="family-b"),
    )
    store.append(other_tenant)
    assert store.aggregate(_scope(), FeatureKind.VIEW_DURATION_SECONDS) == Decimal("5")
    assert store.aggregate(
        _scope(tenant_id="tenant-b", family_id="family-b"),
        FeatureKind.VIEW_DURATION_SECONDS,
    ) == Decimal("7")

    conflict = _signal(
        "same-id",
        FeatureKind.VIEW_DURATION_SECONDS,
        "9",
        purpose=FeaturePurpose.UX_OPTIMIZATION,
    )
    with pytest.raises(ExperienceContractError, match="IDEMPOTENCY_REPLAY_MISMATCH"):
        store.append(conflict)


def test_experiment_assignment_is_stable_and_supports_family_exit() -> None:
    allocator = ExperimentAllocator()
    definition = ExperimentDefinition(
        experiment_id="exp-home-v1",
        version="1",
        variants=("control", "compact", "guided"),
        purpose="ux_optimization",
        status=ExperimentStatus.RUNNING,
    )
    first = allocator.assign(definition, _scope())
    second = allocator.assign(definition, _scope())
    assert first is not None
    assert first is second
    assert first.variant in definition.variants
    assert first.withdraw().opted_out is True


def test_experiment_rollout_and_minor_commercial_guardrails_are_explicit() -> None:
    allocator = ExperimentAllocator()
    zero = ExperimentDefinition(
        experiment_id="exp-zero",
        version="1",
        variants=("control", "treatment"),
        purpose="ux_optimization",
        status=ExperimentStatus.RUNNING,
        rollout_percentage=0,
    )
    assert allocator.assign(zero, _scope()) is None

    with pytest.raises(ExperienceContractError, match="MINOR_EXPERIMENT_PURPOSE"):
        allocator.assign(
            ExperimentDefinition(
                experiment_id="exp-sales",
                version="1",
                variants=("control", "treatment"),
                purpose="marketing",
                status=ExperimentStatus.RUNNING,
            ),
            _scope(),
        )

    with pytest.raises(ExperienceContractError, match="EXPERIMENT_NOT_RUNNING"):
        allocator.assign(
            ExperimentDefinition(
                experiment_id="exp-draft",
                version="1",
                variants=("control", "treatment"),
                purpose="ux_optimization",
            ),
            _scope(),
        )
