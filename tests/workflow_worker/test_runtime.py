from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from backend.workflow_worker.runtime import (
    AcceptedActionActivity,
    ActivityExecution,
    GrowthActionExperienceRelayActivity,
    WorkerState,
    WorkflowWorkerConfigurationError,
    WorkflowWorkerRuntime,
)

NOW = datetime(2026, 9, 3, 6, tzinfo=UTC)


@dataclass
class RecordingActivity:
    name: str
    outcomes: list[object] = field(default_factory=list)
    calls: int = 0

    async def run_once(self) -> ActivityExecution:
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else {"processed": 0}
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, ActivityExecution):
            return outcome
        return ActivityExecution(True, type(outcome).__name__)


@dataclass
class RecordingAcceptedRuntime:
    calls: list[tuple[int, int]] = field(default_factory=list)
    result: object = field(default_factory=lambda: Report())

    async def run_until_idle(self, *, limit: int, max_polls: int) -> object:
        self.calls.append((limit, max_polls))
        return self.result


@dataclass
class RecordingRelay:
    calls: list[int] = field(default_factory=list)

    async def run_once(self, *, limit: int) -> object:
        self.calls.append(limit)
        return RelayReport()


@dataclass(frozen=True)
class Report:
    retried: int = 0
    dead_lettered: int = 0


@dataclass(frozen=True)
class RelayReport:
    failed: int = 0
    dead_lettered: int = 0


@pytest.mark.asyncio
async def test_cycle_runs_all_activities_and_recovers_from_degraded_state() -> None:
    healthy = RecordingActivity("healthy")
    unstable = RecordingActivity(
        "unstable",
        outcomes=[RuntimeError("provider detail must not leak"), {"processed": 1}],
    )
    runtime = WorkflowWorkerRuntime(
        activities=(healthy, unstable),
        degraded_after_failed_cycles=1,
        clock=lambda: NOW,
    )

    failed = await runtime.run_cycle()
    assert [outcome.succeeded for outcome in failed] == [True, False]
    assert runtime.health.state is WorkerState.DEGRADED
    assert runtime.health.live is True
    assert runtime.health.ready is False
    assert runtime.health.consecutive_failed_cycles == 1
    assert all("provider detail" not in repr(outcome) for outcome in failed)
    assert failed[1].error_type == "RuntimeError"

    recovered = await runtime.run_cycle()
    assert all(outcome.succeeded for outcome in recovered)
    assert runtime.health.state is WorkerState.RUNNING
    assert runtime.health.ready is True
    assert runtime.health.consecutive_failed_cycles == 0
    assert runtime.health.cycle_count == 2


@pytest.mark.asyncio
async def test_reported_retry_degrades_health_without_requiring_exception() -> None:
    accepted = RecordingAcceptedRuntime(result=Report(retried=1))
    runtime = WorkflowWorkerRuntime(
        activities=(AcceptedActionActivity(accepted),),
        degraded_after_failed_cycles=1,
        clock=lambda: NOW,
    )

    outcomes = await runtime.run_cycle()

    assert outcomes[0].succeeded is False
    assert outcomes[0].error_type == "AcceptedActionReportFailure"
    assert runtime.health.state is WorkerState.DEGRADED


@pytest.mark.asyncio
async def test_activity_timeout_bounds_a_stuck_poll() -> None:
    blocker = asyncio.Event()

    @dataclass
    class StuckActivity:
        name: str = "stuck"

        async def run_once(self) -> ActivityExecution:
            await blocker.wait()
            return ActivityExecution(True, "never")

    runtime = WorkflowWorkerRuntime(
        activities=(StuckActivity(),),
        activity_timeout=timedelta(milliseconds=5),
        degraded_after_failed_cycles=1,
        clock=lambda: NOW,
    )

    outcomes = await runtime.run_cycle()

    assert outcomes[0].succeeded is False
    assert outcomes[0].error_type == "TimeoutError"
    assert runtime.health.state is WorkerState.DEGRADED


@pytest.mark.asyncio
async def test_run_forever_stops_without_waiting_for_next_poll() -> None:
    stop = asyncio.Event()
    activity = RecordingActivity("only")

    async def controlled_sleep(_seconds: float) -> None:
        stop.set()

    runtime = WorkflowWorkerRuntime(
        activities=(activity,),
        poll_interval=timedelta(hours=1),
        clock=lambda: NOW,
        sleep=controlled_sleep,
    )
    await runtime.run_forever(stop)

    assert activity.calls == 1
    assert runtime.health.state is WorkerState.STOPPED
    assert runtime.health.live is False
    assert runtime.health.cycle_count == 1


@pytest.mark.asyncio
async def test_production_activity_adapters_keep_bounded_poll_contracts() -> None:
    accepted = RecordingAcceptedRuntime()
    relay = RecordingRelay()

    await AcceptedActionActivity(accepted, limit=17, max_polls=4).run_once()
    await GrowthActionExperienceRelayActivity(relay, limit=23).run_once()

    assert accepted.calls == [(17, 4)]
    assert relay.calls == [23]


def test_runtime_rejects_invalid_process_configuration() -> None:
    with pytest.raises(WorkflowWorkerConfigurationError, match="at least one"):
        WorkflowWorkerRuntime(activities=())
    with pytest.raises(WorkflowWorkerConfigurationError, match="unique"):
        WorkflowWorkerRuntime(
            activities=(RecordingActivity("same"), RecordingActivity("same"))
        )
    with pytest.raises(WorkflowWorkerConfigurationError, match="positive"):
        AcceptedActionActivity(RecordingAcceptedRuntime(), limit=0)
