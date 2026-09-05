from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from backend.workflow_worker.health import build_worker_health_app
from backend.workflow_worker.runtime import (
    ActivityOutcome,
    WorkerHealth,
    WorkerState,
)

NOW = datetime(2026, 9, 3, 8, tzinfo=UTC)


def _health(state: WorkerState) -> WorkerHealth:
    return WorkerHealth(
        state=state,
        cycle_count=4,
        consecutive_failed_cycles=2 if state is WorkerState.DEGRADED else 0,
        last_cycle_started_at=NOW,
        last_cycle_completed_at=NOW,
        last_outcomes=(
            ActivityOutcome(
                activity="accepted_named_actions",
                succeeded=state is WorkerState.RUNNING,
                completed_at=NOW,
                error_type=(None if state is WorkerState.RUNNING else "RuntimeError"),
            ),
        ),
    )


def test_health_probe_exposes_only_bounded_operational_metadata() -> None:
    current = _health(WorkerState.RUNNING)
    client = TestClient(build_worker_health_app(lambda: current))

    live = client.get("/health")
    ready = client.get("/ready")

    assert live.status_code == 200
    assert ready.status_code == 200
    assert ready.json()["activities"] == [
        {
            "name": "accepted_named_actions",
            "succeeded": True,
            "result_type": None,
            "error_type": None,
        }
    ]


def test_degraded_worker_is_live_but_not_ready() -> None:
    client = TestClient(build_worker_health_app(lambda: _health(WorkerState.DEGRADED)))

    assert client.get("/health").status_code == 200
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["activities"][0]["error_type"] == "RuntimeError"


def test_stopped_worker_fails_both_probes() -> None:
    client = TestClient(build_worker_health_app(lambda: _health(WorkerState.STOPPED)))

    assert client.get("/health").status_code == 503
    assert client.get("/ready").status_code == 503
