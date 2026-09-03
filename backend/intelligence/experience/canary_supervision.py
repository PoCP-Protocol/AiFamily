"""Provider-neutral canary SLO assessment and pre-authorized rollback."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, Index, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.evaluation.deployment import (
    DeploymentOperation,
    DeploymentPhase,
    DeploymentReceipt,
)
from backend.intelligence.evaluation.release_catalog import ReleaseCandidate
from backend.intelligence.evaluation.release_control import (
    ReleaseControlEvent,
    ReleaseControlRow,
)

from .release_bundle_deployment import FamilyExperienceReleaseDeploymentService


class CanarySupervisionError(ValueError):
    """Raised when canary evidence or rollback authority is unsafe."""


class CanaryRollbackBlockedError(CanarySupervisionError):
    """A breach was assessed, but its pre-authorized rollback could not execute."""

    def __init__(self, code: str, assessment: CanaryAssessment) -> None:
        super().__init__(code)
        self.code = code
        self.assessment = assessment


class CanaryHealth(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    HEALTHY = "HEALTHY"
    BREACHED = "BREACHED"


class CanaryAssessmentBase(DeclarativeBase):
    """Metadata-only persistence boundary for canary decisions."""


class CanaryAssessmentRow(CanaryAssessmentBase):
    __tablename__ = "ai_family_experience_canary_assessments"
    __table_args__ = (
        CheckConstraint(
            "health IN ('INSUFFICIENT_DATA', 'HEALTHY', 'BREACHED')",
            name="ck_ai_family_experience_canary_health",
        ),
        Index(
            "uq_ai_family_experience_canary_observation_policy",
            "observation_id",
            "policy_version",
            unique=True,
        ),
        Index(
            "ix_ai_family_experience_canary_candidate_environment",
            "candidate_id",
            "environment",
            "evaluated_at",
        ),
    )

    assessment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    health: Mapped[str] = mapped_column(String(32), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    observation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(256), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_rate: Mapped[float] = mapped_column(Float, nullable=False)
    p95_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    safety_violation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    minor_safety_violation_count: Mapped[int] = mapped_column(Integer, nullable=False)


@dataclass(frozen=True, slots=True)
class CanarySloPolicy:
    version: str
    min_request_count: int
    max_error_rate: float
    max_p95_latency_ms: int
    rollback_authorization_ttl_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise CanarySupervisionError("CANARY_POLICY_VERSION_REQUIRED")
        if (
            not isinstance(self.min_request_count, int)
            or isinstance(self.min_request_count, bool)
            or self.min_request_count <= 0
        ):
            raise CanarySupervisionError("CANARY_MIN_REQUEST_COUNT_INVALID")
        if (
            not isinstance(self.max_error_rate, (int, float))
            or isinstance(self.max_error_rate, bool)
            or not 0 <= self.max_error_rate <= 1
        ):
            raise CanarySupervisionError("CANARY_MAX_ERROR_RATE_INVALID")
        if (
            not isinstance(self.max_p95_latency_ms, int)
            or isinstance(self.max_p95_latency_ms, bool)
            or self.max_p95_latency_ms <= 0
        ):
            raise CanarySupervisionError("CANARY_MAX_LATENCY_INVALID")
        if (
            not isinstance(self.rollback_authorization_ttl_seconds, int)
            or isinstance(self.rollback_authorization_ttl_seconds, bool)
            or self.rollback_authorization_ttl_seconds <= 0
        ):
            raise CanarySupervisionError("ROLLBACK_AUTHORIZATION_TTL_INVALID")


@dataclass(frozen=True, slots=True)
class CanaryObservation:
    observation_id: str
    receipt_id: str
    candidate_id: str
    environment: str
    observed_at: datetime
    window_seconds: int
    request_count: int
    error_rate: float
    p95_latency_ms: int | None
    safety_violation_count: int
    minor_safety_violation_count: int

    def __post_init__(self) -> None:
        required = (
            self.observation_id,
            self.receipt_id,
            self.candidate_id,
            self.environment,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise CanarySupervisionError("CANARY_OBSERVATION_IDENTITY_REQUIRED")
        _aware(self.observed_at, "CANARY_OBSERVED_AT_MUST_BE_AWARE")
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in (
                self.window_seconds,
                self.request_count,
                self.safety_violation_count,
                self.minor_safety_violation_count,
            )
        ):
            raise CanarySupervisionError("CANARY_OBSERVATION_COUNTS_INVALID")
        if self.window_seconds <= 0 or self.request_count < 0:
            raise CanarySupervisionError("CANARY_OBSERVATION_COUNTS_INVALID")
        if (
            not isinstance(self.error_rate, (int, float))
            or isinstance(self.error_rate, bool)
            or not 0 <= self.error_rate <= 1
        ):
            raise CanarySupervisionError("CANARY_ERROR_RATE_INVALID")
        if self.p95_latency_ms is not None and (
            not isinstance(self.p95_latency_ms, int)
            or isinstance(self.p95_latency_ms, bool)
            or self.p95_latency_ms < 0
        ):
            raise CanarySupervisionError("CANARY_LATENCY_INVALID")
        if self.safety_violation_count < 0 or self.minor_safety_violation_count < 0:
            raise CanarySupervisionError("CANARY_SAFETY_COUNT_INVALID")


@dataclass(frozen=True, slots=True)
class CanaryAssessment:
    assessment_id: str
    health: CanaryHealth
    reasons: tuple[str, ...]
    policy_version: str
    observation_id: str
    receipt_id: str
    candidate_id: str
    environment: str
    observed_at: datetime
    evaluated_at: datetime
    window_seconds: int
    request_count: int
    error_rate: float
    p95_latency_ms: int | None
    safety_violation_count: int
    minor_safety_violation_count: int

    def __post_init__(self) -> None:
        _validate_assessment(self)


@dataclass(frozen=True, slots=True)
class CanarySupervisionResult:
    assessment: CanaryAssessment
    rollback_receipt: DeploymentReceipt | None


class CanaryObservationPort(Protocol):
    async def observe(
        self,
        candidate: ReleaseCandidate,
        canary_receipt: DeploymentReceipt,
        *,
        idempotency_key: str,
    ) -> CanaryObservation: ...


class RollbackControlReader(Protocol):
    async def get(self, control_id: str) -> ReleaseControlEvent | None: ...


class CanaryAssessmentStore(Protocol):
    async def get(self, assessment_id: str) -> CanaryAssessment | None: ...

    async def append(self, assessment: CanaryAssessment) -> CanaryAssessment: ...


class InMemoryCanaryAssessmentStore:
    def __init__(self) -> None:
        self._by_id: dict[str, CanaryAssessment] = {}
        self._by_observation_policy: dict[tuple[str, str], CanaryAssessment] = {}

    async def get(self, assessment_id: str) -> CanaryAssessment | None:
        return self._by_id.get(assessment_id)

    async def append(self, assessment: CanaryAssessment) -> CanaryAssessment:
        _validate_assessment(assessment)
        existing = self._by_id.get(assessment.assessment_id)
        bound = self._by_observation_policy.get(
            (assessment.observation_id, assessment.policy_version)
        )
        for stored in (existing, bound):
            if stored is not None and not _same_assessment(stored, assessment):
                raise CanarySupervisionError("CANARY_ASSESSMENT_CONFLICT")
        stored = existing or bound or assessment
        self._by_id[assessment.assessment_id] = stored
        self._by_observation_policy[
            (assessment.observation_id, assessment.policy_version)
        ] = stored
        return stored


class SqlAlchemyCanaryAssessmentStore:
    """Append-only SQL assessment ledger; caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, assessment_id: str) -> CanaryAssessment | None:
        row = await self._session.scalar(
            select(CanaryAssessmentRow).where(
                CanaryAssessmentRow.assessment_id == assessment_id
            )
        )
        return None if row is None else _stored_assessment(row)

    async def append(self, assessment: CanaryAssessment) -> CanaryAssessment:
        _validate_assessment(assessment)
        existing = await self.get(assessment.assessment_id)
        bound_row = await self._session.scalar(
            select(CanaryAssessmentRow).where(
                CanaryAssessmentRow.observation_id == assessment.observation_id,
                CanaryAssessmentRow.policy_version == assessment.policy_version,
            )
        )
        bound = None if bound_row is None else _stored_assessment(bound_row)
        for stored in (existing, bound):
            if stored is not None and not _same_assessment(stored, assessment):
                raise CanarySupervisionError("CANARY_ASSESSMENT_CONFLICT")
        stored = existing or bound
        if stored is not None:
            return stored
        self._session.add(_assessment_row(assessment))
        await self._session.flush()
        return assessment


class SessionPerCallCanaryAssessmentStore:
    """Transaction-per-call assessment store for long-lived schedulers."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def get(self, assessment_id: str) -> CanaryAssessment | None:
        async with self._session_factory() as session:
            return await SqlAlchemyCanaryAssessmentStore(session).get(assessment_id)

    async def append(self, assessment: CanaryAssessment) -> CanaryAssessment:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyCanaryAssessmentStore(session).append(assessment)


class InMemoryRollbackControlReader:
    def __init__(self, controls: tuple[ReleaseControlEvent, ...] = ()) -> None:
        self._controls = {control.control_id: control for control in controls}

    async def get(self, control_id: str) -> ReleaseControlEvent | None:
        return self._controls.get(control_id)


class SessionPerCallRollbackControlReader:
    """Read only controls already admitted through the verified SQL ledger."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def get(self, control_id: str) -> ReleaseControlEvent | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ReleaseControlRow).where(ReleaseControlRow.control_id == control_id)
            )
        if row is None:
            return None
        created_at = _database_aware(row.created_at)
        return ReleaseControlEvent(
            control_id=row.control_id,
            kind=row.kind,  # type: ignore[arg-type]
            idempotency_key=row.idempotency_key,
            decision_id=row.decision_id,
            candidate_id=row.candidate_id,
            environment=row.environment,
            actor_id=row.actor_id,
            target_candidate_id=row.target_candidate_id,
            reason=row.reason,
            signature_ref=row.signature_ref,
            signature_algorithm=row.signature_algorithm,
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class FamilyExperienceCanarySupervisor:
    observation_port: CanaryObservationPort
    rollback_controls: RollbackControlReader
    deployment: FamilyExperienceReleaseDeploymentService
    assessments: CanaryAssessmentStore
    policy: CanarySloPolicy
    clock: Callable[[], datetime] | None = None

    async def supervise(
        self,
        candidate: ReleaseCandidate,
        canary_receipt: DeploymentReceipt,
        *,
        rollback_control_id: str | None,
        idempotency_key: str,
    ) -> CanarySupervisionResult:
        _validate_canary_receipt(candidate, canary_receipt)
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise CanarySupervisionError("CANARY_IDEMPOTENCY_KEY_REQUIRED")
        observation = await self.observation_port.observe(
            candidate,
            canary_receipt,
            idempotency_key=idempotency_key,
        )
        _validate_observation(candidate, canary_receipt, observation)
        assessment = await self.assessments.append(
            assess_canary(observation, self.policy, evaluated_at=self._now())
        )
        if assessment.health is not CanaryHealth.BREACHED:
            return CanarySupervisionResult(assessment=assessment, rollback_receipt=None)
        try:
            if not rollback_control_id:
                raise CanarySupervisionError("PREAUTHORIZED_ROLLBACK_CONTROL_REQUIRED")
            control = await self.rollback_controls.get(rollback_control_id)
            if control is None:
                raise CanarySupervisionError("PREAUTHORIZED_ROLLBACK_CONTROL_NOT_FOUND")
            _validate_rollback_control(candidate, observation, control, self.policy)
            rollback_receipt = await self.deployment.rollback(
                candidate,
                control,
                human_actor=control.actor_id,
                idempotency_key=(
                    f"canary-rollback:{canary_receipt.receipt_id}:{control.control_id}"
                ),
            )
        except Exception as exc:
            raise CanaryRollbackBlockedError(_error_code(exc), assessment) from exc
        return CanarySupervisionResult(
            assessment=assessment,
            rollback_receipt=rollback_receipt,
        )

    def _now(self) -> datetime:
        value = self.clock() if self.clock is not None else datetime.now(UTC)
        return _aware(value, "CANARY_CLOCK_MUST_BE_AWARE")


def assess_canary(
    observation: CanaryObservation,
    policy: CanarySloPolicy,
    *,
    evaluated_at: datetime,
) -> CanaryAssessment:
    """Evaluate metadata only; safety violations are immediate hard stops."""

    if not isinstance(observation, CanaryObservation):
        raise CanarySupervisionError("CANARY_OBSERVATION_REQUIRED")
    if not isinstance(policy, CanarySloPolicy):
        raise CanarySupervisionError("CANARY_POLICY_REQUIRED")
    evaluated_at = _aware(evaluated_at, "CANARY_EVALUATED_AT_MUST_BE_AWARE")
    if evaluated_at < observation.observed_at:
        raise CanarySupervisionError("CANARY_EVALUATION_PRECEDES_OBSERVATION")
    reasons: list[str] = []
    if observation.minor_safety_violation_count > 0:
        reasons.append("minor_safety_violation")
    if observation.safety_violation_count > 0:
        reasons.append("safety_violation")
    if reasons:
        health = CanaryHealth.BREACHED
    elif observation.request_count < policy.min_request_count:
        health = CanaryHealth.INSUFFICIENT_DATA
        reasons.append("request_count_below_minimum")
    else:
        if observation.error_rate > policy.max_error_rate:
            reasons.append("error_rate_above_maximum")
        if observation.p95_latency_ms is None:
            reasons.append("p95_latency_missing")
        elif observation.p95_latency_ms > policy.max_p95_latency_ms:
            reasons.append("p95_latency_above_maximum")
        health = CanaryHealth.BREACHED if reasons else CanaryHealth.HEALTHY
    assessment_id = _digest(
        {
            "observation_id": observation.observation_id,
            "receipt_id": observation.receipt_id,
            "policy_version": policy.version,
            "health": health.value,
            "reasons": reasons,
            "candidate_id": observation.candidate_id,
            "environment": observation.environment,
            "observed_at": observation.observed_at.isoformat(),
            "window_seconds": observation.window_seconds,
            "request_count": observation.request_count,
            "error_rate": observation.error_rate,
            "p95_latency_ms": observation.p95_latency_ms,
            "safety_violation_count": observation.safety_violation_count,
            "minor_safety_violation_count": observation.minor_safety_violation_count,
        }
    )
    return CanaryAssessment(
        assessment_id=assessment_id,
        health=health,
        reasons=tuple(reasons),
        policy_version=policy.version,
        observation_id=observation.observation_id,
        receipt_id=observation.receipt_id,
        candidate_id=observation.candidate_id,
        environment=observation.environment,
        observed_at=observation.observed_at,
        evaluated_at=evaluated_at,
        window_seconds=observation.window_seconds,
        request_count=observation.request_count,
        error_rate=observation.error_rate,
        p95_latency_ms=observation.p95_latency_ms,
        safety_violation_count=observation.safety_violation_count,
        minor_safety_violation_count=observation.minor_safety_violation_count,
    )


def _validate_assessment(assessment: CanaryAssessment) -> None:
    if not isinstance(assessment, CanaryAssessment):
        raise CanarySupervisionError("CANARY_ASSESSMENT_REQUIRED")
    if not isinstance(assessment.health, CanaryHealth):
        raise CanarySupervisionError("CANARY_ASSESSMENT_HEALTH_INVALID")
    _aware(assessment.observed_at, "CANARY_OBSERVED_AT_MUST_BE_AWARE")
    _aware(assessment.evaluated_at, "CANARY_EVALUATED_AT_MUST_BE_AWARE")
    if assessment.evaluated_at < assessment.observed_at:
        raise CanarySupervisionError("CANARY_EVALUATION_PRECEDES_OBSERVATION")
    required = (
        assessment.assessment_id,
        assessment.policy_version,
        assessment.observation_id,
        assessment.receipt_id,
        assessment.candidate_id,
        assessment.environment,
    )
    if not all(isinstance(value, str) and value.strip() for value in required):
        raise CanarySupervisionError("CANARY_ASSESSMENT_IDENTITY_REQUIRED")
    if not isinstance(assessment.reasons, tuple) or any(
        not isinstance(reason, str) or not reason.strip() for reason in assessment.reasons
    ):
        raise CanarySupervisionError("CANARY_ASSESSMENT_REASONS_INVALID")
    allowed_reasons = {
        "minor_safety_violation",
        "safety_violation",
        "request_count_below_minimum",
        "error_rate_above_maximum",
        "p95_latency_missing",
        "p95_latency_above_maximum",
    }
    if any(reason not in allowed_reasons for reason in assessment.reasons):
        raise CanarySupervisionError("CANARY_ASSESSMENT_REASON_UNKNOWN")
    if (assessment.health is CanaryHealth.HEALTHY) != (not assessment.reasons):
        raise CanarySupervisionError("CANARY_ASSESSMENT_HEALTH_REASON_MISMATCH")
    CanaryObservation(
        observation_id=assessment.observation_id,
        receipt_id=assessment.receipt_id,
        candidate_id=assessment.candidate_id,
        environment=assessment.environment,
        observed_at=assessment.observed_at,
        window_seconds=assessment.window_seconds,
        request_count=assessment.request_count,
        error_rate=assessment.error_rate,
        p95_latency_ms=assessment.p95_latency_ms,
        safety_violation_count=assessment.safety_violation_count,
        minor_safety_violation_count=assessment.minor_safety_violation_count,
    )
    expected_id = _digest(
        {
            "observation_id": assessment.observation_id,
            "receipt_id": assessment.receipt_id,
            "policy_version": assessment.policy_version,
            "health": assessment.health.value,
            "reasons": list(assessment.reasons),
            "candidate_id": assessment.candidate_id,
            "environment": assessment.environment,
            "observed_at": assessment.observed_at.isoformat(),
            "window_seconds": assessment.window_seconds,
            "request_count": assessment.request_count,
            "error_rate": assessment.error_rate,
            "p95_latency_ms": assessment.p95_latency_ms,
            "safety_violation_count": assessment.safety_violation_count,
            "minor_safety_violation_count": assessment.minor_safety_violation_count,
        }
    )
    if assessment.assessment_id != expected_id:
        raise CanarySupervisionError("CANARY_ASSESSMENT_DIGEST_MISMATCH")


def _same_assessment(left: CanaryAssessment, right: CanaryAssessment) -> bool:
    return _normalized_assessment(left) == _normalized_assessment(right)


def _normalized_assessment(assessment: CanaryAssessment) -> CanaryAssessment:
    """Normalize replay-only wall clock without weakening assessment identity."""

    return CanaryAssessment(
        assessment_id=assessment.assessment_id,
        health=assessment.health,
        reasons=assessment.reasons,
        policy_version=assessment.policy_version,
        observation_id=assessment.observation_id,
        receipt_id=assessment.receipt_id,
        candidate_id=assessment.candidate_id,
        environment=assessment.environment,
        observed_at=assessment.observed_at,
        evaluated_at=assessment.observed_at,
        window_seconds=assessment.window_seconds,
        request_count=assessment.request_count,
        error_rate=assessment.error_rate,
        p95_latency_ms=assessment.p95_latency_ms,
        safety_violation_count=assessment.safety_violation_count,
        minor_safety_violation_count=assessment.minor_safety_violation_count,
    )


def _assessment_row(assessment: CanaryAssessment) -> CanaryAssessmentRow:
    return CanaryAssessmentRow(
        assessment_id=assessment.assessment_id,
        health=assessment.health.value,
        reasons=list(assessment.reasons),
        policy_version=assessment.policy_version,
        observation_id=assessment.observation_id,
        receipt_id=assessment.receipt_id,
        candidate_id=assessment.candidate_id,
        environment=assessment.environment,
        observed_at=assessment.observed_at,
        evaluated_at=assessment.evaluated_at,
        window_seconds=assessment.window_seconds,
        request_count=assessment.request_count,
        error_rate=assessment.error_rate,
        p95_latency_ms=assessment.p95_latency_ms,
        safety_violation_count=assessment.safety_violation_count,
        minor_safety_violation_count=assessment.minor_safety_violation_count,
    )


def _stored_assessment(row: CanaryAssessmentRow) -> CanaryAssessment:
    try:
        health = CanaryHealth(row.health)
    except ValueError as exc:
        raise CanarySupervisionError("PERSISTED_CANARY_HEALTH_INVALID") from exc
    if not isinstance(row.reasons, list) or any(
        not isinstance(reason, str) for reason in row.reasons
    ):
        raise CanarySupervisionError("PERSISTED_CANARY_REASONS_INVALID")
    return CanaryAssessment(
        assessment_id=row.assessment_id,
        health=health,
        reasons=tuple(row.reasons),
        policy_version=row.policy_version,
        observation_id=row.observation_id,
        receipt_id=row.receipt_id,
        candidate_id=row.candidate_id,
        environment=row.environment,
        observed_at=_database_aware(row.observed_at),
        evaluated_at=_database_aware(row.evaluated_at),
        window_seconds=row.window_seconds,
        request_count=row.request_count,
        error_rate=row.error_rate,
        p95_latency_ms=row.p95_latency_ms,
        safety_violation_count=row.safety_violation_count,
        minor_safety_violation_count=row.minor_safety_violation_count,
    )


def _database_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _validate_canary_receipt(
    candidate: ReleaseCandidate, receipt: DeploymentReceipt
) -> None:
    if not isinstance(receipt, DeploymentReceipt):
        raise CanarySupervisionError("CANARY_RECEIPT_REQUIRED")
    if receipt.operation is not DeploymentOperation.APPLY:
        raise CanarySupervisionError("CANARY_APPLY_RECEIPT_REQUIRED")
    if receipt.phase is not DeploymentPhase.CANARY:
        raise CanarySupervisionError("CANARY_PHASE_RECEIPT_REQUIRED")
    if (
        receipt.candidate_id != candidate.candidate_id
        or receipt.environment != candidate.environment
    ):
        raise CanarySupervisionError("CANARY_RECEIPT_CANDIDATE_MISMATCH")


def _validate_observation(
    candidate: ReleaseCandidate,
    receipt: DeploymentReceipt,
    observation: CanaryObservation,
) -> None:
    if not isinstance(observation, CanaryObservation):
        raise CanarySupervisionError("CANARY_OBSERVATION_REQUIRED")
    if (
        observation.receipt_id != receipt.receipt_id
        or observation.candidate_id != candidate.candidate_id
        or observation.environment != candidate.environment
    ):
        raise CanarySupervisionError("CANARY_OBSERVATION_SCOPE_MISMATCH")
    if observation.observed_at < receipt.created_at:
        raise CanarySupervisionError("CANARY_OBSERVATION_PRECEDES_DEPLOYMENT")


def _validate_rollback_control(
    candidate: ReleaseCandidate,
    observation: CanaryObservation,
    control: ReleaseControlEvent,
    policy: CanarySloPolicy,
) -> None:
    if (
        control.kind != "ROLLBACK"
        or control.candidate_id != candidate.candidate_id
        or control.environment != candidate.environment
        or control.decision_id != candidate.decision_id
        or not control.target_candidate_id
        or control.target_candidate_id == candidate.candidate_id
    ):
        raise CanarySupervisionError("PREAUTHORIZED_ROLLBACK_CONTROL_MISMATCH")
    if control.actor_id.startswith("ai:") or not control.signature_ref:
        raise CanarySupervisionError("PREAUTHORIZED_ROLLBACK_HUMAN_SIGNATURE_REQUIRED")
    age_seconds = (observation.observed_at - control.created_at).total_seconds()
    if age_seconds < 0:
        raise CanarySupervisionError("ROLLBACK_CONTROL_CREATED_AFTER_OBSERVATION")
    if age_seconds > policy.rollback_authorization_ttl_seconds:
        raise CanarySupervisionError("ROLLBACK_CONTROL_EXPIRED")


def _aware(value: datetime, code: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanarySupervisionError(code)
    return value


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _error_code(error: Exception) -> str:
    if isinstance(error, CanarySupervisionError) and error.args:
        code = error.args[0]
        if isinstance(code, str) and code.strip():
            return code[:128]
    args = getattr(error, "args", ())
    if args and isinstance(args[0], str) and args[0].strip():
        return args[0][:128]
    return type(error).__name__.upper()[:128]


__all__ = [
    "CanaryAssessment",
    "CanaryAssessmentBase",
    "CanaryAssessmentRow",
    "CanaryAssessmentStore",
    "CanaryHealth",
    "CanaryObservation",
    "CanaryObservationPort",
    "CanaryRollbackBlockedError",
    "CanarySloPolicy",
    "CanarySupervisionError",
    "CanarySupervisionResult",
    "FamilyExperienceCanarySupervisor",
    "InMemoryCanaryAssessmentStore",
    "InMemoryRollbackControlReader",
    "RollbackControlReader",
    "SessionPerCallRollbackControlReader",
    "SessionPerCallCanaryAssessmentStore",
    "SqlAlchemyCanaryAssessmentStore",
    "assess_canary",
]
