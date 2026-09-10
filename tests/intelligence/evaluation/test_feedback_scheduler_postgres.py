from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.intelligence.evaluation.feedback_regression import FeedbackRegressionBatch
from backend.intelligence.evaluation.feedback_scheduler import (
    FeedbackJobStatus,
    FeedbackRegressionJob,
    FeedbackSchedulerBase,
    SqlAlchemyFeedbackRegressionJobStore,
)
from backend.intelligence.experience.run_http import RunScope
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

NOW = datetime(2026, 9, 10, tzinfo=UTC)


def _job() -> FeedbackRegressionJob:
    scope = RunScope(tenant_id="tenant-pg", family_id="family-pg", subject_ids=("child-pg",))
    return FeedbackRegressionJob(
        job_id="feedback-pg-1",
        batch=FeedbackRegressionBatch(
            batch_ref="batch-pg-1",
            case_version="feedback-v1",
            run_id="run-pg-1",
            scope=scope,
        ),
        due_at=NOW,
    )


@pytest.mark.asyncio
async def test_postgres_feedback_job_claim_takeover_and_completion() -> None:
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)
    async with postgres_schema_engine(FeedbackSchedulerBase.metadata) as engine:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        first_store = SqlAlchemyFeedbackRegressionJobStore(sessions)
        job = await first_store.enqueue(_job())
        claimed = await first_store.claim_due(
            worker_id="worker-a", now=NOW, lease_ttl=timedelta(minutes=1), limit=1
        )
        assert claimed[0].status is FeedbackJobStatus.LEASED

        second_store = SqlAlchemyFeedbackRegressionJobStore(sessions)
        assert (
            await second_store.claim_due(
                worker_id="worker-b",
                now=NOW + timedelta(seconds=30),
                lease_ttl=timedelta(minutes=1),
                limit=1,
            )
            == ()
        )
        takeover = await second_store.claim_due(
            worker_id="worker-b",
            now=NOW + timedelta(minutes=1),
            lease_ttl=timedelta(minutes=1),
            limit=1,
        )
        assert takeover[0].attempts == 2
        completed = await second_store.complete(
            job.job_id, worker_id="worker-b", now=NOW + timedelta(minutes=1)
        )
        assert completed.status is FeedbackJobStatus.COMPLETED
