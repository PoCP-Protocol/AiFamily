"""Standalone process entry for AiFamily durable workflow orchestration."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import uvicorn

from backend.apps.family_api.production_growth_plan_action_wiring import (
    build_production_growth_plan_action_runtime,
)
from backend.domains.action.infrastructure.postgres import (
    SqlAlchemyDailyActionApplication,
)
from backend.domains.journey.infrastructure.application import (
    build_postgres_journey_application,
)
from backend.platform.persistence.session import (
    get_engine,
    get_sessionmaker,
    is_postgres_url,
    resolve_database_url,
)
from backend.workflow_worker.growth_action_experience_relay import (
    GrowthActionExperienceRelay,
)
from backend.workflow_worker.health import build_worker_health_app
from backend.workflow_worker.runtime import (
    AcceptedActionActivity,
    GrowthActionExperienceRelayActivity,
    WorkflowWorkerRuntime,
)

LOGGER = logging.getLogger("aifamily.workflow_worker")


@dataclass(frozen=True, slots=True)
class WorkflowWorkerSettings:
    database_url: str
    claim_owner: str
    poll_interval: timedelta
    batch_limit: int
    accepted_action_max_polls: int
    degraded_after_failed_cycles: int
    activity_timeout: timedelta
    health_host: str
    health_port: int

    @classmethod
    def from_environment(cls) -> WorkflowWorkerSettings:
        database_url = resolve_database_url()
        if not is_postgres_url(database_url):
            raise RuntimeError("workflow_worker_requires_postgresql")
        return cls(
            database_url=database_url,
            claim_owner=os.getenv(
                "AIFAMILY_WORKER_CLAIM_OWNER",
                _default_claim_owner(),
            ),
            poll_interval=timedelta(
                seconds=_positive_float("AIFAMILY_WORKER_POLL_SECONDS", 2.0)
            ),
            batch_limit=_positive_int("AIFAMILY_WORKER_BATCH_LIMIT", 100),
            accepted_action_max_polls=_positive_int(
                "AIFAMILY_WORKER_MAX_POLLS", 10
            ),
            degraded_after_failed_cycles=_positive_int(
                "AIFAMILY_WORKER_DEGRADED_AFTER", 3
            ),
            activity_timeout=timedelta(
                seconds=_positive_float("AIFAMILY_WORKER_ACTIVITY_TIMEOUT_SECONDS", 60.0)
            ),
            health_host=os.getenv("AIFAMILY_WORKER_HEALTH_HOST", "0.0.0.0"),
            health_port=_positive_int("AIFAMILY_WORKER_HEALTH_PORT", 8082),
        )


def build_runtime(settings: WorkflowWorkerSettings) -> WorkflowWorkerRuntime:
    engine = get_engine(settings.database_url)
    session_factory = get_sessionmaker(settings.database_url)
    journey = build_postgres_journey_application(settings.database_url)
    accepted_actions = build_production_growth_plan_action_runtime(
        session_factory=session_factory,
        journey_application=journey,
        daily_action_initializer=SqlAlchemyDailyActionApplication(engine),
        claim_owner=settings.claim_owner,
        clock=lambda: datetime.now(UTC),
    )
    return WorkflowWorkerRuntime(
        activities=(
            AcceptedActionActivity(
                accepted_actions,
                limit=settings.batch_limit,
                max_polls=settings.accepted_action_max_polls,
            ),
            GrowthActionExperienceRelayActivity(
                GrowthActionExperienceRelay(session_factory),
                limit=settings.batch_limit,
            ),
        ),
        poll_interval=settings.poll_interval,
        activity_timeout=settings.activity_timeout,
        degraded_after_failed_cycles=settings.degraded_after_failed_cycles,
    )


async def serve(settings: WorkflowWorkerSettings | None = None) -> None:
    resolved = settings or WorkflowWorkerSettings.from_environment()
    runtime = build_runtime(resolved)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, stop.set)
        except NotImplementedError:
            signal.signal(signal_name, lambda *_: loop.call_soon_threadsafe(stop.set))
    LOGGER.info(
        "workflow worker started owner=%s activities=%s",
        resolved.claim_owner,
        [activity.name for activity in runtime.activities],
    )
    server = uvicorn.Server(
        uvicorn.Config(
            build_worker_health_app(lambda: runtime.health),
            host=resolved.health_host,
            port=resolved.health_port,
            log_level=os.getenv("AIFAMILY_LOG_LEVEL", "info").lower(),
            access_log=False,
        )
    )
    server.install_signal_handlers = lambda: None
    worker_task = asyncio.create_task(runtime.run_forever(stop))
    probe_task = asyncio.create_task(server.serve())
    stop_task = asyncio.create_task(stop.wait())
    done, _pending = await asyncio.wait(
        {worker_task, probe_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    stop.set()
    server.should_exit = True
    await asyncio.gather(worker_task, probe_task, return_exceptions=False)
    stop_task.cancel()
    await asyncio.gather(stop_task, return_exceptions=True)
    for task in done:
        if task is not stop_task:
            task.result()
    LOGGER.info("workflow worker stopped cycles=%s", runtime.health.cycle_count)


async def run_once(settings: WorkflowWorkerSettings | None = None) -> None:
    resolved = settings or WorkflowWorkerSettings.from_environment()
    runtime = build_runtime(resolved)
    outcomes = await runtime.run_cycle()
    if not all(outcome.succeeded for outcome in outcomes):
        failed = [outcome.activity for outcome in outcomes if not outcome.succeeded]
        raise RuntimeError(f"workflow_worker_cycle_failed:{','.join(failed)}")


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=os.getenv("AIFAMILY_LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(description="Run the AiFamily workflow worker")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="validate production configuration and composition, then exit",
    )
    mode.add_argument(
        "--once",
        action="store_true",
        help="run one bounded orchestration cycle, then exit",
    )
    arguments = parser.parse_args(argv)
    settings = WorkflowWorkerSettings.from_environment()
    if arguments.check:
        build_runtime(settings)
        LOGGER.info("workflow worker configuration is valid")
        return
    if arguments.once:
        asyncio.run(run_once(settings))
        return
    asyncio.run(serve(settings))


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name}_must_be_integer") from error
    if value < 1:
        raise RuntimeError(f"{name}_must_be_positive")
    return value


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name}_must_be_number") from error
    if value <= 0:
        raise RuntimeError(f"{name}_must_be_positive")
    return value


def _default_claim_owner() -> str:
    host = socket.gethostname().strip()[:40] or "unknown-host"
    return f"workflow-worker:{host}:{os.getpid()}:{uuid4().hex[:12]}"


if __name__ == "__main__":
    main()
