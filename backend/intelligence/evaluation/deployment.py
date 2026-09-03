"""Provider-neutral deployment and rollout boundary for approved candidates.

AI evaluation owns admission evidence and human control.  This module is the
last application seam before an external deployment platform: it validates the
approved candidate/control pair, calls an injected ``DeploymentPort``, and
stores a metadata-only receipt.  It never reads credentials or imports a
provider SDK, and it has no synthetic default adapter.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.evaluation.release_catalog import (
    ReleaseCandidate,
    ReleaseCandidateStatus,
)
from backend.intelligence.evaluation.release_control import ReleaseControlEvent
from backend.intelligence.observability import (
    SpanStatus,
    TelemetryContext,
    TelemetrySink,
    TelemetrySpanHandle,
)


class DeploymentError(ValueError):
    """Raised when a deployment request is not safe or cannot be recorded."""


class DeploymentOperation(StrEnum):
    APPLY = "APPLY"
    ROLLBACK = "ROLLBACK"


class DeploymentPhase(StrEnum):
    CANARY = "CANARY"
    ACTIVE = "ACTIVE"
    ROLLED_BACK = "ROLLED_BACK"


class DeploymentBase(DeclarativeBase):
    """Metadata boundary owned by the deployment receipt adapter."""


class DeploymentReceiptRow(DeploymentBase):
    __tablename__ = "ai_release_deployment_receipts"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('APPLY', 'ROLLBACK')",
            name="ck_ai_release_deployment_receipts_operation",
        ),
        CheckConstraint(
            "phase IN ('CANARY', 'ACTIVE', 'ROLLED_BACK')",
            name="ck_ai_release_deployment_receipts_phase",
        ),
        Index("uq_ai_release_deployment_receipts_idempotency", "idempotency_key", unique=True),
        Index(
            "ix_ai_release_deployment_receipts_candidate_environment",
            "candidate_id",
            "environment",
            "created_at",
        ),
    )

    receipt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(256), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(256), nullable=False)
    rollout_percent: Mapped[int] = mapped_column(nullable=False)
    external_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class DeploymentResult:
    """Minimal response returned by an external deployment adapter."""

    external_ref: str


@dataclass(frozen=True, slots=True)
class DeploymentReceipt:
    receipt_id: str
    operation: DeploymentOperation
    phase: DeploymentPhase
    idempotency_key: str
    candidate_id: str
    environment: str
    control_id: str
    actor_id: str
    rollout_percent: int
    external_ref: str
    created_at: datetime


class DeploymentPort(Protocol):
    """Adapter implemented by a deployment platform, never by AI Runtime."""

    async def apply(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        phase: DeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> DeploymentResult: ...

    async def rollback(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        idempotency_key: str,
    ) -> DeploymentResult: ...


class DeploymentReceiptStore(Protocol):
    async def get(self, idempotency_key: str) -> DeploymentReceipt | None: ...

    async def append(self, receipt: DeploymentReceipt) -> DeploymentReceipt: ...


class InMemoryDeploymentReceiptStore:
    def __init__(self) -> None:
        self.receipts: dict[str, DeploymentReceipt] = {}

    async def get(self, idempotency_key: str) -> DeploymentReceipt | None:
        return self.receipts.get(idempotency_key)

    async def append(self, receipt: DeploymentReceipt) -> DeploymentReceipt:
        existing = self.receipts.get(receipt.idempotency_key)
        if existing is not None and existing != receipt:
            raise DeploymentError("DEPLOYMENT_IDEMPOTENCY_CONFLICT")
        self.receipts[receipt.idempotency_key] = receipt
        return existing or receipt


class SqlAlchemyDeploymentReceiptStore:
    """SQL metadata-only receipt ledger; caller owns commit/rollback."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, idempotency_key: str) -> DeploymentReceipt | None:
        row = await self._session.scalar(
            select(DeploymentReceiptRow).where(
                DeploymentReceiptRow.idempotency_key == idempotency_key
            )
        )
        return None if row is None else _stored(row)

    async def append(self, receipt: DeploymentReceipt) -> DeploymentReceipt:
        _validate_receipt(receipt)
        existing = await self.get(receipt.idempotency_key)
        if existing is not None:
            if existing != receipt:
                raise DeploymentError("DEPLOYMENT_IDEMPOTENCY_CONFLICT")
            return existing
        self._session.add(_row_from_receipt(receipt))
        await self._session.flush()
        return receipt


@dataclass(frozen=True, slots=True)
class ReleaseDeploymentService:
    """Validate human control, call the external port, and persist a receipt."""

    port: DeploymentPort
    receipts: DeploymentReceiptStore
    clock: Callable[[], datetime] | None = None
    telemetry_sink: TelemetrySink | None = None

    async def apply(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        human_actor: str,
        phase: DeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> DeploymentReceipt:
        _validate_request(
            candidate,
            control,
            human_actor=human_actor,
            expected_operation=DeploymentOperation.APPLY,
            phase=phase,
            rollout_percent=rollout_percent,
            idempotency_key=idempotency_key,
        )
        existing = await self.receipts.get(idempotency_key)
        if existing is not None:
            return existing
        span = await self._start_telemetry(
            candidate,
            operation=DeploymentOperation.APPLY,
            phase=phase,
            idempotency_key=idempotency_key,
        )
        try:
            result = await self.port.apply(
                candidate,
                control,
                phase=phase,
                rollout_percent=rollout_percent,
                idempotency_key=idempotency_key,
            )
            receipt = await self.receipts.append(
                _receipt(
                    candidate,
                    control,
                    operation=DeploymentOperation.APPLY,
                    phase=phase,
                    rollout_percent=rollout_percent,
                    idempotency_key=idempotency_key,
                    external_ref=result.external_ref,
                    created_at=self._now(),
                )
            )
        except Exception as exc:
            await self._finish_telemetry(span, status="ERROR", error_code=_error_code(exc))
            raise
        await self._finish_telemetry(span, status="OK")
        return receipt

    async def rollback(
        self,
        candidate: ReleaseCandidate,
        control: ReleaseControlEvent,
        *,
        human_actor: str,
        idempotency_key: str,
    ) -> DeploymentReceipt:
        _validate_request(
            candidate,
            control,
            human_actor=human_actor,
            expected_operation=DeploymentOperation.ROLLBACK,
            phase=DeploymentPhase.ROLLED_BACK,
            rollout_percent=0,
            idempotency_key=idempotency_key,
        )
        existing = await self.receipts.get(idempotency_key)
        if existing is not None:
            return existing
        span = await self._start_telemetry(
            candidate,
            operation=DeploymentOperation.ROLLBACK,
            phase=DeploymentPhase.ROLLED_BACK,
            idempotency_key=idempotency_key,
        )
        try:
            result = await self.port.rollback(candidate, control, idempotency_key=idempotency_key)
            receipt = await self.receipts.append(
                _receipt(
                    candidate,
                    control,
                    operation=DeploymentOperation.ROLLBACK,
                    phase=DeploymentPhase.ROLLED_BACK,
                    rollout_percent=0,
                    idempotency_key=idempotency_key,
                    external_ref=result.external_ref,
                    created_at=self._now(),
                )
            )
        except Exception as exc:
            await self._finish_telemetry(span, status="ERROR", error_code=_error_code(exc))
            raise
        await self._finish_telemetry(span, status="OK")
        return receipt

    def _now(self) -> datetime:
        value = self.clock() if self.clock is not None else datetime.now(UTC)
        if value.tzinfo is None or value.utcoffset() is None:
            raise DeploymentError("CLOCK_MUST_BE_TIMEZONE_AWARE")
        return value

    async def _start_telemetry(
        self,
        candidate: ReleaseCandidate,
        *,
        operation: DeploymentOperation,
        phase: DeploymentPhase,
        idempotency_key: str,
    ) -> TelemetrySpanHandle | None:
        if self.telemetry_sink is None:
            return None
        context = TelemetryContext(
            trace_id=_deployment_trace_id(candidate),
            operation_id=f"{operation.value.lower()}:{idempotency_key}",
            use_case="AI_RELEASE_DEPLOYMENT",
            data_class="OPERATIONAL_TEXT",
        )
        return await self.telemetry_sink.start_span(
            name="ai.release.deployment",
            context=context,
            attributes={
                "provider_id": candidate.provider_id,
                "model": candidate.model,
                "model_version": candidate.model_version,
                "environment": candidate.environment,
                "stage": phase.value,
            },
        )

    async def _finish_telemetry(
        self,
        span: TelemetrySpanHandle | None,
        *,
        status: SpanStatus,
        error_code: str | None = None,
    ) -> None:
        if span is None or self.telemetry_sink is None:
            return
        await self.telemetry_sink.finish_span(
            span,
            status=status,
            error_code=error_code,
        )


def _validate_request(
    candidate: ReleaseCandidate,
    control: ReleaseControlEvent,
    *,
    human_actor: str,
    expected_operation: DeploymentOperation,
    phase: DeploymentPhase,
    rollout_percent: int,
    idempotency_key: str,
) -> None:
    if candidate.status is not ReleaseCandidateStatus.APPROVED:
        raise DeploymentError("CANDIDATE_NOT_APPROVED")
    if not isinstance(control, ReleaseControlEvent):
        raise DeploymentError("RELEASE_CONTROL_REQUIRED")
    expected_kind = "APPROVAL" if expected_operation is DeploymentOperation.APPLY else "ROLLBACK"
    if control.kind != expected_kind:
        raise DeploymentError("CONTROL_OPERATION_MISMATCH")
    if (
        control.candidate_id != candidate.candidate_id
        or control.environment != candidate.environment
    ):
        raise DeploymentError("CONTROL_CANDIDATE_MISMATCH")
    if control.decision_id != candidate.decision_id:
        raise DeploymentError("CONTROL_DECISION_MISMATCH")
    if not isinstance(human_actor, str) or not human_actor.strip():
        raise DeploymentError("HUMAN_ACTOR_REQUIRED")
    if human_actor.startswith("ai:") or human_actor != control.actor_id:
        raise DeploymentError("HUMAN_ACTOR_MISMATCH")
    if not control.signature_ref:
        raise DeploymentError("CONTROL_SIGNATURE_REQUIRED")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise DeploymentError("IDEMPOTENCY_KEY_REQUIRED")
    if len(idempotency_key) > 256:
        raise DeploymentError("IDEMPOTENCY_KEY_TOO_LONG")
    if (
        phase is DeploymentPhase.ROLLED_BACK
        and expected_operation is not DeploymentOperation.ROLLBACK
    ):
        raise DeploymentError("INVALID_APPLY_PHASE")
    if (
        expected_operation is DeploymentOperation.ROLLBACK
        and phase is not DeploymentPhase.ROLLED_BACK
    ):
        raise DeploymentError("INVALID_ROLLBACK_PHASE")
    if (
        not isinstance(rollout_percent, int)
        or isinstance(rollout_percent, bool)
        or not 0 <= rollout_percent <= 100
    ):
        raise DeploymentError("ROLLOUT_PERCENT_INVALID")
    if expected_operation is DeploymentOperation.APPLY and rollout_percent == 0:
        raise DeploymentError("ROLLOUT_PERCENT_REQUIRED")


def _deployment_trace_id(candidate: ReleaseCandidate) -> str:
    """Return a stable, non-sensitive trace id for a release operation."""

    payload = f"{candidate.candidate_id}|{candidate.environment}".encode()
    return "release-" + hashlib.sha256(payload).hexdigest()[:24]


def _error_code(error: BaseException) -> str:
    """Map failures to a stable code without persisting exception text."""

    if isinstance(error, DeploymentError) and error.args:
        value = error.args[0]
        if isinstance(value, str) and value.strip():
            return value[:128]
    return f"{type(error).__name__.upper()}"


def _receipt(
    candidate: ReleaseCandidate,
    control: ReleaseControlEvent,
    *,
    operation: DeploymentOperation,
    phase: DeploymentPhase,
    rollout_percent: int,
    idempotency_key: str,
    external_ref: str,
    created_at: datetime,
) -> DeploymentReceipt:
    if not isinstance(external_ref, str) or not external_ref.strip():
        raise DeploymentError("DEPLOYMENT_EXTERNAL_REF_REQUIRED")
    payload = {
        "operation": operation.value,
        "phase": phase.value,
        "idempotency_key": idempotency_key,
        "candidate_id": candidate.candidate_id,
        "environment": candidate.environment,
        "control_id": control.control_id,
        "external_ref": external_ref,
    }
    receipt_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return DeploymentReceipt(
        receipt_id=receipt_id,
        operation=operation,
        phase=phase,
        idempotency_key=idempotency_key,
        candidate_id=candidate.candidate_id,
        environment=candidate.environment,
        control_id=control.control_id,
        actor_id=control.actor_id,
        rollout_percent=rollout_percent,
        external_ref=external_ref,
        created_at=created_at,
    )


def _validate_receipt(receipt: DeploymentReceipt) -> None:
    if not isinstance(receipt, DeploymentReceipt):
        raise DeploymentError("DEPLOYMENT_RECEIPT_REQUIRED")
    if not receipt.idempotency_key.strip() or not receipt.candidate_id.strip():
        raise DeploymentError("DEPLOYMENT_RECEIPT_IDENTITY_REQUIRED")


def _row_from_receipt(receipt: DeploymentReceipt) -> DeploymentReceiptRow:
    return DeploymentReceiptRow(
        receipt_id=receipt.receipt_id,
        operation=receipt.operation.value,
        phase=receipt.phase.value,
        idempotency_key=receipt.idempotency_key,
        candidate_id=receipt.candidate_id,
        environment=receipt.environment,
        control_id=receipt.control_id,
        actor_id=receipt.actor_id,
        rollout_percent=receipt.rollout_percent,
        external_ref=receipt.external_ref,
        created_at=receipt.created_at,
    )


def _stored(row: DeploymentReceiptRow) -> DeploymentReceipt:
    try:
        operation = DeploymentOperation(row.operation)
        phase = DeploymentPhase(row.phase)
    except ValueError as exc:
        raise DeploymentError("PERSISTED_DEPLOYMENT_ENUM_INVALID") from exc
    created_at = row.created_at
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        created_at = created_at.replace(tzinfo=UTC)
    return DeploymentReceipt(
        receipt_id=row.receipt_id,
        operation=operation,
        phase=phase,
        idempotency_key=row.idempotency_key,
        candidate_id=row.candidate_id,
        environment=row.environment,
        control_id=row.control_id,
        actor_id=row.actor_id,
        rollout_percent=row.rollout_percent,
        external_ref=row.external_ref,
        created_at=created_at,
    )


__all__ = [
    "DeploymentBase",
    "DeploymentError",
    "DeploymentOperation",
    "DeploymentPhase",
    "DeploymentPort",
    "DeploymentReceipt",
    "DeploymentReceiptRow",
    "DeploymentReceiptStore",
    "DeploymentResult",
    "InMemoryDeploymentReceiptStore",
    "ReleaseDeploymentService",
    "SqlAlchemyDeploymentReceiptStore",
]
