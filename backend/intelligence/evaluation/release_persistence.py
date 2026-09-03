"""Durable audit ledger for AI release/admission decisions.

The release gate remains a pure evaluator.  This module is the persistence
seam for its immutable result: it stores governance metadata and failure codes
only, never benchmark payloads, media, prompts, model output, or deployment
state.  Transaction ownership stays with the composition root.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import JSON, DateTime, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.evaluation.release_gate import ReleaseDecision


class ReleaseDecisionPersistenceError(ValueError):
    """Raised when an admission decision cannot be safely persisted."""


class ReleaseDecisionPersistenceBase(DeclarativeBase):
    """Metadata boundary for AI evaluation governance records."""


class ReleaseDecisionRow(ReleaseDecisionPersistenceBase):
    """Append-only AI governance ledger row."""

    __tablename__ = "ai_release_decisions"
    __table_args__ = (
        Index(
            "ix_ai_release_decisions_candidate_environment",
            "candidate_id",
            "environment",
            "evaluated_at",
        ),
        Index(
            "ix_ai_release_decisions_provider_environment",
            "provider_id",
            "environment",
            "evaluated_at",
        ),
    )

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(256), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    report_ref: Mapped[str] = mapped_column(Text, nullable=False)
    failures: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReleaseDecisionSink(Protocol):
    """Persistence port used by an offline evaluator or release service."""

    async def append(self, decision: ReleaseDecision) -> ReleaseDecision: ...


class InMemoryReleaseDecisionSink:
    """Deterministic sink for tests and local evaluation runs."""

    def __init__(self) -> None:
        self.decisions: list[ReleaseDecision] = []

    async def append(self, decision: ReleaseDecision) -> ReleaseDecision:
        _validate(decision)
        fingerprint = decision_fingerprint(decision)
        for existing in self.decisions:
            if decision_fingerprint(existing) == fingerprint:
                return existing
        self.decisions.append(decision)
        return decision


class SqlAlchemyReleaseDecisionSink:
    """SQL implementation; add/flush only, never commits the caller's UoW."""

    def __init__(
        self, session: AsyncSession, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    async def append(self, decision: ReleaseDecision) -> ReleaseDecision:
        _validate(decision)
        decision_id = decision_fingerprint(decision)
        existing = await self._session.scalar(
            select(ReleaseDecisionRow).where(ReleaseDecisionRow.decision_id == decision_id)
        )
        if existing is not None:
            return _stored(existing)

        evaluated_at = self._clock()
        if evaluated_at.tzinfo is None:
            raise ReleaseDecisionPersistenceError("clock must return timezone-aware datetime")
        row = ReleaseDecisionRow(
            decision_id=decision_id,
            status=decision.status,
            candidate_id=decision.candidate_id,
            provider_id=decision.provider_id,
            model=decision.model,
            model_version=decision.model_version,
            environment=decision.environment,
            report_ref=decision.report_ref,
            failures=list(decision.failures),
            evaluated_at=evaluated_at,
        )
        self._session.add(row)
        await self._session.flush()
        return decision

    async def list_decisions(
        self, *, candidate_id: str | None = None, environment: str | None = None
    ) -> tuple[ReleaseDecision, ...]:
        statement = select(ReleaseDecisionRow).order_by(
            ReleaseDecisionRow.evaluated_at, ReleaseDecisionRow.decision_id
        )
        if candidate_id is not None:
            statement = statement.where(ReleaseDecisionRow.candidate_id == candidate_id)
        if environment is not None:
            statement = statement.where(ReleaseDecisionRow.environment == environment)
        result = await self._session.execute(statement)
        return tuple(_stored(row) for row in result.scalars())


def decision_fingerprint(decision: ReleaseDecision) -> str:
    """Stable idempotency key over the complete decision, excluding wall-clock time."""

    _validate(decision)
    payload = {
        "status": decision.status,
        "candidate_id": decision.candidate_id,
        "provider_id": decision.provider_id,
        "model": decision.model,
        "model_version": decision.model_version,
        "environment": decision.environment,
        "report_ref": decision.report_ref,
        "failures": list(decision.failures),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate(decision: ReleaseDecision) -> None:
    if not isinstance(decision, ReleaseDecision):
        raise ReleaseDecisionPersistenceError("RELEASE_DECISION_REQUIRED")
    for name in (
        "candidate_id",
        "provider_id",
        "model",
        "model_version",
        "environment",
        "report_ref",
    ):
        value = getattr(decision, name)
        if not isinstance(value, str) or not value.strip():
            raise ReleaseDecisionPersistenceError(f"{name.upper()}_REQUIRED")
    if decision.status not in {"ADMITTED", "BLOCKED"}:
        raise ReleaseDecisionPersistenceError("INVALID_RELEASE_STATUS")
    if not isinstance(decision.failures, tuple) or any(
        not isinstance(item, str) or not item.strip() for item in decision.failures
    ):
        raise ReleaseDecisionPersistenceError("INVALID_RELEASE_FAILURES")


def _stored(row: ReleaseDecisionRow) -> ReleaseDecision:
    failures = row.failures or []
    if not isinstance(failures, (list, tuple)) or any(
        not isinstance(item, str) for item in failures
    ):
        raise ReleaseDecisionPersistenceError("PERSISTED_FAILURES_INVALID")
    return ReleaseDecision(
        status=row.status,  # type: ignore[arg-type]
        candidate_id=row.candidate_id,
        provider_id=row.provider_id,
        model=row.model,
        model_version=row.model_version,
        environment=row.environment,
        report_ref=row.report_ref,
        failures=tuple(failures),
    )


__all__ = [
    "InMemoryReleaseDecisionSink",
    "ReleaseDecisionPersistenceError",
    "ReleaseDecisionPersistenceBase",
    "ReleaseDecisionRow",
    "ReleaseDecisionSink",
    "SqlAlchemyReleaseDecisionSink",
    "decision_fingerprint",
]
