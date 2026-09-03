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


@pytest.mark.asyncio
async def test_records_and_projects_parent_understanding_feedback() -> None:
    ledger = _ledger()
    receipt = await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="helpful",
        feedback=FamilyUnderstandingFeedback(
            4,
            False,
            True,
            True,
            "input:correction:1",
            "基本理解了，但遗漏了孩子自己选择时更顺利。",
        ),
        idempotency_key="feedback:understanding:1",
    )
    projection = project_family_understanding_feedback(
        ledger.replay(scope=_scope(), run_id="run:understanding")
    )

    assert receipt.interaction.payload["understood_rating"] == 4
    assert projection.status == "MEASURED"
    assert projection.response_count == 1
    assert projection.felt_understood_mean == 0.75
    assert projection.felt_judged_rate == 0.0
    assert projection.willing_to_continue_rate == 1.0
    assert projection.correction_rate == 1.0
    assert projection.latest_correction_ref == "input:correction:1"
    spec = FamilyUnderstandingEvalSpec(
        allowed_evidence_refs=frozenset({"input:concern"}),
        allowed_knowledge_refs=frozenset(),
    )
    assert apply_parent_feedback_to_eval_spec(spec, projection).parent_felt_understood == 0.75


@pytest.mark.asyncio
async def test_feedback_is_idempotent_and_aggregates() -> None:
    ledger = _ledger()
    first = FamilyUnderstandingFeedback(5, False, True, False)
    second = FamilyUnderstandingFeedback(2, True, False, True, "input:correction:2")
    await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="helpful",
        feedback=first,
        idempotency_key="feedback:1",
    )
    replayed = await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="helpful",
        feedback=first,
        idempotency_key="feedback:1",
    )
    await record_family_understanding_feedback(
        ledger,
        scope=_scope(),
        run_id="run:understanding",
        signal="not_helpful",
        feedback=second,
        idempotency_key="feedback:2",
    )
    projection = project_family_understanding_feedback(
        ledger.replay(scope=_scope(), run_id="run:understanding")
    )

    assert replayed.idempotency_replayed is True
    assert projection.response_count == 2
    assert projection.felt_understood_mean == 0.625
    assert projection.felt_judged_rate == 0.5
    assert projection.willing_to_continue_rate == 0.5


def test_projection_updates_the_eval_spec() -> None:
    spec = FamilyUnderstandingEvalSpec(
        allowed_evidence_refs=frozenset({"input:concern"}),
        allowed_knowledge_refs=frozenset(),
    )
    projection = project_family_understanding_feedback(
        _ledger().replay(scope=_scope(), run_id="run:understanding")
    )
    assert apply_parent_feedback_to_eval_spec(spec, projection).parent_felt_understood is None


def test_invalid_feedback_is_rejected() -> None:
    with pytest.raises(ValueError, match="understood_rating"):
        FamilyUnderstandingFeedback(0, False, True, False)
    with pytest.raises(ValueError, match="correction_ref"):
        FamilyUnderstandingFeedback(4, False, True, True)
