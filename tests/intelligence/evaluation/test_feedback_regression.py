from __future__ import annotations

import pytest

from backend.intelligence.evaluation.feedback_regression import (
    ExperienceFeedbackCaseSource,
    FeedbackRegressionBatch,
    FeedbackRegressionCase,
    FeedbackRegressionError,
    FeedbackRegressionWorker,
    evaluate_feedback_regression,
    persist_feedback_regression_report,
)
from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
    RunScope,
)


def _case(**overrides):
    values = {
        "case_ref": "case-1",
        "case_version": "feedback-v1",
        "feedback_ref": "feedback-1",
        "feedback_kind": "GUARDIAN_EDIT",
        "input_contract": {"capability_refs": ["practice:morning"]},
        "expected_output": {"next_step": "记录一次晨间观察"},
        "output_schema": {
            "type": "object",
            "required": ["next_step"],
            "properties": {"next_step": {"type": "string"}},
        },
        "scope_digest": "sha256:opaque-family-scope",
    }
    values.update(overrides)
    return FeedbackRegressionCase(**values)


def test_feedback_regression_is_bounded_and_produces_release_signal() -> None:
    report = evaluate_feedback_regression(
        [_case()],
        lambda case: {"next_step": "记录一次晨间观察"},
        case_version="feedback-v1",
    )

    assert report.total_cases == 1
    assert report.passed_cases == 1
    assert report.release_eligibility == "ELIGIBLE"
    assert report.report_ref.startswith("benchmark:feedback-regression:feedback-v1:")


def test_mismatch_blocks_release_without_exposing_payload() -> None:
    report = evaluate_feedback_regression(
        [_case()],
        lambda case: {"next_step": "不同的草案"},
        case_version="feedback-v1",
    )

    assert report.release_eligibility == "BLOCKED"
    assert report.results[0].passed is False
    assert "不同的草案" not in report.report_ref


def test_forbidden_family_or_minor_fields_fail_closed() -> None:
    with pytest.raises(FeedbackRegressionError, match="forbidden field"):
        _case(input_contract={"family_id": "family-1"})


def test_adapter_failure_is_reported_as_failed_case() -> None:
    report = evaluate_feedback_regression(
        [_case()],
        lambda case: (_ for _ in ()).throw(RuntimeError("adapter unavailable")),
        case_version="feedback-v1",
    )

    assert report.passed_cases == 0
    assert report.results[0].failure_reason.startswith("RuntimeError:")


@pytest.mark.asyncio
async def test_report_projects_to_canonical_experience_ledger_and_replays() -> None:
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope(tenant_id="tenant-1", family_id="family-1", subject_ids=("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id="run-1",
        request_ref="agi:need-1:path-1",
        draft_payload={"family_need_id": "need-1", "status": "DRAFT"},
        idempotency_key="create-1",
    )
    report = evaluate_feedback_regression(
        [_case()], lambda case: {"next_step": "记录一次晨间观察"}, case_version="feedback-v1"
    )

    first = await persist_feedback_regression_report(
        ledger,
        scope=scope,
        run_id="run-1",
        report=report,
        idempotency_key="eval-1",
    )
    repeated = await persist_feedback_regression_report(
        ledger,
        scope=scope,
        run_id="run-1",
        report=report,
        idempotency_key="eval-1",
    )

    assert first.status == "recorded"
    assert repeated.idempotency_replayed is True
    replay = ledger.replay(scope=scope, run_id="run-1")
    evaluation = [item for item in replay.entries if item.interaction_type.value == "evaluation"]
    assert len(evaluation) == 1
    assert evaluation[0].payload["report_ref"] == report.report_ref
    assert evaluation[0].payload["release_eligibility"] == "ELIGIBLE"


@pytest.mark.asyncio
async def test_report_projection_cannot_be_read_from_another_family() -> None:
    ledger = InMemoryExperienceRunLedger()
    owner = RunScope(tenant_id="tenant-1", family_id="family-1", subject_ids=("child-1",))
    other = RunScope(tenant_id="tenant-1", family_id="family-2", subject_ids=("child-2",))
    ledger.create_draft(
        scope=owner,
        run_id="run-1",
        request_ref="agi:need-1:path-1",
        draft_payload={"family_need_id": "need-1", "status": "DRAFT"},
        idempotency_key="create-1",
    )
    report = evaluate_feedback_regression(
        [_case()], lambda case: {"next_step": "记录一次晨间观察"}, case_version="feedback-v1"
    )
    await persist_feedback_regression_report(
        ledger, scope=owner, run_id="run-1", report=report, idempotency_key="eval-1"
    )
    with pytest.raises(Exception, match="SCOPE_MISMATCH"):
        ledger.replay(scope=other, run_id="run-1")


@pytest.mark.asyncio
async def test_worker_loads_deidentified_cases_and_persists_one_bounded_batch() -> None:
    class Source:
        async def load(self, *, case_version: str, batch_ref: str):
            assert case_version == "feedback-v1"
            assert batch_ref == "batch-1"
            return (_case(),)

    ledger = InMemoryExperienceRunLedger()
    scope = RunScope(tenant_id="tenant-1", family_id="family-1", subject_ids=("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id="run-worker-1",
        request_ref="agi:need-1:path-1",
        draft_payload={"family_need_id": "need-1", "status": "DRAFT"},
        idempotency_key="create-worker-1",
    )
    worker = FeedbackRegressionWorker(
        case_source=Source(),
        ledger=ledger,
        adapter=lambda case: {"next_step": "记录一次晨间观察"},
    )
    result = await worker.run_once(
        FeedbackRegressionBatch(
            batch_ref="batch-1",
            case_version="feedback-v1",
            run_id="run-worker-1",
            scope=scope,
        )
    )

    assert result.report.release_eligibility == "ELIGIBLE"
    assert result.ledger_receipt.status == "recorded"


@pytest.mark.asyncio
async def test_worker_rejects_empty_or_mixed_version_batch() -> None:
    class EmptySource:
        async def load(self, **kwargs):
            return ()

    worker = FeedbackRegressionWorker(
        case_source=EmptySource(),
        ledger=InMemoryExperienceRunLedger(),
        adapter=lambda case: {},
    )
    batch = FeedbackRegressionBatch(
        batch_ref="empty",
        case_version="feedback-v1",
        run_id="run-empty",
        scope=object(),
    )
    with pytest.raises(FeedbackRegressionError, match="empty"):
        await worker.run_once(batch)


@pytest.mark.asyncio
async def test_experience_source_reads_only_explicit_feedback_contracts() -> None:
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope(tenant_id="tenant-1", family_id="family-1", subject_ids=("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id="run-source-1",
        request_ref="agi:need-1:path-1",
        draft_payload={"family_need_id": "need-1", "status": "DRAFT"},
        idempotency_key="create-source-1",
    )
    ledger.record_feedback(
        scope=scope,
        run_id="run-source-1",
        signal="not_helpful",
        idempotency_key="feedback-source-1",
        payload={
            "feedback_ref": "feedback-source-1",
            "regression_case": {
                "case_ref": "case-source-1",
                "case_version": "feedback-v1",
                "feedback_kind": "GUARDIAN_EDIT",
                "input_contract": {"capability_refs": ["practice:morning"]},
                "expected_output": {"next_step": "记录一次晨间观察"},
                "output_schema": {
                    "type": "object",
                    "required": ["next_step"],
                    "properties": {"next_step": {"type": "string"}},
                },
                "scope_digest": "sha256:opaque-source-scope",
            },
        },
    )
    source = ExperienceFeedbackCaseSource(ledger=ledger, scope=scope)
    cases = await source.load(case_version="feedback-v1", batch_ref="run-source-1")
    assert len(cases) == 1
    assert cases[0].feedback_ref == "feedback-source-1"


@pytest.mark.asyncio
async def test_experience_source_rejects_version_drift() -> None:
    ledger = InMemoryExperienceRunLedger()
    scope = RunScope(tenant_id="tenant-1", family_id="family-1", subject_ids=("child-1",))
    ledger.create_draft(
        scope=scope,
        run_id="run-source-drift",
        request_ref="agi:need-1:path-1",
        draft_payload={"family_need_id": "need-1", "status": "DRAFT"},
        idempotency_key="create-source-drift",
    )
    ledger.record_feedback(
        scope=scope,
        run_id="run-source-drift",
        signal="helpful",
        idempotency_key="feedback-source-drift",
        payload={
            "regression_case": {
                "case_ref": "case-drift",
                "case_version": "old-version",
                "feedback_kind": "GUARDIAN_ACCEPT",
                "input_contract": {"x": 1},
                "expected_output": {"next_step": "x"},
                "output_schema": {"type": "object"},
                "scope_digest": "sha256:opaque-drift-scope",
            }
        },
    )
    with pytest.raises(FeedbackRegressionError, match="version mismatch"):
        await ExperienceFeedbackCaseSource(ledger=ledger, scope=scope).load(
            case_version="feedback-v1", batch_ref="run-source-drift"
        )
