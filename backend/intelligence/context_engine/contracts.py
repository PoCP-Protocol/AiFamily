"""Contracts for the read-only Family Context Broker boundary.

Context is an AI input projection, not a second copy of a family aggregate.  A
caller must provide a complete scope envelope before an observation can be
read.  The contract is deliberately provider/domain agnostic: the broker only
holds observations and immutable projections and never writes business facts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal


class ContextContractError(ValueError):
    """Base error for observations, scopes and snapshots."""


class ContextScopeError(ContextContractError):
    """Raised when a context read crosses a tenant/family/subject boundary."""


class DataClass(StrEnum):
    """Data classifications accepted by the context plane."""

    SYNTHETIC = "SYNTHETIC"
    OPERATIONAL_TEXT = "OPERATIONAL_TEXT"
    FAMILY_PRIVATE_TEXT = "FAMILY_PRIVATE_TEXT"
    MINOR_PERSONAL_DATA = "MINOR_PERSONAL_DATA"


_VALID_DELETION_STATES = frozenset({"ACTIVE", "PENDING", "DELETED"})


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContextContractError(f"{name} is required")


def _require_locale(name: str, value: str) -> None:
    _require_text(name, value)
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", value):
        raise ContextContractError(f"{name.upper()}_UNSUPPORTED")


def _normalise_moment(moment: datetime | None) -> datetime:
    value = moment or datetime.now(UTC)
    if value.tzinfo is None:
        raise ContextContractError("context timestamps require a timezone")
    return value


def _coerce_data_class(value: object) -> DataClass:
    if isinstance(value, DataClass):
        return value
    try:
        return DataClass(str(value))
    except ValueError as exc:
        raise ContextContractError("DATA_CLASS_UNSUPPORTED") from exc


@dataclass(frozen=True, slots=True)
class ContextScope:
    """The complete authorization and lifecycle envelope for a context read."""

    tenant_id: str
    region_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    purpose: str
    consent_version: str
    consent_granted: bool
    data_class: DataClass
    locale: str
    deletion_ref: str
    correlation_id: str
    causation_id: str
    content_locale: str | None = None
    model_locale: str | None = None
    policy_locale: str | None = None
    deletion_state: Literal["ACTIVE", "PENDING", "DELETED"] = "ACTIVE"

    def __post_init__(self) -> None:
        for name, value in (
            ("tenant_id", self.tenant_id),
            ("region_id", self.region_id),
            ("family_id", self.family_id),
            ("purpose", self.purpose),
            ("consent_version", self.consent_version),
            ("deletion_ref", self.deletion_ref),
            ("correlation_id", self.correlation_id),
            ("causation_id", self.causation_id),
        ):
            _require_text(name, value)
        if not isinstance(self.subject_ids, tuple) or not self.subject_ids:
            raise ContextContractError("subject_ids must be a non-empty tuple")
        if any(not isinstance(value, str) or not value.strip() for value in self.subject_ids):
            raise ContextContractError("subject_ids must contain non-empty ids")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise ContextContractError("subject_ids must not contain duplicates")
        object.__setattr__(self, "data_class", _coerce_data_class(self.data_class))
        if not re.fullmatch(r"[A-Z]{2,3}", self.region_id):
            raise ContextContractError("REGION_UNSUPPORTED")
        _require_locale("locale", self.locale)
        for name, value in (
            ("content_locale", self.content_locale),
            ("model_locale", self.model_locale),
            ("policy_locale", self.policy_locale),
        ):
            if value is not None:
                _require_locale(name, value)
        if self.deletion_state not in _VALID_DELETION_STATES:
            raise ContextContractError("DELETION_STATE_UNSUPPORTED")
        if not self.consent_granted:
            raise ContextContractError("CONSENT_REVOKED")

    def assert_active(self) -> None:
        if self.deletion_state != "ACTIVE":
            raise ContextContractError("CONTEXT_DELETION_IN_PROGRESS")
        if not self.consent_granted:
            raise ContextContractError("CONSENT_REVOKED")


@dataclass(frozen=True, slots=True)
class StateObservation:
    """An append-only observation with bounded retention and explicit scope."""

    observation_id: str
    tenant_id: str
    family_id: str
    subject_id: str
    dimension: str
    observed_value: str
    evidence_refs: tuple[str, ...]
    provenance: str
    observed_at: datetime
    data_class: DataClass
    purpose: str
    consent_version: str
    consent_granted: bool
    region_id: str = "CN"
    locale: str = "zh-CN"
    deletion_ref: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    expires_at: datetime | None = None
    retention_policy: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("observation_id", self.observation_id),
            ("tenant_id", self.tenant_id),
            ("family_id", self.family_id),
            ("subject_id", self.subject_id),
            ("dimension", self.dimension),
            ("observed_value", self.observed_value),
            ("provenance", self.provenance),
            ("purpose", self.purpose),
            ("consent_version", self.consent_version),
            ("deletion_ref", self.deletion_ref),
            ("correlation_id", self.correlation_id),
            ("causation_id", self.causation_id),
        ):
            _require_text(name, value)
        if not isinstance(self.evidence_refs, tuple) or not self.evidence_refs:
            raise ContextContractError("evidence_refs must be a non-empty tuple")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.evidence_refs):
            raise ContextContractError("evidence_refs must contain non-empty refs")
        object.__setattr__(self, "data_class", _coerce_data_class(self.data_class))
        if not re.fullmatch(r"[A-Z]{2,3}", self.region_id):
            raise ContextContractError("REGION_UNSUPPORTED")
        if self.observed_at.tzinfo is None:
            raise ContextContractError("observed_at requires a timezone")
        if self.expires_at is None:
            raise ContextContractError("observation expiry is required")
        if self.expires_at.tzinfo is None or self.expires_at <= self.observed_at:
            raise ContextContractError("observation expiry must follow observed_at")
        if not self.retention_policy:
            raise ContextContractError("retention_policy is required")
        if not self.consent_granted:
            raise ContextContractError("CONSENT_REVOKED")
        _require_locale("locale", self.locale)

    def is_expired(self, moment: datetime | None = None) -> bool:
        return self.expires_at <= _normalise_moment(moment)

    def assert_readable_by(self, scope: ContextScope, *, now: datetime | None = None) -> None:
        """Fail closed before a projection can include this observation."""

        scope.assert_active()
        if self.tenant_id != scope.tenant_id:
            raise ContextScopeError("CROSS_TENANT_CONTEXT_READ")
        if self.region_id != scope.region_id or self.family_id != scope.family_id:
            raise ContextScopeError("CROSS_FAMILY_CONTEXT_READ")
        if self.subject_id not in scope.subject_ids:
            raise ContextScopeError("CONTEXT_SUBJECT_READ_DENIED")
        if self.purpose != scope.purpose:
            raise ContextContractError("CONTEXT_PURPOSE_MISMATCH")
        if self.consent_version != scope.consent_version:
            raise ContextContractError("CONTEXT_CONSENT_VERSION_MISMATCH")
        if not self.consent_granted:
            raise ContextContractError("CONSENT_REVOKED")
        if self.is_expired(now):
            raise ContextContractError("CONTEXT_OBSERVATION_EXPIRED")


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    """An immutable, expiring, scope-bound read projection for AI reasoning."""

    snapshot_ref: str
    scope: ContextScope
    generated_at: datetime
    observations: tuple[StateObservation, ...]
    expires_at: datetime
    provenance: str
    deletion_ref: str
    redaction_policy_version: str = "context-redaction.v1"
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text("snapshot_ref", self.snapshot_ref)
        if not isinstance(self.scope, ContextScope):
            raise ContextContractError("CONTEXT_SCOPE_REQUIRED")
        self.scope.assert_active()
        if self.generated_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ContextContractError("snapshot timestamps require a timezone")
        if self.expires_at <= self.generated_at:
            raise ContextContractError("snapshot expiry must follow generated_at")
        _require_text("provenance", self.provenance)
        _require_text("deletion_ref", self.deletion_ref)
        _require_text("redaction_policy_version", self.redaction_policy_version)
        if not isinstance(self.observations, tuple):
            raise ContextContractError("observations must be immutable tuple")
        for observation in self.observations:
            if not isinstance(observation, StateObservation):
                raise ContextContractError("snapshot observations must be StateObservation")
            observation.assert_readable_by(self.scope, now=self.generated_at)
        if not isinstance(self.source_refs, tuple):
            raise ContextContractError("source_refs must be immutable tuple")
        expected_refs = tuple(
            ref for observation in self.observations for ref in observation.evidence_refs
        )
        if self.source_refs and self.source_refs != expected_refs:
            raise ContextContractError("SNAPSHOT_SOURCE_REFS_MISMATCH")
        if not self.source_refs and expected_refs:
            object.__setattr__(self, "source_refs", expected_refs)

    @property
    def tenant_id(self) -> str:
        return self.scope.tenant_id

    @property
    def region_id(self) -> str:
        return self.scope.region_id

    @property
    def family_id(self) -> str:
        return self.scope.family_id

    @property
    def subject_ids(self) -> tuple[str, ...]:
        return self.scope.subject_ids

    @property
    def subject_id(self) -> str | None:
        return self.subject_ids[0] if len(self.subject_ids) == 1 else None

    @property
    def purpose(self) -> str:
        return self.scope.purpose

    @property
    def consent_version(self) -> str:
        return self.scope.consent_version

    @property
    def consent_granted(self) -> bool:
        return self.scope.consent_granted

    @property
    def data_class(self) -> DataClass:
        return self.scope.data_class

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= datetime.now(UTC)

    @property
    def read_only_projection(self) -> Mapping[str, Any]:
        """Expose only the bounded projection passed to AI callers."""

        return MappingProxyType(
            {
                "snapshot_ref": self.snapshot_ref,
                "tenant_id": self.tenant_id,
                "region_id": self.region_id,
                "family_id": self.family_id,
                "subject_ids": self.subject_ids,
                "purpose": self.purpose,
                "consent_version": self.consent_version,
                "data_class": self.data_class.value,
                "provenance": self.provenance,
                "deletion_ref": self.deletion_ref,
                "expires_at": self.expires_at.isoformat(),
                "observations": tuple(
                    MappingProxyType(
                        {
                            "observation_id": item.observation_id,
                            "subject_id": item.subject_id,
                            "dimension": item.dimension,
                            "observed_value": item.observed_value,
                            "evidence_refs": item.evidence_refs,
                            "provenance": item.provenance,
                            "observed_at": item.observed_at.isoformat(),
                            "expires_at": item.expires_at.isoformat(),
                        }
                    )
                    for item in self.observations
                ),
            }
        )


__all__ = [
    "ContextContractError",
    "ContextScope",
    "ContextScopeError",
    "ContextSnapshot",
    "DataClass",
    "StateObservation",
]
