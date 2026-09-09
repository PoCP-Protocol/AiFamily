from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.apps.family_api.feedback_regression_scheduler_wiring import (
    FeedbackRegressionSchedule,
    build_sql_feedback_regression_scheduler,
)
from backend.intelligence.evaluation.feedback_regression import FeedbackRegressionCaseSource
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger


def test_production_feedback_scheduler_requires_explicit_dependencies() -> None:
    ledger = InMemoryExperienceRunLedger()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, class_=AsyncSession)
    with pytest.raises(ValueError, match="INTERVAL_INVALID"):
        FeedbackRegressionSchedule(interval=timedelta(0))
    with pytest.raises(TypeError, match="case_source"):
        build_sql_feedback_regression_scheduler(
            session_factory=sessions,
            case_source=object(),  # type: ignore[arg-type]
            ledger=ledger,
            adapter=lambda case: {},
            worker_id="worker-1",
        )


def test_production_feedback_scheduler_builds_sql_runtime() -> None:
    ledger = InMemoryExperienceRunLedger()

    class Source(FeedbackRegressionCaseSource):
        async def load(self, **kwargs):
            return ()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, class_=AsyncSession)
    runtime = build_sql_feedback_regression_scheduler(
        session_factory=sessions,
        case_source=Source(),
        ledger=ledger,
        adapter=lambda case: {},
        worker_id="worker-1",
    )
    assert runtime.schedule.batch_limit == 20
    assert runtime.scheduler.worker_id == "worker-1"
