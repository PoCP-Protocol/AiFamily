"""Durable operator alerts for family-experience canary supervision."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy import CheckConstraint, DateTime, Index, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.evaluation.deployment import DeploymentReceipt
from backend.intelligence.evaluation.release_catalog import ReleaseCandidate

from .canary_supervision import (
    CanaryAssessment,
    CanaryHealth,
    CanaryRollbackBlockedError,
    CanarySupervisionError,
    CanarySupervisionResult,
    FamilyExperienceCanarySupervisor,
)


class CanaryAlertKind(StrEnum):
    ROLLBACK_EXECUTED = "ROLLBACK_EXECUTED"
    ROLLBACK_BLOCKED = "ROLLBACK_BLOCKED"


class CanaryAlertStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class CanaryAlertBase(DeclarativeBase):
    """Metadata-only operator alert persistence boundary."""


class CanaryAlertRow(CanaryAlertBase):
    __tablename__ = "ai_family_experience_canary_alerts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('ROLLBACK_EXECUTED', 'ROLLBACK_BLOCKED')",
            name="ck_ai_family_experience_canary_alert_kind",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED')",
            name="ck_ai_family_experience_canary_alert_status",
        ),
        Index(
            "ix_ai_family_experience_canary_alerts_environment_status",
            "environment",
            "status",
            "opened_at",
        ),
        Index("uq_ai_family_experience_canary_alert_assessment", "assessment_id", unique=True),
    )

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(256), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    rollback_receipt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@dataclass(frozen=True, slots=True)
class CanaryAlert:
    alert_id: str
    assessment_id: str
    candidate_id: str
    environment: str
    kind: CanaryAlertKind
    status: CanaryAlertStatus
    rollback_receipt_id: str | None
    error_code: str | None
    opened_at: datetime
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None

    def __post_init__(self) -> None:
        _validate_alert(self)


class CanaryAlertStore(Protocol):
    async def append(self, alert: CanaryAlert) -> CanaryAlert: ...

    async def get(self, alert_id: str) -> CanaryAlert | None: ...

    async def acknowledge(
        self, alert_id: str, *, actor_id: str, acknowledged_at: datetime
    ) -> CanaryAlert: ...

    async def list_open(
        self, *, environment: str, limit: int = 100
    ) -> tuple[CanaryAlert, ...]: ...


class InMemoryCanaryAlertStore:
    def __init__(self) -> None:
        self._alerts: dict[str, CanaryAlert] = {}
        self._by_assessment: dict[str, CanaryAlert] = {}

    async def append(self, alert: CanaryAlert) -> CanaryAlert:
        existing = self._alerts.get(alert.alert_id)
        bound = self._by_assessment.get(alert.assessment_id)
        for stored in (existing, bound):
            if stored is not None and stored != alert:
                raise CanarySupervisionError("CANARY_ALERT_CONFLICT")
        stored = existing or bound or alert
        self._alerts[stored.alert_id] = stored
        self._by_assessment[stored.assessment_id] = stored
        return stored

    async def get(self, alert_id: str) -> CanaryAlert | None:
        return self._alerts.get(alert_id)

    async def acknowledge(
        self, alert_id: str, *, actor_id: str, acknowledged_at: datetime
    ) -> CanaryAlert:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise CanarySupervisionError("CANARY_ALERT_NOT_FOUND")
        updated = _acknowledged(alert, actor_id=actor_id, acknowledged_at=acknowledged_at)
        self._alerts[alert_id] = updated
        self._by_assessment[updated.assessment_id] = updated
        return updated

    async def list_open(
        self, *, environment: str, limit: int = 100
    ) -> tuple[CanaryAlert, ...]:
        _validate_list_request(environment, limit)
        alerts = sorted(self._alerts.values(), key=lambda alert: (alert.opened_at, alert.alert_id))
        return tuple(
            alert
            for alert in alerts
            if alert.environment == environment and alert.status is CanaryAlertStatus.OPEN
        )[:limit]


class SqlAlchemyCanaryAlertStore:
    """SQL alert ledger; caller owns the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, alert: CanaryAlert) -> CanaryAlert:
        row = await self._session.scalar(
            select(CanaryAlertRow).where(
                (CanaryAlertRow.alert_id == alert.alert_id)
                | (CanaryAlertRow.assessment_id == alert.assessment_id)
            )
        )
        if row is not None:
            existing = _stored(row)
            if existing != alert:
                raise CanarySupervisionError("CANARY_ALERT_CONFLICT")
            return existing
        self._session.add(_row(alert))
        await self._session.flush()
        return alert

    async def get(self, alert_id: str) -> CanaryAlert | None:
        row = await self._session.scalar(
            select(CanaryAlertRow).where(CanaryAlertRow.alert_id == alert_id)
        )
        return None if row is None else _stored(row)

    async def acknowledge(
        self, alert_id: str, *, actor_id: str, acknowledged_at: datetime
    ) -> CanaryAlert:
        row = await self._session.scalar(
            select(CanaryAlertRow)
            .where(CanaryAlertRow.alert_id == alert_id)
            .with_for_update()
        )
        if row is None:
            raise CanarySupervisionError("CANARY_ALERT_NOT_FOUND")
        current = _stored(row)
        updated = _acknowledged(
            current,
            actor_id=actor_id,
            acknowledged_at=acknowledged_at,
        )
        row.status = updated.status.value
        row.acknowledged_by = updated.acknowledged_by
        row.acknowledged_at = updated.acknowledged_at
        await self._session.flush()
        return updated

    async def list_open(
        self, *, environment: str, limit: int = 100
    ) -> tuple[CanaryAlert, ...]:
        _validate_list_request(environment, limit)
        result = await self._session.execute(
            select(CanaryAlertRow)
            .where(
                CanaryAlertRow.environment == environment,
                CanaryAlertRow.status == CanaryAlertStatus.OPEN.value,
            )
            .order_by(CanaryAlertRow.opened_at, CanaryAlertRow.alert_id)
            .limit(limit)
        )
        return tuple(_stored(row) for row in result.scalars())


class SessionPerCallCanaryAlertStore:
    """Transaction-per-call alert store for long-lived schedulers."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def append(self, alert: CanaryAlert) -> CanaryAlert:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyCanaryAlertStore(session).append(alert)

    async def get(self, alert_id: str) -> CanaryAlert | None:
        async with self._session_factory() as session:
            return await SqlAlchemyCanaryAlertStore(session).get(alert_id)

    async def acknowledge(
        self, alert_id: str, *, actor_id: str, acknowledged_at: datetime
    ) -> CanaryAlert:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyCanaryAlertStore(session).acknowledge(
                alert_id,
                actor_id=actor_id,
                acknowledged_at=acknowledged_at,
            )

    async def list_open(
        self, *, environment: str, limit: int = 100
    ) -> tuple[CanaryAlert, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyCanaryAlertStore(session).list_open(
                environment=environment,
                limit=limit,
            )


@dataclass(frozen=True, slots=True)
class CanaryAlertingSupervisor:
    """Persist operator alerts without changing rollback authorization semantics."""

    supervisor: FamilyExperienceCanarySupervisor
    alerts: CanaryAlertStore
    clock: Callable[[], datetime] | None = None

    async def supervise(
        self,
        candidate: ReleaseCandidate,
        canary_receipt: DeploymentReceipt,
        *,
        rollback_control_id: str | None,
        idempotency_key: str,
    ) -> CanarySupervisionResult:
        try:
            result = await self.supervisor.supervise(
                candidate,
                canary_receipt,
                rollback_control_id=rollback_control_id,
                idempotency_key=idempotency_key,
            )
        except CanaryRollbackBlockedError as error:
            await self.alerts.append(
                build_canary_alert(
                    error.assessment,
                    rollback_receipt_id=None,
                    error_code=error.code,
                    opened_at=self._now(),
                )
            )
            raise
        if result.assessment.health is CanaryHealth.BREACHED:
            if result.rollback_receipt is None:
                raise CanarySupervisionError("CANARY_BREACH_OUTCOME_INVALID")
            await self.alerts.append(
                build_canary_alert(
                    result.assessment,
                    rollback_receipt_id=result.rollback_receipt.receipt_id,
                    error_code=None,
                    opened_at=self._now(),
                )
            )
        return result

    def _now(self) -> datetime:
        value = self.clock() if self.clock is not None else datetime.now(UTC)
        return _aware(value)


def build_canary_alert(
    assessment: CanaryAssessment,
    *,
    rollback_receipt_id: str | None,
    error_code: str | None,
    opened_at: datetime,
) -> CanaryAlert:
    if assessment.health is not CanaryHealth.BREACHED:
        raise CanarySupervisionError("CANARY_ALERT_REQUIRES_BREACH")
    kind = (
        CanaryAlertKind.ROLLBACK_EXECUTED
        if rollback_receipt_id is not None
        else CanaryAlertKind.ROLLBACK_BLOCKED
    )
    if kind is CanaryAlertKind.ROLLBACK_EXECUTED and error_code is not None:
        raise CanarySupervisionError("CANARY_ALERT_OUTCOME_CONFLICT")
    if kind is CanaryAlertKind.ROLLBACK_BLOCKED and not error_code:
        raise CanarySupervisionError("CANARY_ALERT_ERROR_REQUIRED")
    payload = {
        "assessment_id": assessment.assessment_id,
        "candidate_id": assessment.candidate_id,
        "environment": assessment.environment,
        "kind": kind.value,
        "rollback_receipt_id": rollback_receipt_id,
        "error_code": error_code,
    }
    return CanaryAlert(
        alert_id=hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        assessment_id=assessment.assessment_id,
        candidate_id=assessment.candidate_id,
        environment=assessment.environment,
        kind=kind,
        status=CanaryAlertStatus.OPEN,
        rollback_receipt_id=rollback_receipt_id,
        error_code=error_code,
        opened_at=_aware(opened_at),
    )


def _acknowledged(
    alert: CanaryAlert, *, actor_id: str, acknowledged_at: datetime
) -> CanaryAlert:
    if not isinstance(actor_id, str) or not actor_id.strip() or actor_id.startswith("ai:"):
        raise CanarySupervisionError("CANARY_ALERT_HUMAN_ACTOR_REQUIRED")
    acknowledged_at = _aware(acknowledged_at)
    if acknowledged_at < alert.opened_at:
        raise CanarySupervisionError("CANARY_ALERT_ACK_PRECEDES_OPEN")
    if alert.status is CanaryAlertStatus.ACKNOWLEDGED:
        if alert.acknowledged_by != actor_id:
            raise CanarySupervisionError("CANARY_ALERT_ALREADY_ACKNOWLEDGED")
        return alert
    return replace(
        alert,
        status=CanaryAlertStatus.ACKNOWLEDGED,
        acknowledged_by=actor_id,
        acknowledged_at=acknowledged_at,
    )


def _validate_alert(alert: CanaryAlert) -> None:
    required = (alert.alert_id, alert.assessment_id, alert.candidate_id, alert.environment)
    if not all(isinstance(value, str) and value.strip() for value in required):
        raise CanarySupervisionError("CANARY_ALERT_IDENTITY_REQUIRED")
    _aware(alert.opened_at)
    if alert.kind is CanaryAlertKind.ROLLBACK_EXECUTED:
        if not alert.rollback_receipt_id or alert.error_code is not None:
            raise CanarySupervisionError("CANARY_ALERT_OUTCOME_INVALID")
    elif alert.kind is CanaryAlertKind.ROLLBACK_BLOCKED:
        if alert.rollback_receipt_id is not None or not alert.error_code:
            raise CanarySupervisionError("CANARY_ALERT_OUTCOME_INVALID")
    else:
        raise CanarySupervisionError("CANARY_ALERT_KIND_INVALID")
    if alert.status is CanaryAlertStatus.OPEN:
        if alert.acknowledged_by is not None or alert.acknowledged_at is not None:
            raise CanarySupervisionError("CANARY_ALERT_OPEN_ACK_INVALID")
    elif alert.status is CanaryAlertStatus.ACKNOWLEDGED:
        if not alert.acknowledged_by or alert.acknowledged_at is None:
            raise CanarySupervisionError("CANARY_ALERT_ACK_REQUIRED")
        if alert.acknowledged_by.startswith("ai:"):
            raise CanarySupervisionError("CANARY_ALERT_HUMAN_ACTOR_REQUIRED")
        _aware(alert.acknowledged_at)
    else:
        raise CanarySupervisionError("CANARY_ALERT_STATUS_INVALID")


def _row(alert: CanaryAlert) -> CanaryAlertRow:
    return CanaryAlertRow(
        alert_id=alert.alert_id,
        assessment_id=alert.assessment_id,
        candidate_id=alert.candidate_id,
        environment=alert.environment,
        kind=alert.kind.value,
        status=alert.status.value,
        rollback_receipt_id=alert.rollback_receipt_id,
        error_code=alert.error_code,
        opened_at=alert.opened_at,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at,
    )


def _stored(row: CanaryAlertRow) -> CanaryAlert:
    try:
        kind = CanaryAlertKind(row.kind)
        status = CanaryAlertStatus(row.status)
    except ValueError as exc:
        raise CanarySupervisionError("PERSISTED_CANARY_ALERT_ENUM_INVALID") from exc
    return CanaryAlert(
        alert_id=row.alert_id,
        assessment_id=row.assessment_id,
        candidate_id=row.candidate_id,
        environment=row.environment,
        kind=kind,
        status=status,
        rollback_receipt_id=row.rollback_receipt_id,
        error_code=row.error_code,
        opened_at=_database_aware(row.opened_at),
        acknowledged_by=row.acknowledged_by,
        acknowledged_at=(
            None if row.acknowledged_at is None else _database_aware(row.acknowledged_at)
        ),
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanarySupervisionError("CANARY_ALERT_TIME_MUST_BE_AWARE")
    return value


def _validate_list_request(environment: str, limit: int) -> None:
    if not isinstance(environment, str) or not environment.strip():
        raise CanarySupervisionError("CANARY_ALERT_ENVIRONMENT_REQUIRED")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 0 <= limit <= 1000:
        raise CanarySupervisionError("CANARY_ALERT_LIMIT_INVALID")


def _database_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


__all__ = [
    "CanaryAlert",
    "CanaryAlertBase",
    "CanaryAlertKind",
    "CanaryAlertRow",
    "CanaryAlertStore",
    "CanaryAlertStatus",
    "CanaryAlertingSupervisor",
    "InMemoryCanaryAlertStore",
    "SessionPerCallCanaryAlertStore",
    "SqlAlchemyCanaryAlertStore",
    "build_canary_alert",
]
