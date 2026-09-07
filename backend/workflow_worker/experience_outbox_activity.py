"""Worker activity that drains the governed Experience outbox.

Before this module, ``ExperienceAchievementConsumer`` and
``GrowthGraphOutboxConsumer`` existed and were exercised in tests, but nothing
in the running composition root ever called ``SqlAlchemyExperienceOutbox
.pending()``/``.mark_published()`` in production: the Experience outbox
(fed in turn by ``GrowthActionExperienceRelay``, which *is* wired into
``workflow_worker/main.py``) had no consumer that actually drained it.  This
activity closes that gap using the exact fan-out consumer
(``AtomicExperienceFanoutConsumer``) already proven in
``tests/domains/action/test_daily_action_postgres.py``: one bounded batch per
tick, each message projected into every registered consumer (achievement +
Growth Graph today) before it is marked published, and the whole batch runs on
one caller-owned ``AsyncSession``/transaction so a projection failure leaves
the message pending for the next tick rather than silently skipped.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.experience.achievement_consumer import (
    ExperienceAchievementConsumer,
)
from backend.intelligence.experience.achievement_persistence import (
    SqlAlchemyAchievementProjection,
)
from backend.intelligence.experience.persistence import SqlAlchemyExperienceOutbox
from backend.intelligence.experience.projections import (
    SqlAlchemyAchievementNotificationProjection,
    SqlAlchemyExperienceAnalyticsProjection,
)
from backend.intelligence.growth_graph.outbox_consumer import GrowthGraphOutboxConsumer
from backend.intelligence.growth_graph.store import SqlAlchemyGrowthGraphProjection
from backend.workflow_worker.experience_fanout import AtomicExperienceFanoutConsumer
from backend.workflow_worker.runtime import ActivityExecution, WorkflowWorkerConfigurationError


@dataclass(frozen=True, slots=True)
class ExperienceOutboxFanoutReport:
    inspected: int
    published: int
    failed: int


@dataclass(frozen=True, slots=True)
class ExperienceOutboxFanoutRunner:
    """Drain the governed Experience outbox through every registered projection."""

    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("experience outbox fanout requires async_sessionmaker")

    async def run_once(self, *, limit: int = 100) -> ExperienceOutboxFanoutReport:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("experience outbox fanout limit must be positive")
        published = 0
        failed = 0
        async with self.session_factory() as session, session.begin():
            outbox = SqlAlchemyExperienceOutbox(session)
            pending = await outbox.pending(limit=limit)
            consumer = AtomicExperienceFanoutConsumer(
                (
                    ExperienceAchievementConsumer(
                        projection=SqlAlchemyAchievementProjection(session),
                        notifications=SqlAlchemyAchievementNotificationProjection(session),
                        analytics=SqlAlchemyExperienceAnalyticsProjection(session),
                    ),
                    GrowthGraphOutboxConsumer(SqlAlchemyGrowthGraphProjection(session)),
                )
            )
            for message in pending:
                try:
                    await consumer.consume(message)
                except Exception:  # noqa: BLE001 - leave the message pending for retry
                    failed += 1
                    continue
                await outbox.mark_published(message.message_id)
                published += 1
        return ExperienceOutboxFanoutReport(
            inspected=len(pending),
            published=published,
            failed=failed,
        )


@dataclass(frozen=True, slots=True)
class ExperienceOutboxFanoutActivity:
    """``WorkerActivity`` wrapper so the runner joins the same poll loop."""

    runner: ExperienceOutboxFanoutRunner
    limit: int = 100
    name: str = "experience_outbox_fanout"

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise WorkflowWorkerConfigurationError(
                "experience outbox fanout limit must be positive"
            )

    async def run_once(self) -> ActivityExecution:
        report = await self.runner.run_once(limit=self.limit)
        return ActivityExecution(
            succeeded=report.failed == 0,
            result_type=type(report).__name__,
            error_type=(None if report.failed == 0 else "ExperienceOutboxFanoutReportFailure"),
        )


__all__ = [
    "ExperienceOutboxFanoutActivity",
    "ExperienceOutboxFanoutReport",
    "ExperienceOutboxFanoutRunner",
]
