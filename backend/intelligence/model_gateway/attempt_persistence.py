"""Durable SQL AttemptSink for the Model Gateway.

The gateway accepts both synchronous in-memory sinks and awaitable sinks.  This
adapter is the durable implementation: it records STARTED before the provider
call and closes that row with the observed outcome.  Session ownership and
transaction commit remain with the composition root; the sink only flushes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.model_gateway.attempts import AttemptOutcome


class AttemptPersistenceBase(DeclarativeBase):
    """Metadata boundary for AI-runtime-owned attempt tables."""


class ModelAttemptRow(AttemptPersistenceBase):
    __tablename__ = "ai_model_attempts"

    attempt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    use_case: Mapped[str] = mapped_column(String(128), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    route_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(256))
    session_id: Mapped[str | None] = mapped_column(String(256))
    tenant_id: Mapped[str | None] = mapped_column(String(128), index=True)
    family_id: Mapped[str | None] = mapped_column(String(128), index=True)
    release_set_id: Mapped[str | None] = mapped_column(String(64), index=True)
    bundle_id: Mapped[str | None] = mapped_column(String(64))
    deployment_receipt_id: Mapped[str | None] = mapped_column(String(64))
    deployment_sequence: Mapped[int | None] = mapped_column(Integer)
    runtime_config_digest: Mapped[str | None] = mapped_column(String(64))
    control_id: Mapped[str | None] = mapped_column(String(128))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    failure_kind: Mapped[str | None] = mapped_column(String(128))
    model: Mapped[str | None] = mapped_column(String(256))
    model_version: Mapped[str | None] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)


class SqlAlchemyAttemptSink:
    """Async durable implementation of the Gateway's AttemptSink protocol."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)

    async def begin(
        self,
        *,
        provider_id: str,
        use_case: str,
        data_class: str,
        environment: str,
        route_sequence: int,
        request_id: str | None,
        session_id: str | None,
        tenant_id: str | None = None,
        family_id: str | None = None,
        release_set_id: str | None = None,
        bundle_id: str | None = None,
        deployment_receipt_id: str | None = None,
        deployment_sequence: int | None = None,
        runtime_config_digest: str | None = None,
        control_id: str | None = None,
    ) -> str:
        attempt_id = f"attempt:{uuid4().hex}"
        started_at = self._clock()
        if started_at.tzinfo is None:
            raise ValueError("attempt clock must be timezone-aware")
        self._session.add(
            ModelAttemptRow(
                attempt_id=attempt_id,
                provider_id=provider_id,
                use_case=use_case,
                data_class=data_class,
                environment=environment,
                route_sequence=route_sequence,
                status="STARTED",
                started_at=started_at,
                request_id=request_id,
                session_id=session_id,
                tenant_id=tenant_id,
                family_id=family_id,
                release_set_id=release_set_id,
                bundle_id=bundle_id,
                deployment_receipt_id=deployment_receipt_id,
                deployment_sequence=deployment_sequence,
                runtime_config_digest=runtime_config_digest,
                control_id=control_id,
            )
        )
        await self._session.flush()
        return attempt_id

    async def finish(self, attempt_id: str | None, outcome: AttemptOutcome) -> None:
        if attempt_id is None:
            return
        row = await self._session.scalar(
            select(ModelAttemptRow).where(ModelAttemptRow.attempt_id == attempt_id)
        )
        if row is None:
            return
        if outcome.status not in {"STARTED", "SUCCESS", "FAILURE"}:
            raise ValueError("invalid attempt status")
        row.status = outcome.status
        row.finished_at = self._clock()
        row.latency_ms = outcome.latency_ms
        row.failure_kind = outcome.failure_kind
        row.model = outcome.model
        row.model_version = outcome.model_version
        usage = outcome.token_usage
        row.prompt_tokens = usage.prompt_tokens if usage is not None else None
        row.completion_tokens = usage.completion_tokens if usage is not None else None
        row.total_tokens = usage.total_tokens if usage is not None else None
        await self._session.flush()

    async def list_attempts(
        self,
        *,
        provider_id: str | None = None,
        request_id: str | None = None,
    ) -> tuple[ModelAttemptRow, ...]:
        statement = select(ModelAttemptRow).order_by(ModelAttemptRow.started_at)
        if provider_id is not None:
            statement = statement.where(ModelAttemptRow.provider_id == provider_id)
        if request_id is not None:
            statement = statement.where(ModelAttemptRow.request_id == request_id)
        return tuple((await self._session.scalars(statement)).all())


class SessionPerCallAttemptSink:
    """Commit attempt transitions independently from the business UoW."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def begin(
        self,
        *,
        provider_id: str,
        use_case: str,
        data_class: str,
        environment: str,
        route_sequence: int,
        request_id: str | None,
        session_id: str | None,
        tenant_id: str | None = None,
        family_id: str | None = None,
        release_set_id: str | None = None,
        bundle_id: str | None = None,
        deployment_receipt_id: str | None = None,
        deployment_sequence: int | None = None,
        runtime_config_digest: str | None = None,
        control_id: str | None = None,
    ) -> str:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyAttemptSink(session, clock=self._clock).begin(
                provider_id=provider_id,
                use_case=use_case,
                data_class=data_class,
                environment=environment,
                route_sequence=route_sequence,
                request_id=request_id,
                session_id=session_id,
                tenant_id=tenant_id,
                family_id=family_id,
                release_set_id=release_set_id,
                bundle_id=bundle_id,
                deployment_receipt_id=deployment_receipt_id,
                deployment_sequence=deployment_sequence,
                runtime_config_digest=runtime_config_digest,
                control_id=control_id,
            )

    async def finish(self, attempt_id: str | None, outcome: AttemptOutcome) -> None:
        async with self._session_factory() as session, session.begin():
            await SqlAlchemyAttemptSink(session, clock=self._clock).finish(
                attempt_id,
                outcome,
            )


__all__ = [
    "AttemptPersistenceBase",
    "ModelAttemptRow",
    "SessionPerCallAttemptSink",
    "SqlAlchemyAttemptSink",
]
