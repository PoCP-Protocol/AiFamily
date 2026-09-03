"""Purpose-bound feature signals for the experience and commerce loops.

The platform should retain useful signals such as view duration and transaction
amount.  This module makes their intended use explicit so an online recommender
cannot silently turn a financial fact or a child's interaction into a family
score.  The in-memory store is a dev/test adapter; an online/offline Feature
Store can implement the same append/query contract later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from backend.intelligence.experience.contracts import (
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    ScopeMismatchError,
)
from backend.platform.idempotency.keys import IdempotencyKey


class FeatureKind(StrEnum):
    VIEW_DURATION_SECONDS = "view_duration_seconds"
    CONTENT_COMPLETION_RATE = "content_completion_rate"
    TRANSACTION_AMOUNT_MINOR = "transaction_amount_minor"


class FeaturePurpose(StrEnum):
    UX_OPTIMIZATION = "ux_optimization"
    RECOMMENDATION_TUNING = "recommendation_tuning"
    REVENUE_REPORTING = "revenue_reporting"
    CAPACITY_PLANNING = "capacity_planning"


class FeatureGranularity(StrEnum):
    EVENT = "event"
    SESSION = "session"
    FAMILY_DAY = "family_day"
    TENANT_DAY = "tenant_day"


class RuntimeEnvironment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


@dataclass(frozen=True, slots=True)
class FeatureSignal:
    """An immutable, purpose-bound signal used by a feature pipeline."""

    signal_id: str
    kind: FeatureKind
    value: Decimal
    scope: ExperienceScope
    purpose: FeaturePurpose
    granularity: FeatureGranularity
    provenance: ExperienceProvenance
    idempotency_key: IdempotencyKey
    source_ref: str
    environment: RuntimeEnvironment
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.signal_id or not self.source_ref:
            raise ExperienceContractError("FEATURE_SIGNAL_ID_AND_SOURCE_REQUIRED")
        if not isinstance(self.kind, FeatureKind):
            raise ExperienceContractError("FEATURE_KIND_UNSUPPORTED")
        if not isinstance(self.scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not isinstance(self.purpose, FeaturePurpose):
            raise ExperienceContractError("FEATURE_PURPOSE_UNSUPPORTED")
        if not isinstance(self.granularity, FeatureGranularity):
            raise ExperienceContractError("FEATURE_GRANULARITY_UNSUPPORTED")
        if not isinstance(self.environment, RuntimeEnvironment):
            raise ExperienceContractError("FEATURE_ENVIRONMENT_UNSUPPORTED")
        if not isinstance(self.provenance, ExperienceProvenance):
            raise ExperienceContractError("PROVENANCE_REQUIRED")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise ExperienceContractError("IDEMPOTENCY_KEY_REQUIRED")
        if self.idempotency_key.tenant_id != self.scope.tenant_id:
            raise ScopeMismatchError("IDEMPOTENCY_TENANT_MISMATCH")
        try:
            value = Decimal(self.value)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ExperienceContractError("FEATURE_VALUE_UNSUPPORTED") from exc
        if not value.is_finite() or value < 0:
            raise ExperienceContractError("FEATURE_VALUE_MUST_BE_NON_NEGATIVE")
        object.__setattr__(self, "value", value)
        if self.kind is FeatureKind.CONTENT_COMPLETION_RATE and value > 1:
            raise ExperienceContractError("COMPLETION_RATE_OUT_OF_RANGE")
        if self.kind is FeatureKind.TRANSACTION_AMOUNT_MINOR and self.purpose not in {
            FeaturePurpose.REVENUE_REPORTING,
            FeaturePurpose.CAPACITY_PLANNING,
        }:
            raise ExperienceContractError("TRANSACTION_AMOUNT_PURPOSE_RESTRICTED")
        if (
            self.kind is FeatureKind.VIEW_DURATION_SECONDS
            and self.granularity is FeatureGranularity.EVENT
            and self.purpose is FeaturePurpose.RECOMMENDATION_TUNING
        ):
            raise ExperienceContractError("RAW_VIEW_DURATION_CANNOT_DIRECTLY_TUNE_RECOMMENDATION")


class InMemoryFeatureStore:
    """Append-only dev/test feature adapter with exact scope reads."""

    def __init__(self) -> None:
        self._signals_by_key: dict[str, FeatureSignal] = {}
        self._signals: list[FeatureSignal] = []

    def append(self, signal: FeatureSignal) -> FeatureSignal:
        existing = self._signals_by_key.get(signal.idempotency_key.scoped_value)
        if existing is not None:
            if existing != signal:
                raise ExperienceContractError("IDEMPOTENCY_REPLAY_MISMATCH")
            return existing
        self._signals_by_key[signal.idempotency_key.scoped_value] = signal
        self._signals.append(signal)
        return signal

    def read(
        self,
        scope: ExperienceScope,
        *,
        kind: FeatureKind | None = None,
    ) -> tuple[FeatureSignal, ...]:
        """Read only signals from the exact tenant/region/family/subject scope."""

        if not isinstance(scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        signals = [signal for signal in self._signals if _same_scope(signal.scope, scope)]
        if kind is not None:
            signals = [signal for signal in signals if signal.kind is kind]
        return tuple(sorted(signals, key=lambda signal: _as_utc(signal.observed_at)))

    def aggregate(self, scope: ExperienceScope, kind: FeatureKind) -> Decimal | None:
        """Return a simple sum for operational metrics, never a family score."""

        values = [signal.value for signal in self.read(scope, kind=kind)]
        return sum(values, Decimal("0")) if values else None


def _same_scope(left: ExperienceScope, right: ExperienceScope) -> bool:
    return (
        left.tenant_id == right.tenant_id
        and left.region_id == right.region_id
        and left.family_id == right.family_id
        and frozenset(left.subject_ids) == frozenset(right.subject_ids)
        and left.purpose == right.purpose
        and left.consent_version == right.consent_version
    )


def _as_utc(value: datetime) -> datetime:
    return (value if value.tzinfo is not None else value.replace(tzinfo=UTC)).astimezone(UTC)


__all__ = [
    "FeatureGranularity",
    "FeatureKind",
    "FeaturePurpose",
    "FeatureSignal",
    "InMemoryFeatureStore",
    "RuntimeEnvironment",
]
