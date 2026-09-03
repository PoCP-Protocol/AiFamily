"""Metadata-only health endpoints for the standalone workflow worker."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Response, status

from backend.workflow_worker.runtime import WorkerHealth


def build_worker_health_app(health: Callable[[], WorkerHealth]) -> FastAPI:
    if not callable(health):
        raise TypeError("worker health provider must be callable")
    app = FastAPI(title="AiFamily Workflow Worker", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def liveness(response: Response) -> dict[str, object]:
        snapshot = health()
        if not snapshot.live:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return _payload(snapshot)

    @app.get("/ready")
    async def readiness(response: Response) -> dict[str, object]:
        snapshot = health()
        if not snapshot.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return _payload(snapshot)

    return app


def _payload(snapshot: WorkerHealth) -> dict[str, object]:
    return {
        "service": "workflow_worker",
        "state": snapshot.state.value,
        "live": snapshot.live,
        "ready": snapshot.ready,
        "cycle_count": snapshot.cycle_count,
        "consecutive_failed_cycles": snapshot.consecutive_failed_cycles,
        "last_cycle_started_at": _timestamp(snapshot.last_cycle_started_at),
        "last_cycle_completed_at": _timestamp(snapshot.last_cycle_completed_at),
        "activities": [
            {
                "name": outcome.activity,
                "succeeded": outcome.succeeded,
                "result_type": outcome.result_type,
                "error_type": outcome.error_type,
            }
            for outcome in snapshot.last_outcomes
        ],
    }


def _timestamp(value) -> str | None:
    return None if value is None else value.isoformat()


__all__ = ["build_worker_health_app"]
