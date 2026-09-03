"""Durable persistence seam for governed AgentRun executions and traces.

The adapter stores runtime metadata only.  It never calls a model provider and
never writes a Family/Growth fact.  ``AsyncSession`` ownership remains with the
composition root: every method flushes but does not commit, so a run and an
outbox record can be committed atomically by the caller.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.agent_runtime.contracts import AgentRun, AgentTask
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft, TokenUsage


class AgentRunPersistenceBase(DeclarativeBase):
    """Metadata boundary for AI-runtime-owned tables."""


class AgentRunRow(AgentRunPersistenceBase):
    __tablename__ = "ai_agent_runs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "family_id",
            "idempotency_key",
            name="uq_ai_agent_run_scope_idempotency",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(256), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    use_case: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    idempotency_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="STARTED")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(128))
    draft_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AgentTraceRow(AgentRunPersistenceBase):
    __tablename__ = "ai_agent_traces"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "idempotency_key",
            name="uq_ai_agent_trace_idempotency",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentRunStatus(StrEnum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class AgentRunPersistenceError(ValueError):
    """Base error raised by the durable AgentRun adapter."""


class AgentRunNotFound(AgentRunPersistenceError):
    """The run does not exist in the requested tenant/family scope."""


class AgentRunConflict(AgentRunPersistenceError):
    """A retry reused an idempotency key with a different operation body."""


@dataclass(frozen=True, slots=True)
class AgentRunScope:
    tenant_id: str
    family_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.family_id:
            raise AgentRunPersistenceError("AGENT_RUN_SCOPE_REQUIRED")


@dataclass(frozen=True, slots=True)
class AgentTraceEvent:
    trace_id: str
    run_id: str
    scope: AgentRunScope
    event_type: str
    payload: Mapping[str, Any]
    idempotency_key: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not all((self.trace_id, self.run_id, self.event_type, self.idempotency_key)):
            raise AgentRunPersistenceError("AGENT_TRACE_IDENTITY_REQUIRED")
        if self.occurred_at.tzinfo is None:
            raise AgentRunPersistenceError("AGENT_TRACE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        _assert_safe_mapping(self.payload, path="trace.payload")
        object.__setattr__(self, "payload", dict(self.payload))


# Short semantic alias for callers that refer to the persisted event as a Trace.
AgentTrace = AgentTraceEvent


@dataclass(frozen=True, slots=True)
class AgentRunRecord:
    run_id: str
    request_id: str
    agent_id: str
    tenant_id: str
    family_id: str
    use_case: str
    trace_id: str
    status: AgentRunStatus
    started_at: datetime
    completed_at: datetime | None
    error_code: str | None
    draft: ModelDraft | None
    idempotency_key: str
    task_fingerprint: str

    @property
    def may_mutate_business_state(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class AgentRunReplay:
    run: AgentRunRecord
    traces: tuple[AgentTraceEvent, ...]


class AgentRunPersistencePort(Protocol):
    async def create(
        self,
        task: AgentTask,
        *,
        run_id: str,
        trace_id: str,
        idempotency_key: str,
        started_at: datetime | None = None,
    ) -> AgentRunRecord:
        """Create a STARTED run (alias of ``start`` for command-oriented callers)."""
        ...

    async def start(
        self,
        task: AgentTask,
        *,
        run_id: str,
        trace_id: str,
        idempotency_key: str,
        started_at: datetime | None = None,
    ) -> AgentRunRecord:
        ...

    async def succeed(self, run: AgentRun, *, scope: AgentRunScope) -> AgentRunRecord:
        ...

    async def fail(
        self,
        run_id: str,
        *,
        scope: AgentRunScope,
        error_code: str,
        completed_at: datetime | None = None,
    ) -> AgentRunRecord:
        ...

    async def append_trace(self, event: AgentTraceEvent) -> AgentTraceEvent:
        ...

    async def replay(self, run_id: str, *, scope: AgentRunScope) -> AgentRunReplay | None:
        ...

    async def replay_by_request_id(
        self,
        request_id: str,
        *,
        scope: AgentRunScope,
    ) -> AgentRunReplay | None:
        """Resolve one stable logical request inside its trusted scope."""

        ...


class SqlAlchemyAgentRunStore:
    """Async SQLAlchemy implementation; transaction ownership stays external."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        task: AgentTask,
        *,
        run_id: str,
        trace_id: str,
        idempotency_key: str,
        started_at: datetime | None = None,
    ) -> AgentRunRecord:
        """Command alias that makes the create/start lifecycle explicit."""

        return await self.start(
            task,
            run_id=run_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            started_at=started_at,
        )

    async def start(
        self,
        task: AgentTask,
        *,
        run_id: str,
        trace_id: str,
        idempotency_key: str,
        started_at: datetime | None = None,
    ) -> AgentRunRecord:
        if not all((run_id, trace_id, idempotency_key)):
            raise AgentRunPersistenceError("AGENT_RUN_IDENTITY_REQUIRED")
        scope = AgentRunScope(task.tenant_id, task.family_id)
        fingerprint = agent_task_fingerprint(task)
        existing = await self._session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.tenant_id == scope.tenant_id,
                AgentRunRow.family_id == scope.family_id,
                AgentRunRow.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if not agent_task_fingerprint_matches(existing.idempotency_fingerprint, task):
                raise AgentRunConflict("AGENT_RUN_IDEMPOTENCY_REPLAY_MISMATCH")
            # Experimental rows created before fingerprints were hashed may
            # contain canonical task JSON. Redact it opportunistically on the
            # first safe replay without changing the replay identity.
            if existing.idempotency_fingerprint != fingerprint:
                existing.idempotency_fingerprint = fingerprint
                await self._session.flush()
            return _record(existing)
        instant = started_at or datetime.now(UTC)
        if instant.tzinfo is None:
            raise AgentRunPersistenceError("AGENT_RUN_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        row = AgentRunRow(
            tenant_id=scope.tenant_id,
            run_id=run_id,
            family_id=scope.family_id,
            request_id=task.request_id,
            agent_id=task.agent_id,
            use_case=task.use_case,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            idempotency_fingerprint=fingerprint,
            status=AgentRunStatus.STARTED.value,
            started_at=instant,
        )
        self._session.add(row)
        await self._session.flush()
        await self.append_trace(
            AgentTraceEvent(
                trace_id=trace_id,
                run_id=run_id,
                scope=scope,
                event_type="run.started",
                payload={"status": AgentRunStatus.STARTED.value},
                idempotency_key=f"{idempotency_key}:started",
                occurred_at=instant,
            )
        )
        return _record(row)

    async def succeed(self, run: AgentRun, *, scope: AgentRunScope) -> AgentRunRecord:
        row = await self._get(run.run_id, scope)
        if run.tenant_id != scope.tenant_id or run.family_id != scope.family_id:
            raise AgentRunConflict("AGENT_RUN_SCOPE_MISMATCH")
        draft_payload = _encode_draft(run.draft)
        if row.status == AgentRunStatus.SUCCEEDED.value:
            if row.draft_payload != draft_payload:
                raise AgentRunConflict("AGENT_RUN_COMPLETION_REPLAY_MISMATCH")
            return _record(row)
        if row.status != AgentRunStatus.STARTED.value:
            raise AgentRunConflict("AGENT_RUN_NOT_COMPLETABLE")
        row.status = AgentRunStatus.SUCCEEDED.value
        row.completed_at = _normalise_datetime(run.completed_at)
        row.draft_payload = draft_payload
        row.error_code = None
        await self._session.flush()
        await self.append_trace(
            AgentTraceEvent(
                trace_id=row.trace_id,
                run_id=row.run_id,
                scope=scope,
                event_type="run.succeeded",
                payload={"status": AgentRunStatus.SUCCEEDED.value},
                idempotency_key=f"{row.idempotency_key}:succeeded",
                occurred_at=row.completed_at,
            )
        )
        return _record(row)

    async def fail(
        self,
        run_id: str,
        *,
        scope: AgentRunScope,
        error_code: str,
        completed_at: datetime | None = None,
    ) -> AgentRunRecord:
        if not error_code:
            raise AgentRunPersistenceError("AGENT_RUN_ERROR_CODE_REQUIRED")
        row = await self._get(run_id, scope)
        if row.status == AgentRunStatus.FAILED.value:
            if row.error_code != error_code:
                raise AgentRunConflict("AGENT_RUN_FAILURE_REPLAY_MISMATCH")
            return _record(row)
        if row.status != AgentRunStatus.STARTED.value:
            raise AgentRunConflict("AGENT_RUN_NOT_FAILABLE")
        row.status = AgentRunStatus.FAILED.value
        row.completed_at = _normalise_datetime(completed_at or datetime.now(UTC))
        row.error_code = error_code
        await self._session.flush()
        await self.append_trace(
            AgentTraceEvent(
                trace_id=row.trace_id,
                run_id=row.run_id,
                scope=scope,
                event_type="run.failed",
                payload={"status": AgentRunStatus.FAILED.value, "error_code": error_code},
                idempotency_key=f"{row.idempotency_key}:failed",
                occurred_at=row.completed_at,
            )
        )
        return _record(row)

    async def append_trace(self, event: AgentTraceEvent) -> AgentTraceEvent:
        run = await self._session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.tenant_id == event.scope.tenant_id,
                AgentRunRow.family_id == event.scope.family_id,
                AgentRunRow.run_id == event.run_id,
            )
        )
        if run is None:
            raise AgentRunNotFound("AGENT_RUN_NOT_FOUND")
        if run.trace_id != event.trace_id:
            raise AgentRunConflict("AGENT_TRACE_ID_MISMATCH")
        existing = await self._session.scalar(
            select(AgentTraceRow).where(
                AgentTraceRow.tenant_id == event.scope.tenant_id,
                AgentTraceRow.run_id == event.run_id,
                AgentTraceRow.idempotency_key == event.idempotency_key,
            )
        )
        if existing is not None:
            if existing.event_type != event.event_type or existing.payload != dict(event.payload):
                raise AgentRunConflict("AGENT_TRACE_IDEMPOTENCY_REPLAY_MISMATCH")
            return _trace(existing)
        sequence = await self._next_sequence(event.scope, event.trace_id)
        row = AgentTraceRow(
            tenant_id=event.scope.tenant_id,
            trace_id=event.trace_id,
            sequence=sequence,
            run_id=event.run_id,
            family_id=event.scope.family_id,
            event_type=event.event_type,
            payload=dict(event.payload),
            idempotency_key=event.idempotency_key,
            occurred_at=_normalise_datetime(event.occurred_at),
        )
        self._session.add(row)
        await self._session.flush()
        return _trace(row)

    async def replay(self, run_id: str, *, scope: AgentRunScope) -> AgentRunReplay | None:
        row = await self._session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.tenant_id == scope.tenant_id,
                AgentRunRow.family_id == scope.family_id,
                AgentRunRow.run_id == run_id,
            )
        )
        if row is None:
            return None
        result = await self._session.scalars(
            select(AgentTraceRow)
            .where(
                AgentTraceRow.tenant_id == scope.tenant_id,
                AgentTraceRow.family_id == scope.family_id,
                AgentTraceRow.run_id == run_id,
            )
            .order_by(AgentTraceRow.sequence)
        )
        return AgentRunReplay(_record(row), tuple(_trace(trace) for trace in result))

    async def replay_by_request_id(
        self,
        request_id: str,
        *,
        scope: AgentRunScope,
    ) -> AgentRunReplay | None:
        if not isinstance(request_id, str) or not request_id.strip():
            raise AgentRunPersistenceError("AGENT_RUN_REQUEST_ID_REQUIRED")
        rows = (
            await self._session.scalars(
                select(AgentRunRow)
                .where(
                    AgentRunRow.tenant_id == scope.tenant_id,
                    AgentRunRow.family_id == scope.family_id,
                    AgentRunRow.request_id == request_id,
                )
                .limit(2)
            )
        ).all()
        if not rows:
            return None
        if len(rows) != 1:
            raise AgentRunConflict("AGENT_RUN_REQUEST_ID_AMBIGUOUS")
        return await self.replay(rows[0].run_id, scope=scope)

    async def _get(self, run_id: str, scope: AgentRunScope) -> AgentRunRow:
        row = await self._session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.tenant_id == scope.tenant_id,
                AgentRunRow.family_id == scope.family_id,
                AgentRunRow.run_id == run_id,
            )
        )
        if row is None:
            raise AgentRunNotFound("AGENT_RUN_NOT_FOUND")
        return row

    async def _next_sequence(self, scope: AgentRunScope, trace_id: str) -> int:
        latest = await self._session.scalar(
            select(AgentTraceRow.sequence)
            .where(
                AgentTraceRow.tenant_id == scope.tenant_id,
                AgentTraceRow.trace_id == trace_id,
            )
            .order_by(AgentTraceRow.sequence.desc())
            .limit(1)
        )
        return 0 if latest is None else int(latest) + 1


def agent_task_fingerprint(task: AgentTask) -> str:
    canonical = _canonical_task(task)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def agent_task_fingerprint_matches(stored: str, task: AgentTask) -> bool:
    """Accept the SHA-256 form and redactable pre-hash experimental rows."""

    canonical = _canonical_task(task)
    return stored == hashlib.sha256(canonical.encode("utf-8")).hexdigest() or stored == canonical


def _canonical_task(task: AgentTask) -> str:
    body = {
        "request_id": task.request_id,
        "agent_id": task.agent_id,
        "tenant_id": task.tenant_id,
        "family_id": task.family_id,
        "use_case": task.use_case,
        "context_snapshot_ref": task.context_snapshot_ref,
        "prompt_version": task.prompt_version,
        "schema_version": task.schema_version,
        "data_class": task.data_class,
        "input_refs": task.input_refs,
        "payload": _jsonable(task.payload),
        "output_schema": _jsonable(task.output_schema),
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def _encode_draft(draft: ModelDraft) -> dict[str, Any]:
    _assert_safe_mapping(draft.output, path="draft.output")
    if draft.status != "DRAFT" or draft.may_mutate_business_state:
        raise AgentRunPersistenceError("AGENT_RUN_DRAFT_ONLY_REQUIRED")
    provenance = draft.provenance
    payload: dict[str, Any] = {
        "output": _jsonable(draft.output),
        "status": "DRAFT",
        "provenance": {
            "provider_id": provenance.provider_id,
            "model": provenance.model,
            "model_version": provenance.model_version,
            "prompt_version": provenance.prompt_version,
            "schema_version": provenance.schema_version,
            "context_snapshot_ref": provenance.context_snapshot_ref,
            "latency_ms": provenance.latency_ms,
            "data_class": provenance.data_class,
            "use_case": provenance.use_case,
            "confidence": provenance.confidence,
            "token_usage": _jsonable(provenance.token_usage),
            "generated_at": provenance.generated_at.isoformat(),
        },
    }
    return payload


def _decode_draft(payload: Mapping[str, Any] | None) -> ModelDraft | None:
    if payload is None:
        return None
    if payload.get("status") != "DRAFT":
        raise AgentRunPersistenceError("AGENT_RUN_DRAFT_ONLY_REQUIRED")
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise AgentRunPersistenceError("AGENT_RUN_DRAFT_PROVENANCE_REQUIRED")
    usage = provenance.get("token_usage")
    token_usage = TokenUsage(**usage) if isinstance(usage, Mapping) else None
    return ModelDraft(
        output=dict(payload.get("output", {})),
        status="DRAFT",
        provenance=AiProvenance(
            provider_id=str(provenance["provider_id"]),
            model=str(provenance["model"]),
            model_version=str(provenance["model_version"]),
            prompt_version=str(provenance["prompt_version"]),
            schema_version=str(provenance["schema_version"]),
            context_snapshot_ref=str(provenance["context_snapshot_ref"]),
            latency_ms=int(provenance["latency_ms"]),
            data_class=provenance["data_class"],
            use_case=str(provenance["use_case"]),
            confidence=provenance.get("confidence"),
            token_usage=token_usage,
            generated_at=datetime.fromisoformat(str(provenance["generated_at"])),
        ),
    )


def _record(row: AgentRunRow) -> AgentRunRecord:
    return AgentRunRecord(
        run_id=row.run_id,
        request_id=row.request_id,
        agent_id=row.agent_id,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        use_case=row.use_case,
        trace_id=row.trace_id,
        status=AgentRunStatus(row.status),
        started_at=_normalise_datetime(row.started_at),
        completed_at=_normalise_datetime(row.completed_at) if row.completed_at else None,
        error_code=row.error_code,
        draft=_decode_draft(row.draft_payload),
        idempotency_key=row.idempotency_key,
        task_fingerprint=row.idempotency_fingerprint,
    )


def _trace(row: AgentTraceRow) -> AgentTraceEvent:
    return AgentTraceEvent(
        trace_id=row.trace_id,
        run_id=row.run_id,
        scope=AgentRunScope(row.tenant_id, row.family_id),
        event_type=row.event_type,
        payload=row.payload,
        idempotency_key=row.idempotency_key,
        occurred_at=_normalise_datetime(row.occurred_at),
    )


def _normalise_datetime(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


_FORBIDDEN_FACT_KEYS = frozenset(
    {"family_score", "family_rank", "ranking", "authoritative_fact", "canonical_state"}
)


def _assert_safe_mapping(value: object, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_FACT_KEYS:
                raise AgentRunPersistenceError(f"{path}.{key} cannot become a business fact")
            _assert_safe_mapping(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            _assert_safe_mapping(item, path=f"{path}[{index}]")
    elif isinstance(value, bytes):
        raise AgentRunPersistenceError(f"{path} cannot contain raw bytes")


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {name: _jsonable(getattr(value, name)) for name in value.__dataclass_fields__}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


__all__ = [
    "AgentRunConflict",
    "AgentRunNotFound",
    "AgentRunPersistenceBase",
    "AgentRunPersistenceError",
    "AgentRunPersistencePort",
    "AgentRunRecord",
    "AgentRunReplay",
    "AgentRunRow",
    "AgentRunScope",
    "AgentRunStatus",
    "agent_task_fingerprint",
    "agent_task_fingerprint_matches",
    "AgentTraceEvent",
    "AgentTrace",
    "AgentTraceRow",
    "SqlAlchemyAgentRunStore",
]
