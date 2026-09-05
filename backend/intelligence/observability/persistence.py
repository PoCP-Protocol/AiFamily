"""In-memory and SQL sinks for metadata-only AI telemetry spans."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .contracts import (
    AttributeValue,
    SpanStatus,
    TelemetryContext,
    TelemetrySpanHandle,
    new_span_handle,
    validate_attributes,
)


class TelemetryPersistenceBase(DeclarativeBase):
    """Metadata boundary for AI-runtime-owned telemetry records."""


class TelemetrySpanRow(TelemetryPersistenceBase):
    __tablename__ = "ai_telemetry_spans"
    __table_args__ = (
        UniqueConstraint(
            "trace_id",
            "operation_id",
            "name",
            name="uq_ai_telemetry_trace_operation_name",
        ),
        Index("ix_ai_telemetry_trace_sequence", "trace_id", "started_at"),
        Index(
            "ix_ai_telemetry_scope_started",
            "tenant_id",
            "family_id",
            "started_at",
        ),
    )

    span_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(256))
    session_id: Mapped[str | None] = mapped_column(String(256))
    tenant_id: Mapped[str | None] = mapped_column(String(128))
    family_id: Mapped[str | None] = mapped_column(String(128))
    use_case: Mapped[str] = mapped_column(String(128), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(256))
    causation_id: Mapped[str | None] = mapped_column(String(256))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class InMemoryTelemetrySink:
    """Test sink that exposes the same lifecycle as the durable adapter."""

    def __init__(self) -> None:
        self.spans: list[dict[str, Any]] = []
        self._handles: dict[tuple[str, str, str], TelemetrySpanHandle] = {}

    async def start_span(
        self,
        *,
        name: str,
        context: TelemetryContext,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> TelemetrySpanHandle:
        clean = validate_attributes(attributes or {})
        key = (context.trace_id, context.operation_id or context.trace_id, name)
        existing = self._handles.get(key)
        if existing is not None:
            current = next(span for span in self.spans if span["span_id"] == existing.span_id)
            if current["attributes"] != clean or not _same_context(current, context):
                raise ValueError("TELEMETRY_IDEMPOTENCY_CONFLICT")
            return existing
        handle = new_span_handle(name=name, context=context)
        self._handles[key] = handle
        self.spans.append(_record(handle, status="IN_PROGRESS", attributes=clean))
        return handle

    async def finish_span(
        self,
        handle: TelemetrySpanHandle,
        *,
        status: SpanStatus,
        ended_at: datetime | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        error_code: str | None = None,
    ) -> None:
        clean = validate_attributes(attributes or {})
        if status not in {"OK", "ERROR"}:
            raise ValueError("TELEMETRY_FINAL_STATUS_REQUIRED")
        ended = ended_at or datetime.now(UTC)
        if ended.tzinfo is None:
            raise ValueError("TELEMETRY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        for span in self.spans:
            if span["span_id"] == handle.span_id:
                if span["status"] != "IN_PROGRESS":
                    if span["status"] != status or span["error_code"] != error_code:
                        raise ValueError("TELEMETRY_IDEMPOTENCY_CONFLICT")
                    if any(span["attributes"].get(key) != value for key, value in clean.items()):
                        raise ValueError("TELEMETRY_IDEMPOTENCY_CONFLICT")
                    return
                span.update(
                    status=status,
                    attributes={**span["attributes"], **clean},
                    error_code=error_code,
                    ended_at=ended,
                    duration_ms=max(0, int((ended - handle.started_at).total_seconds() * 1000)),
                )
                return
        raise ValueError("TELEMETRY_SPAN_NOT_FOUND")


class SqlAlchemyTelemetrySink:
    """Async SQL sink; flushes only and never commits the caller's UoW."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start_span(
        self,
        *,
        name: str,
        context: TelemetryContext,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> TelemetrySpanHandle:
        clean = validate_attributes(attributes or {})
        operation_id = context.operation_id or context.trace_id
        existing = await self._session.scalar(
            select(TelemetrySpanRow).where(
                TelemetrySpanRow.trace_id == context.trace_id,
                TelemetrySpanRow.operation_id == operation_id,
                TelemetrySpanRow.name == name,
            )
        )
        if existing is not None:
            if existing.attributes != clean or not _same_row_context(existing, context):
                raise ValueError("TELEMETRY_IDEMPOTENCY_CONFLICT")
            return TelemetrySpanHandle(
                span_id=existing.span_id,
                name=existing.name,
                context=context,
                started_at=_aware(existing.started_at),
            )
        handle = new_span_handle(name=name, context=context)
        self._session.add(
            TelemetrySpanRow(
                span_id=handle.span_id,
                trace_id=context.trace_id,
                operation_id=operation_id,
                parent_span_id=context.parent_span_id,
                name=name,
                status="IN_PROGRESS",
                request_id=context.request_id,
                session_id=context.session_id,
                tenant_id=context.tenant_id,
                family_id=context.family_id,
                use_case=context.use_case,
                data_class=context.data_class,
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                attributes=clean,
                started_at=handle.started_at,
            )
        )
        await self._session.flush()
        return handle

    async def finish_span(
        self,
        handle: TelemetrySpanHandle,
        *,
        status: SpanStatus,
        ended_at: datetime | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        error_code: str | None = None,
    ) -> None:
        clean = validate_attributes(attributes or {})
        if status not in {"OK", "ERROR"}:
            raise ValueError("TELEMETRY_FINAL_STATUS_REQUIRED")
        ended = ended_at or datetime.now(UTC)
        if ended.tzinfo is None:
            raise ValueError("TELEMETRY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        row = await self._session.scalar(
            select(TelemetrySpanRow).where(TelemetrySpanRow.span_id == handle.span_id)
        )
        if row is None:
            raise ValueError("TELEMETRY_SPAN_NOT_FOUND")
        if row.status != "IN_PROGRESS":
            if row.status != status or row.error_code != error_code:
                raise ValueError("TELEMETRY_IDEMPOTENCY_CONFLICT")
            if any(row.attributes.get(key) != value for key, value in clean.items()):
                raise ValueError("TELEMETRY_IDEMPOTENCY_CONFLICT")
            return
        row.status = status
        row.attributes = {**row.attributes, **clean}
        row.error_code = error_code
        row.ended_at = ended
        row.duration_ms = max(0, int((ended - handle.started_at).total_seconds() * 1000))
        await self._session.flush()

    async def list_spans(self, *, trace_id: str) -> tuple[TelemetrySpanRow, ...]:
        result = await self._session.execute(
            select(TelemetrySpanRow)
            .where(TelemetrySpanRow.trace_id == trace_id)
            .order_by(TelemetrySpanRow.started_at, TelemetrySpanRow.span_id)
        )
        return tuple(result.scalars())


class SessionPerCallTelemetrySink:
    """Commit span lifecycle transitions outside the business transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def start_span(
        self,
        *,
        name: str,
        context: TelemetryContext,
        attributes: Mapping[str, AttributeValue] | None = None,
    ) -> TelemetrySpanHandle:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyTelemetrySink(session).start_span(
                name=name,
                context=context,
                attributes=attributes,
            )

    async def finish_span(
        self,
        handle: TelemetrySpanHandle,
        *,
        status: SpanStatus,
        ended_at: datetime | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        error_code: str | None = None,
    ) -> None:
        async with self._session_factory() as session, session.begin():
            await SqlAlchemyTelemetrySink(session).finish_span(
                handle,
                status=status,
                ended_at=ended_at,
                attributes=attributes,
                error_code=error_code,
            )


def _record(
    handle: TelemetrySpanHandle,
    *,
    status: SpanStatus,
    attributes: dict[str, AttributeValue],
) -> dict[str, Any]:
    context = handle.context
    return {
        "span_id": handle.span_id,
        "trace_id": context.trace_id,
        "operation_id": context.operation_id or context.trace_id,
        "parent_span_id": context.parent_span_id,
        "name": handle.name,
        "status": status,
        "request_id": context.request_id,
        "session_id": context.session_id,
        "tenant_id": context.tenant_id,
        "family_id": context.family_id,
        "use_case": context.use_case,
        "data_class": context.data_class,
        "correlation_id": context.correlation_id,
        "causation_id": context.causation_id,
        "attributes": attributes,
        "error_code": None,
        "started_at": handle.started_at,
        "ended_at": None,
        "duration_ms": None,
    }


def _same_context(record: Mapping[str, Any], context: TelemetryContext) -> bool:
    """Ensure an idempotent replay cannot relabel an existing span's scope."""

    same = all(
        record.get(name) == getattr(context, name)
        for name in (
            "trace_id",
            "parent_span_id",
            "request_id",
            "session_id",
            "tenant_id",
            "family_id",
            "use_case",
            "data_class",
            "correlation_id",
            "causation_id",
        )
    )
    return same and record.get("operation_id") == (context.operation_id or context.trace_id)


def _same_row_context(row: TelemetrySpanRow, context: TelemetryContext) -> bool:
    same = all(
        getattr(row, name) == getattr(context, name)
        for name in (
            "trace_id",
            "parent_span_id",
            "request_id",
            "session_id",
            "tenant_id",
            "family_id",
            "use_case",
            "data_class",
            "correlation_id",
            "causation_id",
        )
    )
    return same and row.operation_id == (context.operation_id or context.trace_id)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "InMemoryTelemetrySink",
    "SessionPerCallTelemetrySink",
    "SqlAlchemyTelemetrySink",
    "TelemetryPersistenceBase",
    "TelemetrySpanRow",
]
