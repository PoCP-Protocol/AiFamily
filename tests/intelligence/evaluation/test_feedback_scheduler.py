from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.intelligence.evaluation.feedback_regression import (
    FeedbackRegressionBatch,
    FeedbackRegressionCase,
    FeedbackRegressionWorker,
)
from backend.intelligence.evaluation.feedback_scheduler import (
    FeedbackJobStatus,
    FeedbackRegressionJob,
    FeedbackRegressionScheduler,
    FeedbackSchedulerBase,
    InMemoryFeedbackRegressionJobStore,
    SqlAlchemyFeedbackRegressionJobStore,
)
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger, RunScope


def _case() -> FeedbackRegressionCase:
    return FeedbackRegressionCase(
        case_ref="case-scheduler",
        case_version="feedback-v1",
        feedback_ref="feedback-scheduler",
        feedback_kind="GUARDIAN_EDIT",
        input_contract={"capability_refs": ["practice:morning"]},
        expected_output={"next_step": "记录一次晨间观察"},
        output_schema={
            "type": "object",
            "required": ["next_step"],
            "properties": {"next_step": {"type": "string"}},
        },
        scope_digest="sha256:opaque-scheduler-scope",
    )


class Source:
    async def load(self, **kwargs):
        return (_case(),)


def _worker():
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope(tenant_id="tenant-1", family_id="family-1", subject_ids=("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id="run-scheduler",
        request_ref="agi:need:path",
        draft_payload={"family_need_id": "need-1", "status": "DRAFT"},
        idempotency_key="create-scheduler",
    )
    return (
        FeedbackRegressionWorker(
            case_source=Source(),
            ledger=ledger,
            adapter=lambda case: {"next_step": "记录一次晨间观察"},
        ),
        FeedbackRegressionBatch(
            batch_ref="run-scheduler",
            case_version="feedback-v1",
            run_id="run-scheduler",
            scope=scope,
        ),
    )


@pytest.mark.asyncio
async def test_scheduler_claims_and_completes_feedback_batch() -> None:
    worker, batch = _worker()
    jobs = InMemoryFeedbackRegressionJobStore()
    now = datetime(2026, 9, 10, tzinfo=UTC)
    await jobs.enqueue(FeedbackRegressionJob("job-1", batch, now))
    scheduler = FeedbackRegressionScheduler(jobs=jobs, worker=worker, worker_id="worker-a")

    results = await scheduler.run_once(now=now)

    assert results[0].status is FeedbackJobStatus.COMPLETED
    assert results[0].worker_result is not None
    assert (
        await jobs.claim_due(
            worker_id="worker-b", now=now, lease_ttl=timedelta(minutes=1), limit=1
        )
        == ()
    )
    assert (await jobs.get("job-1")).status is FeedbackJobStatus.COMPLETED


@pytest.mark.asyncio
async def test_scheduler_retries_failed_worker_and_lease_expires() -> None:
    worker, batch = _worker()
    jobs = InMemoryFeedbackRegressionJobStore()
    now = datetime(2026, 9, 10, tzinfo=UTC)
    await jobs.enqueue(FeedbackRegressionJob("job-fail", batch, now))

    class FailingWorker:
        async def run_once(self, batch):
            raise RuntimeError("source unavailable")

    scheduler = FeedbackRegressionScheduler(
        jobs=jobs,
        worker=FailingWorker(),
        worker_id="worker-a",
        retry_delay=timedelta(minutes=5),
    )
    results = await scheduler.run_once(now=now)
    assert results[0].status is FeedbackJobStatus.PENDING
    assert results[0].error == "RuntimeError"
    assert (
        await jobs.claim_due(
            worker_id="worker-b", now=now, lease_ttl=timedelta(minutes=1), limit=1
        )
        == ()
    )
    assert (
        await jobs.claim_due(
            worker_id="worker-b",
            now=now + timedelta(minutes=5),
            lease_ttl=timedelta(minutes=1),
            limit=1,
        )
    )[0].lease_owner == "worker-b"


@pytest.mark.asyncio
async def test_scheduler_marks_permanent_failure_after_max_attempts() -> None:
    _, batch = _worker()
    jobs = InMemoryFeedbackRegressionJobStore()
    now = datetime(2026, 9, 10, tzinfo=UTC)
    await jobs.enqueue(FeedbackRegressionJob("job-terminal", batch, now))

    class FailingWorker:
        async def run_once(self, batch):
            raise RuntimeError("permanent")

    scheduler = FeedbackRegressionScheduler(
        jobs=jobs,
        worker=FailingWorker(),
        worker_id="worker-a",
        max_attempts=1,
    )
    result = await scheduler.run_once(now=now)
    assert result[0].status is FeedbackJobStatus.FAILED
    assert (await jobs.get("job-terminal")).status is FeedbackJobStatus.FAILED
    requeued = await jobs.requeue_failed(
        "job-terminal",
        operator_ref="ops-123",
        due_at=now + timedelta(minutes=1),
        now=now,
    )
    assert requeued.status is FeedbackJobStatus.PENDING
    assert requeued.attempts == 0
    assert requeued.last_error == "REQUEUED_BY:ops-123"
    assert requeued.requeued_by == "ops-123"
    assert requeued.requeued_at == now
    with pytest.raises(ValueError, match="NOT_FAILED"):
        await jobs.requeue_failed(
            "job-terminal",
            operator_ref="ops-123",
            due_at=now,
            now=now,
        )


@pytest.mark.asyncio
async def test_sql_job_store_claim_and_takeover_survive_new_session() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(FeedbackSchedulerBase.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        _, batch = _worker()
        store = SqlAlchemyFeedbackRegressionJobStore(sessions)
        now = datetime(2026, 9, 10, tzinfo=UTC)
        await store.enqueue(FeedbackRegressionJob("sql-job", batch, now))
        assert (await store.get("sql-job")).status is FeedbackJobStatus.PENDING
        claimed = await store.claim_due(
            worker_id="worker-a", now=now, lease_ttl=timedelta(minutes=1), limit=1
        )
        assert claimed[0].lease_owner == "worker-a"
        assert (
            await SqlAlchemyFeedbackRegressionJobStore(sessions).claim_due(
                worker_id="worker-b", now=now, lease_ttl=timedelta(minutes=1), limit=1
            )
            == ()
        )
        takeover = await store.claim_due(
            worker_id="worker-b",
            now=now + timedelta(minutes=1),
            lease_ttl=timedelta(minutes=1),
            limit=1,
        )
        assert takeover[0].lease_owner == "worker-b"
        completed = await store.complete(
            "sql-job", worker_id="worker-b", now=now + timedelta(minutes=1)
        )
        assert completed.status is FeedbackJobStatus.COMPLETED

        await store.enqueue(FeedbackRegressionJob("sql-failed", batch, now))
        await store.claim_due(
            worker_id="worker-a", now=now, lease_ttl=timedelta(minutes=1), limit=1
        )
        await store.fail("sql-failed", worker_id="worker-a", error="RuntimeError", now=now)
        restored = await SqlAlchemyFeedbackRegressionJobStore(sessions).requeue_failed(
            "sql-failed",
            operator_ref="ops-sql",
            due_at=now + timedelta(minutes=2),
            now=now + timedelta(minutes=1),
        )
        assert restored.status is FeedbackJobStatus.PENDING
        assert restored.attempts == 0
        assert restored.requeued_by == "ops-sql"
        assert restored.requeued_at == now + timedelta(minutes=1)
    finally:
        await engine.dispose()
