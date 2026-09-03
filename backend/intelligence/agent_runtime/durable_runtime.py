"""Durable orchestration wrapper for the governed Agent Runtime."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime

from backend.intelligence.agent_runtime.contracts import AgentAuthorization, AgentRun, AgentTask
from backend.intelligence.agent_runtime.persistence import (
    AgentRunConflict,
    AgentRunPersistencePort,
    AgentRunReplay,
    AgentRunScope,
    AgentRunStatus,
)
from backend.intelligence.observability import TelemetryContext, TelemetrySink, TelemetrySpanHandle

from .runtime import AgentRuntime, AgentRuntimeError


class DurableAgentRuntimeError(AgentRuntimeError):
    """Raised when a durable run cannot safely be replayed or completed."""


class DurableAgentRuntime:
    """Persist AgentRun lifecycle around one provider-neutral AgentRuntime.

    The persistence port owns STARTED/SUCCEEDED/FAILED and append-only traces;
    this wrapper owns only idempotency and orchestration ordering.  It never
    commits a transaction and never executes a business Named Action.
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        store: AgentRunPersistencePort,
        *,
        clock: Callable[[], datetime] | None = None,
        telemetry_sink: TelemetrySink | None = None,
    ) -> None:
        if not isinstance(runtime, AgentRuntime):
            raise TypeError("runtime must be an AgentRuntime")
        self._runtime = runtime
        self._store = store
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)
        self._telemetry = telemetry_sink

    async def execute(
        self,
        task: AgentTask,
        authorization: AgentAuthorization | None,
        *,
        idempotency_key: str,
    ) -> AgentRun:
        handle = await self._start_telemetry(task, idempotency_key)
        try:
            result = await self._execute(
                task,
                authorization,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            await self._finish_telemetry(
                handle, status="ERROR", error_code=_error_code(exc)
            )
            raise
        await self._finish_telemetry(
            handle, status="OK", attributes={"draft_status": result.draft.status}
        )
        return result

    async def _execute(
        self,
        task: AgentTask,
        authorization: AgentAuthorization | None,
        *,
        idempotency_key: str,
    ) -> AgentRun:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        digest = hashlib.sha256(
            f"{task.tenant_id}:{task.family_id}:{idempotency_key}".encode()
        ).hexdigest()
        run_id = f"agent-run-{digest}"
        trace_id = f"trace-{digest}"
        scope = AgentRunScope(task.tenant_id, task.family_id)
        prior = await self._store.replay(run_id, scope=scope)
        if prior is not None:
            try:
                await self._store.start(
                    task,
                    run_id=prior.run.run_id,
                    trace_id=prior.run.trace_id,
                    idempotency_key=idempotency_key,
                    started_at=prior.run.started_at,
                )
            except AgentRunConflict as exc:
                raise DurableAgentRuntimeError(
                    "AGENT_RUN_IDEMPOTENCY_REPLAY_MISMATCH"
                ) from exc
            return self._replay_or_reject(prior)
        record = await self._store.start(
            task,
            run_id=run_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            started_at=self._clock(),
        )
        if record.status is AgentRunStatus.SUCCEEDED:
            if record.draft is None:
                raise DurableAgentRuntimeError("AGENT_RUN_REPLAY_DRAFT_MISSING")
            return AgentRun(
                run_id=record.run_id,
                request_id=record.request_id,
                agent_id=record.agent_id,
                tenant_id=record.tenant_id,
                family_id=record.family_id,
                use_case=record.use_case,
                draft=record.draft,
                started_at=record.started_at,
                completed_at=record.completed_at or record.started_at,
            )
        if record.status is AgentRunStatus.FAILED:
            raise DurableAgentRuntimeError("AGENT_RUN_REPLAY_FAILED")
        if record.status is not AgentRunStatus.STARTED:
            raise DurableAgentRuntimeError("AGENT_RUN_STATUS_UNSUPPORTED")

        try:
            run = await self._runtime.execute(task, authorization)
            if run.run_id != run_id:
                # The durable row is the replay identity.  Keep its stable id
                # instead of persisting a second anonymous runtime id.
                run = AgentRun(
                    run_id=run_id,
                    request_id=run.request_id,
                    agent_id=run.agent_id,
                    tenant_id=run.tenant_id,
                    family_id=run.family_id,
                    use_case=run.use_case,
                    draft=run.draft,
                    started_at=record.started_at,
                    completed_at=run.completed_at,
                )
            await self._store.succeed(run, scope=scope)
            return run
        except Exception as exc:
            error_code = _error_code(exc)
            await self._store.fail(
                run_id,
                scope=scope,
                error_code=error_code,
                completed_at=self._clock(),
            )
            raise

    async def _start_telemetry(
        self, task: AgentTask, idempotency_key: str
    ) -> TelemetrySpanHandle | None:
        if self._telemetry is None:
            return None
        try:
            digest = hashlib.sha256(
                f"{task.tenant_id}:{task.family_id}:{idempotency_key}".encode()
            ).hexdigest()
            context = TelemetryContext(
                trace_id=task.request_id or f"trace-{digest}",
                request_id=task.request_id,
                tenant_id=task.tenant_id,
                family_id=task.family_id,
                use_case=task.use_case,
                data_class=task.data_class,
                operation_id=f"agent:{task.agent_id}:{idempotency_key}",
            )
            return await self._telemetry.start_span(
                name="ai.agent_runtime.execute",
                context=context,
                attributes={"stage": "agent"},
            )
        except Exception:
            return None

    async def _finish_telemetry(
        self,
        handle: TelemetrySpanHandle | None,
        *,
        status: str,
        error_code: str | None = None,
        attributes: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        if handle is None or self._telemetry is None:
            return
        try:
            await self._telemetry.finish_span(
                handle,
                status=status,  # type: ignore[arg-type]
                error_code=error_code,
                attributes=attributes or {},
            )
        except Exception:
            return

    @staticmethod
    def _replay_or_reject(prior: AgentRunReplay) -> AgentRun:
        record = prior.run
        if record.status is AgentRunStatus.SUCCEEDED:
            if record.draft is None:
                raise DurableAgentRuntimeError("AGENT_RUN_REPLAY_DRAFT_MISSING")
            return AgentRun(
                run_id=record.run_id,
                request_id=record.request_id,
                agent_id=record.agent_id,
                tenant_id=record.tenant_id,
                family_id=record.family_id,
                use_case=record.use_case,
                draft=record.draft,
                started_at=record.started_at,
                completed_at=record.completed_at or record.started_at,
            )
        if record.status is AgentRunStatus.FAILED:
            raise DurableAgentRuntimeError("AGENT_RUN_REPLAY_FAILED")
        raise DurableAgentRuntimeError("AGENT_RUN_IN_PROGRESS")


def _error_code(error: Exception) -> str:
    kind = getattr(error, "kind", None)
    if isinstance(kind, str) and kind:
        return kind[:128]
    return type(error).__name__[:128] or "AGENT_RUNTIME_ERROR"


__all__ = ["DurableAgentRuntime", "DurableAgentRuntimeError"]
