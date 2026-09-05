"""Durable persistence seam for provider-neutral Safety decisions.

Only policy metadata is persisted: no raw family payload, prompt or model
output is copied into the safety ledger.  Session ownership and transaction
commit remain with the application composition root.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.safety.runtime import SafetyContext, SafetyDecision


class SafetyDecisionPersistenceBase(DeclarativeBase):
    """Metadata boundary for AI-runtime-owned safety decision records."""


class SafetyDecisionRow(SafetyDecisionPersistenceBase):
    __tablename__ = "ai_safety_decisions"

    decision_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(256))
    session_id: Mapped[str | None] = mapped_column(String(256))
    tenant_id: Mapped[str | None] = mapped_column(String(128), index=True)
    family_id: Mapped[str | None] = mapped_column(String(128), index=True)
    use_case: Mapped[str] = mapped_column(String(128), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_is_minor: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    requires_human_gate: Mapped[bool] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SafetyDecisionSink(Protocol):
    """A sink that records policy metadata without receiving raw payloads."""

    def record(
        self,
        *,
        stage: str,
        context: SafetyContext,
        decision: SafetyDecision,
        request_id: str | None,
        session_id: str | None,
    ) -> None | Awaitable[None]:
        ...


class InMemorySafetyDecisionSink:
    """Queryable process-local sink for deterministic tests."""

    def __init__(self) -> None:
        self.decisions: list[dict[str, object]] = []

    def record(
        self,
        *,
        stage: str,
        context: SafetyContext,
        decision: SafetyDecision,
        request_id: str | None,
        session_id: str | None,
    ) -> None:
        if stage not in {"input", "output"}:
            raise ValueError("safety decision stage must be input or output")
        self.decisions.append(
            {
                "stage": stage,
                "use_case": context.use_case,
                "data_class": context.data_class,
                "subject_is_minor": context.subject_is_minor,
                "status": decision.status,
                "risk_level": decision.risk_level,
                "reasons": decision.reasons,
                "requires_human_gate": decision.requires_human_gate,
                "request_id": request_id,
                "session_id": session_id,
                "tenant_id": context.tenant_id,
                "family_id": context.family_id,
            }
        )


class SqlAlchemySafetyDecisionSink:
    """Async durable implementation; flushes but never commits."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)

    async def record(
        self,
        *,
        stage: str,
        context: SafetyContext,
        decision: SafetyDecision,
        request_id: str | None,
        session_id: str | None,
    ) -> None:
        if stage not in {"input", "output"}:
            raise ValueError("safety decision stage must be input or output")
        occurred_at = self._clock()
        if occurred_at.tzinfo is None:
            raise ValueError("safety decision clock must be timezone-aware")
        self._session.add(
            SafetyDecisionRow(
                decision_id=f"safety:{uuid4().hex}",
                stage=stage,
                request_id=request_id,
                session_id=session_id,
                tenant_id=context.tenant_id,
                family_id=context.family_id,
                use_case=context.use_case,
                data_class=context.data_class,
                subject_is_minor=context.subject_is_minor,
                status=decision.status,
                risk_level=decision.risk_level,
                reasons=list(decision.reasons),
                requires_human_gate=decision.requires_human_gate,
                occurred_at=occurred_at,
            )
        )
        await self._session.flush()

    async def list_decisions(
        self,
        *,
        request_id: str | None = None,
        stage: str | None = None,
    ) -> tuple[SafetyDecisionRow, ...]:
        statement = select(SafetyDecisionRow).order_by(SafetyDecisionRow.occurred_at)
        if request_id is not None:
            statement = statement.where(SafetyDecisionRow.request_id == request_id)
        if stage is not None:
            statement = statement.where(SafetyDecisionRow.stage == stage)
        return tuple((await self._session.scalars(statement)).all())


class SessionPerCallSafetyDecisionSink:
    """Persist each safety decision in an independent short transaction."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def record(
        self,
        *,
        stage: str,
        context: SafetyContext,
        decision: SafetyDecision,
        request_id: str | None,
        session_id: str | None,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await SqlAlchemySafetyDecisionSink(session, clock=self._clock).record(
                stage=stage,
                context=context,
                decision=decision,
                request_id=request_id,
                session_id=session_id,
            )


__all__ = [
    "InMemorySafetyDecisionSink",
    "SafetyDecisionPersistenceBase",
    "SafetyDecisionRow",
    "SafetyDecisionSink",
    "SessionPerCallSafetyDecisionSink",
    "SqlAlchemySafetyDecisionSink",
]
