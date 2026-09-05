"""Continuous orchestration loop for durable AiFamily workflow activities.

The worker owns scheduling and retry cadence only.  Each activity keeps its own
database transaction, idempotency and lease semantics; this loop never writes a
domain fact directly and never treats a successful poll as a business outcome.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol


class WorkflowWorkerConfigurationError(ValueError):
    pass


class WorkerActivity(Protocol):
    name: str

    async def run_once(self) -> ActivityExecution: ...


class AcceptedActionRuntime(Protocol):
    async def run_until_idle(
        self, *, limit: int, max_polls: int
    ) -> object: ...


class GrowthActionRelay(Protocol):
    async def run_once(self, *, limit: int) -> object: ...


class WorkerState(StrEnum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


@dataclass(frozen=True, slots=True)
class ActivityOutcome:
    activity: str
    succeeded: bool
    completed_at: datetime
    result_type: str | None = None
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class ActivityExecution:
    succeeded: bool
    result_type: str
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerHealth:
    state: WorkerState
    cycle_count: int
    consecutive_failed_cycles: int
    last_cycle_started_at: datetime | None
    last_cycle_completed_at: datetime | None
    last_outcomes: tuple[ActivityOutcome, ...]

    @property
    def ready(self) -> bool:
        return self.state is WorkerState.RUNNING

    @property
    def live(self) -> bool:
        return self.state in {WorkerState.RUNNING, WorkerState.DEGRADED}


@dataclass(frozen=True, slots=True)
class AcceptedActionActivity:
    runtime: AcceptedActionRuntime
    limit: int = 100
    max_polls: int = 10
    name: str = "accepted_named_actions"

    def __post_init__(self) -> None:
        if self.limit < 1 or self.max_polls < 1:
            raise WorkflowWorkerConfigurationError("accepted action limits must be positive")

    async def run_once(self) -> ActivityExecution:
        report = await self.runtime.run_until_idle(limit=self.limit, max_polls=self.max_polls)
        failed = int(getattr(report, "retried", 0)) + int(
            getattr(report, "dead_lettered", 0)
        )
        return ActivityExecution(
            succeeded=failed == 0,
            result_type=type(report).__name__,
            error_type=(None if failed == 0 else "AcceptedActionReportFailure"),
        )


@dataclass(frozen=True, slots=True)
class GrowthActionExperienceRelayActivity:
    relay: GrowthActionRelay
    limit: int = 100
    name: str = "growth_action_experience_relay"

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise WorkflowWorkerConfigurationError("relay limit must be positive")

    async def run_once(self) -> ActivityExecution:
        report = await self.relay.run_once(limit=self.limit)
        failed = int(getattr(report, "failed", 0)) + int(
            getattr(report, "dead_lettered", 0)
        )
        return ActivityExecution(
            succeeded=failed == 0,
            result_type=type(report).__name__,
            error_type=(None if failed == 0 else "GrowthActionRelayReportFailure"),
        )


@dataclass(slots=True)
class WorkflowWorkerRuntime:
    activities: tuple[WorkerActivity, ...]
    poll_interval: timedelta = timedelta(seconds=2)
    activity_timeout: timedelta = timedelta(minutes=1)
    degraded_after_failed_cycles: int = 3
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    _state: WorkerState = field(init=False, default=WorkerState.STARTING)
    _cycle_count: int = field(init=False, default=0)
    _consecutive_failed_cycles: int = field(init=False, default=0)
    _last_cycle_started_at: datetime | None = field(init=False, default=None)
    _last_cycle_completed_at: datetime | None = field(init=False, default=None)
    _last_outcomes: tuple[ActivityOutcome, ...] = field(init=False, default=())

    def __post_init__(self) -> None:
        self.activities = tuple(self.activities)
        if not self.activities:
            raise WorkflowWorkerConfigurationError("at least one worker activity is required")
        names = [activity.name for activity in self.activities]
        if any(not name.strip() for name in names) or len(names) != len(set(names)):
            raise WorkflowWorkerConfigurationError("worker activity names must be unique")
        if self.poll_interval <= timedelta(0):
            raise WorkflowWorkerConfigurationError("poll interval must be positive")
        if self.activity_timeout <= timedelta(0):
            raise WorkflowWorkerConfigurationError("activity timeout must be positive")
        if self.degraded_after_failed_cycles < 1:
            raise WorkflowWorkerConfigurationError(
                "degraded failure threshold must be positive"
            )
        if not callable(self.clock) or not callable(self.sleep):
            raise WorkflowWorkerConfigurationError("worker clock and sleep are required")

    @classmethod
    def from_activities(
        cls,
        activities: Iterable[WorkerActivity],
        **kwargs: object,
    ) -> WorkflowWorkerRuntime:
        return cls(activities=tuple(activities), **kwargs)

    @property
    def health(self) -> WorkerHealth:
        return WorkerHealth(
            state=self._state,
            cycle_count=self._cycle_count,
            consecutive_failed_cycles=self._consecutive_failed_cycles,
            last_cycle_started_at=self._last_cycle_started_at,
            last_cycle_completed_at=self._last_cycle_completed_at,
            last_outcomes=self._last_outcomes,
        )

    async def run_cycle(self) -> tuple[ActivityOutcome, ...]:
        if self._state is WorkerState.STARTING:
            self._state = WorkerState.RUNNING
        self._last_cycle_started_at = _aware(self.clock())
        outcomes: list[ActivityOutcome] = []
        for activity in self.activities:
            try:
                execution = await asyncio.wait_for(
                    activity.run_once(),
                    timeout=self.activity_timeout.total_seconds(),
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - activity owns durable retry details
                outcomes.append(
                    ActivityOutcome(
                        activity=activity.name,
                        succeeded=False,
                        completed_at=_aware(self.clock()),
                        error_type=type(error).__name__,
                    )
                )
            else:
                outcomes.append(
                    ActivityOutcome(
                        activity=activity.name,
                        succeeded=execution.succeeded,
                        completed_at=_aware(self.clock()),
                        result_type=execution.result_type,
                        error_type=execution.error_type,
                    )
                )
        self._cycle_count += 1
        self._last_cycle_completed_at = _aware(self.clock())
        self._last_outcomes = tuple(outcomes)
        if all(outcome.succeeded for outcome in outcomes):
            self._consecutive_failed_cycles = 0
            self._state = WorkerState.RUNNING
        else:
            self._consecutive_failed_cycles += 1
            if self._consecutive_failed_cycles >= self.degraded_after_failed_cycles:
                self._state = WorkerState.DEGRADED
        return self._last_outcomes

    async def run_forever(self, stop: asyncio.Event) -> None:
        if not isinstance(stop, asyncio.Event):
            raise TypeError("stop must be an asyncio.Event")
        try:
            while not stop.is_set():
                await self.run_cycle()
                if stop.is_set():
                    break
                await _sleep_until_stop(
                    stop,
                    seconds=self.poll_interval.total_seconds(),
                    sleep=self.sleep,
                )
        finally:
            self._state = WorkerState.STOPPED


async def _sleep_until_stop(
    stop: asyncio.Event,
    *,
    seconds: float,
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    sleeper = asyncio.create_task(sleep(seconds))
    stopper = asyncio.create_task(stop.wait())
    done, pending = await asyncio.wait(
        {sleeper, stopper},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        await task


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise WorkflowWorkerConfigurationError("worker clock must be timezone-aware")
    return value.astimezone(UTC)


__all__ = [
    "AcceptedActionActivity",
    "ActivityExecution",
    "ActivityOutcome",
    "GrowthActionExperienceRelayActivity",
    "WorkerActivity",
    "WorkerHealth",
    "WorkerState",
    "WorkflowWorkerConfigurationError",
    "WorkflowWorkerRuntime",
]
