"""Deterministic experiment assignment for experience strategies.

Assignments are family-scoped operational facts, not a ranking of families.
The same family receives the same variant for a strategy version, which makes
results reproducible across app restarts and across dev/test/prod adapters.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum

from backend.intelligence.experience.contracts import (
    ExperienceContractError,
    ExperienceScope,
    ScopeMismatchError,
)
from backend.platform.idempotency.keys import IdempotencyKey


class ExperimentStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    """A versioned strategy experiment with an explicit rollout percentage."""

    experiment_id: str
    version: str
    variants: tuple[str, ...]
    purpose: str
    status: ExperimentStatus = ExperimentStatus.DRAFT
    rollout_percentage: int = 100

    def __post_init__(self) -> None:
        if not self.experiment_id or not self.version or not self.purpose:
            raise ExperienceContractError("EXPERIMENT_ID_VERSION_PURPOSE_REQUIRED")
        if not isinstance(self.status, ExperimentStatus):
            raise ExperienceContractError("EXPERIMENT_STATUS_UNSUPPORTED")
        if not self.variants or any(not variant for variant in self.variants):
            raise ExperienceContractError("EXPERIMENT_VARIANTS_REQUIRED")
        if len(set(self.variants)) != len(self.variants):
            raise ExperienceContractError("EXPERIMENT_VARIANTS_MUST_BE_UNIQUE")
        if not 0 <= self.rollout_percentage <= 100:
            raise ExperienceContractError("EXPERIMENT_ROLLOUT_OUT_OF_RANGE")


@dataclass(frozen=True, slots=True)
class ExperimentAssignment:
    """A reproducible family-level assignment with an explicit exit flag."""

    assignment_id: str
    experiment_id: str
    version: str
    variant: str
    scope: ExperienceScope
    idempotency_key: IdempotencyKey
    assigned_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    opted_out: bool = False

    def __post_init__(self) -> None:
        if not self.assignment_id or not self.experiment_id or not self.version or not self.variant:
            raise ExperienceContractError("EXPERIMENT_ASSIGNMENT_FIELDS_REQUIRED")
        if not isinstance(self.scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise ExperienceContractError("IDEMPOTENCY_KEY_REQUIRED")
        if self.idempotency_key.tenant_id != self.scope.tenant_id:
            raise ScopeMismatchError("IDEMPOTENCY_TENANT_MISMATCH")

    def withdraw(self) -> ExperimentAssignment:
        """Opt this family out without deleting the historical assignment."""

        return replace(self, opted_out=True)


class InMemoryExperimentStore:
    """Append-only assignment adapter for dev/test and contract tests."""

    def __init__(self) -> None:
        self._assignments: dict[str, ExperimentAssignment] = {}

    def append(self, assignment: ExperimentAssignment) -> ExperimentAssignment:
        existing = self._assignments.get(assignment.idempotency_key.scoped_value)
        if existing is not None:
            if existing != assignment:
                raise ExperienceContractError("IDEMPOTENCY_REPLAY_MISMATCH")
            return existing
        self._assignments[assignment.idempotency_key.scoped_value] = assignment
        return assignment

    def get(self, experiment_id: str, scope: ExperienceScope) -> ExperimentAssignment | None:
        key = _assignment_key(experiment_id, scope)
        assignment = self._assignments.get(key.scoped_value)
        if assignment is None or not _same_scope(assignment.scope, scope):
            return None
        return assignment


class ExperimentAllocator:
    """Assign families to strategy variants using a stable hash bucket."""

    def __init__(self, store: InMemoryExperimentStore | None = None) -> None:
        self._store = store or InMemoryExperimentStore()

    def assign(
        self,
        definition: ExperimentDefinition,
        scope: ExperienceScope,
    ) -> ExperimentAssignment | None:
        if definition.status is not ExperimentStatus.RUNNING:
            raise ExperienceContractError("EXPERIMENT_NOT_RUNNING")
        if str(scope.data_class) == "MINOR_PERSONAL_DATA" and definition.purpose.lower() in {
            "marketing",
            "upsell",
            "sales",
        }:
            raise ExperienceContractError("MINOR_EXPERIMENT_PURPOSE_FORBIDDEN")
        key = _assignment_key(definition.experiment_id, scope)
        existing = self._store.get(definition.experiment_id, scope)
        if existing is not None:
            return existing
        bucket = _bucket(definition.experiment_id, definition.version, scope)
        if bucket >= definition.rollout_percentage:
            return None
        variant = definition.variants[bucket % len(definition.variants)]
        assignment = ExperimentAssignment(
            assignment_id=f"assignment:{definition.experiment_id}:{scope.family_id}",
            experiment_id=definition.experiment_id,
            version=definition.version,
            variant=variant,
            scope=scope,
            idempotency_key=key,
        )
        return self._store.append(assignment)


def _assignment_key(experiment_id: str, scope: ExperienceScope) -> IdempotencyKey:
    return IdempotencyKey(scope.tenant_id, f"experiment:{experiment_id}:{scope.family_id}")


def _bucket(experiment_id: str, version: str, scope: ExperienceScope) -> int:
    identity = "|".join((scope.tenant_id, scope.region_id, scope.family_id, experiment_id, version))
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 100


def _same_scope(left: ExperienceScope, right: ExperienceScope) -> bool:
    return (
        left.tenant_id == right.tenant_id
        and left.region_id == right.region_id
        and left.family_id == right.family_id
        and frozenset(left.subject_ids) == frozenset(right.subject_ids)
        and left.purpose == right.purpose
        and left.consent_version == right.consent_version
    )


__all__ = [
    "ExperimentAssignment",
    "ExperimentDefinition",
    "ExperimentAllocator",
    "ExperimentStatus",
    "InMemoryExperimentStore",
]
