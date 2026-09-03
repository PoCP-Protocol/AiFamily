import pytest

from backend.intelligence.experience.family_problem_understanding_eval import (
    FamilyUnderstandingEvalSpec,
)
from backend.intelligence.experience.family_problem_understanding_feedback import (
    FamilyUnderstandingFeedback,
    apply_parent_feedback_to_eval_spec,
    project_family_understanding_feedback,
    record_family_understanding_feedback,
)
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger, RunScope


def _scope() -> RunScope:
    return RunScope("tenant:1", "family:1", ("guardian:1", "child:1"))


def _ledger() -> InMemoryExperienceRunLedger:
    ledger = InMemoryExperienceRunLedger()
    ledger.create_draft(
        scope=_scope(),
        run_id="run:understanding",
        request_ref="request:understanding",
        draft_payload={"draft": "generated understanding"},
        idempotency_key="create:understanding",
    )
    return ledger


def _feedback(**overrides) -> FamilyUnderstandingFeedback:
    values = {
        "feedback_ref": "feedback:1",
        "adult_actor_ref": "actor:guardian:1",
        "draft_version": "draft:v1",
        "candidate_id": "candidate:1",
        "understood_rating": 4,
        "response_relevance": 5,
        "felt_judged": False,
        "willing_to_continue": True,
        "correction_needed": True,
        "correction_ref": "input:correction:1",
        "reason_code": "MISSED_CONTEXT",
    }
    values.update(overrides)
    return FamilyUnderstandingFeedback(**values)


@pytest.mark.asyncio
async def test_records_and_projects_bounded_parent_feedback() -> None:
    ledger = _ledger()
    receipt = await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="helpful",
        feedback=_feedback(),
        idempotency_key="feedback:understanding:1",
    )
    projection = project_family_understanding_feedback(
        ledger.replay(scope=_scope(), run_id="run:understanding"),
        expected_response_count=2,
    )

    assert "reason" not in receipt.interaction.payload
    assert projection.status == "MEASURED"
    assert projection.response_count == 1
    assert projection.coverage_rate == 0.5
    assert projection.rating_distribution == ((1, 0), (2, 0), (3, 0), (4, 1), (5, 0))
    assert projection.felt_understood_mean == 0.75
    assert projection.high_understanding_rate == 1.0
    assert projection.low_understanding_rate == 0.0
    assert projection.response_relevance_mean == 1.0
    assert projection.latest_correction_ref == "input:correction:1"

    spec = FamilyUnderstandingEvalSpec(
        allowed_evidence_refs=frozenset({"input:concern"}),
        allowed_knowledge_refs=frozenset(),
    )
    assert apply_parent_feedback_to_eval_spec(spec, projection).parent_felt_understood is None


@pytest.mark.asyncio
async def test_feedback_only_enters_eval_after_minimum_count_and_coverage() -> None:
    ledger = _ledger()
    await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="helpful",
        feedback=_feedback(correction_needed=False, correction_ref=None),
        idempotency_key="feedback:eligible:1",
    )
    await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="not_helpful",
        feedback=_feedback(
            feedback_ref="feedback:eligible:2",
            adult_actor_ref="actor:guardian:2",
            understood_rating=2,
            correction_needed=False,
            correction_ref=None,
        ),
        idempotency_key="feedback:eligible:2",
    )
    projection = project_family_understanding_feedback(
        ledger.replay(scope=_scope(), run_id="run:understanding"),
        expected_response_count=2,
    )
    spec = FamilyUnderstandingEvalSpec(
        allowed_evidence_refs=frozenset({"input:concern"}),
        allowed_knowledge_refs=frozenset(),
    )

    assert apply_parent_feedback_to_eval_spec(spec, projection).parent_felt_understood == 0.5


@pytest.mark.asyncio
async def test_update_must_supersede_latest_feedback_and_projection_deduplicates() -> None:
    ledger = _ledger()
    await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="not_helpful",
        feedback=_feedback(understood_rating=2, response_relevance=2),
        idempotency_key="feedback:1",
    )
    with pytest.raises(ValueError, match="must supersede"):
        await record_family_understanding_feedback(
            ledger,
            scope=_scope(),
            run_id="run:understanding",
            signal="helpful",
            feedback=_feedback(feedback_ref="feedback:2", understood_rating=5),
            idempotency_key="feedback:2-invalid",
        )
    await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="helpful",
        feedback=_feedback(
            feedback_ref="feedback:2",
            understood_rating=5,
            response_relevance=5,
            correction_resolved=True,
            supersedes_feedback_ref="feedback:1",
        ),
        idempotency_key="feedback:2",
    )
    projection = project_family_understanding_feedback(
        ledger.replay(scope=_scope(), run_id="run:understanding")
    )

    assert projection.response_count == 1
    assert projection.rating_distribution[-1] == (5, 1)
    assert projection.correction_resolution_rate == 1.0


@pytest.mark.asyncio
async def test_distinct_adults_are_aggregated_without_hiding_distribution() -> None:
    ledger = _ledger()
    await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="helpful",
        feedback=_feedback(correction_needed=False, correction_ref=None),
        idempotency_key="feedback:1",
    )
    await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="not_helpful",
        feedback=_feedback(
            feedback_ref="feedback:adult-2",
            adult_actor_ref="actor:guardian:2",
            understood_rating=1,
            response_relevance=2,
            felt_judged=True,
            willing_to_continue=False,
            correction_ref="input:correction:adult-2",
        ),
        idempotency_key="feedback:adult-2",
    )
    projection = project_family_understanding_feedback(
        ledger.replay(scope=_scope(), run_id="run:understanding")
    )

    assert projection.response_count == 2
    assert projection.rating_distribution == ((1, 1), (2, 0), (3, 0), (4, 1), (5, 0))
    assert projection.high_understanding_rate == 0.5
    assert projection.low_understanding_rate == 0.5
    assert projection.felt_judged_rate == 0.5


def test_deleted_run_feedback_projection_is_unavailable() -> None:
    ledger = _ledger()
    ledger.delete(
        scope=_scope(),
        run_id="run:understanding",
        deletion_ref="deletion:1",
        idempotency_key="delete:1",
    )
    projection = project_family_understanding_feedback(
        ledger.replay(scope=_scope(), run_id="run:understanding")
    )
    assert ledger.replay(scope=_scope(), run_id="run:understanding").interactions == ()
    assert projection.status == "DELETED"
    assert projection.response_count == 0
    assert projection.latest_correction_ref is None


def test_invalid_free_text_or_unscoped_refs_are_rejected() -> None:
    with pytest.raises(ValueError, match="understood_rating"):
        _feedback(understood_rating=0)
    with pytest.raises(ValueError, match="correction_ref"):
        _feedback(correction_ref="raw correction text")
    with pytest.raises(ValueError, match="OTHER"):
        _feedback(reason_code="OTHER")
