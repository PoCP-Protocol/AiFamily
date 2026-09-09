from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.evaluation.feedback_regression import (
    FeedbackRegressionBatch,
    FeedbackRegressionCase,
    FeedbackRegressionWorker,
)
from backend.intelligence.evaluation.feedback_scheduler import (
    FeedbackJobStatus,
    FeedbackRegressionJob,
    FeedbackRegressionScheduler,
    InMemoryFeedbackRegressionJobStore,
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
