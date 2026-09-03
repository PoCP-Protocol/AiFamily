from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.intelligence.experience.family_problem_understanding_interaction_eval import (
    observe_replayed_revision,
)
from backend.intelligence.experience.run_http import (
    InteractionType,
    RunInteractionEntry,
    RunReplaySnapshot,
    RunScope,
)


def _draft(statement: str) -> dict[str, object]:
    return {"hypotheses": [{"statement": statement}]}


def _replay(run_id: str, draft: dict[str, object], *, feedback: bool) -> RunReplaySnapshot:
    scope = RunScope("tenant-1", "family-1", ("guardian-1",))
    interactions = (
        (
            RunInteractionEntry(
                event_id="event:feedback",
                run_id=run_id,
                scope=scope,
                interaction_type=InteractionType.FEEDBACK,
                idempotency_key="feedback:1",
                sequence=1,
                payload={
                    "feedback_kind": "family_understanding",
                    "feedback_version": "family-understanding-feedback.v2",
                    "feedback_ref": "feedback:1",
                    "adult_actor_ref": "actor:guardian:1",
                    "draft_version": "draft:v1",
                    "candidate_id": "candidate:1",
                    "signal": "helpful",
                    "understood_rating": 4,
                    "response_relevance": 5,
                    "felt_judged": False,
                    "willing_to_continue": True,
                    "correction_needed": True,
                    "correction_ref": "input:correction:1",
                    "correction_resolved": True,
                },
                occurred_at=datetime(2026, 9, 3, 1, 5, tzinfo=UTC),
            ),
        )
        if feedback
        else ()
    )
    return RunReplaySnapshot(
        run_id=run_id,
        scope=scope,
        state="DRAFT",
        status="DRAFT",
        event_sequence=len(interactions),
        interactions=interactions,
        draft_payload=draft,
        artifact_refs=(),
        deletion_state="active",
    )


def _preparation(prior: RunReplaySnapshot):
    request = SimpleNamespace(
        payload={
            "prior_run_id": prior.run_id,
            "prior_draft": prior.draft_payload,
            "reviewed_knowledge": ({"knowledge_ref": "knowledge:reviewed:1"},),
        },
        input_refs=("input:concern", "input:follow-up"),
    )
    spec = SimpleNamespace(
        allowed_knowledge_refs=frozenset({"knowledge:reviewed:1"}),
        allowed_evidence_refs=frozenset({"input:concern", "input:follow-up"}),
    )
    return SimpleNamespace(request=request, eval_spec=spec)


def test_observation_only_uses_replayed_drafts_and_feedback() -> None:
    prior = _replay("run-1", _draft("活动转换可能影响开始。"), feedback=True)
    current = _replay("run-2", _draft("选择顺序可能影响开始。"), feedback=False)
    prepared = _preparation(prior)

    observed = observe_replayed_revision(
        prior_replay=prior,
        preparation=prepared,
        current_replay=current,
    )

    assert observed.prior_hypotheses == ("活动转换可能影响开始。",)
    assert observed.current_hypotheses == ("选择顺序可能影响开始。",)
    assert observed.hypotheses_changed is True
    assert observed.felt_understood_mean == 0.75
    assert observed.response_relevance_mean == 1.0
    assert observed.felt_judged_rate == 0.0
    assert observed.willing_to_continue_rate == 1.0
    assert observed.correction_rate == 1.0
    assert observed.correction_resolution_rate == 1.0
    assert observed.latest_correction_ref == "input:correction:1"
    assert observed.may_mutate_business_state is False


def test_observation_rejects_detached_prior_draft() -> None:
    prior = _replay("run-1", _draft("活动转换可能影响开始。"), feedback=True)
    current = _replay("run-2", _draft("选择顺序可能影响开始。"), feedback=False)
    prepared = _preparation(prior)
    drifted = SimpleNamespace(
        request=SimpleNamespace(
            payload={**prepared.request.payload, "prior_draft": _draft("预设旧假设")},
            input_refs=prepared.request.input_refs,
        ),
        eval_spec=prepared.eval_spec,
    )
    with pytest.raises(ValueError, match="durable replay"):
        observe_replayed_revision(
            prior_replay=prior,
            preparation=drifted,
            current_replay=current,
        )
