from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.intelligence.experience.family_problem_understanding_interaction_eval import (
    StoredUnderstandingPreparation,
    observe_replayed_revision_from_ledger,
)
from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
    InteractionType,
    RunReplaySnapshot,
    RunScope,
)


def _draft(statement: str) -> dict[str, object]:
    return {"hypotheses": [{"statement": statement}]}


class Repository:
    def __init__(self, record: StoredUnderstandingPreparation) -> None:
        self.record = record

    def get(self, *, scope: RunScope, preparation_ref: str):
        del scope, preparation_ref
        return self.record


def _scope(family: str = "family-1") -> RunScope:
    return RunScope("tenant-1", family, ("guardian-1",))


def _ledger(scope: RunScope | None = None) -> InMemoryExperienceRunLedger:
    selected = scope or _scope()
    ledger = InMemoryExperienceRunLedger()
    ledger.create_draft(
        scope=selected,
        run_id="prior",
        request_ref="request:prior",
        draft_payload=_draft("活动转换可能影响开始。"),
        idempotency_key="create:prior",
    )
    ledger.create_draft(
        scope=selected,
        run_id="current",
        request_ref="request:current",
        draft_payload=_draft("选择顺序可能影响开始。"),
        idempotency_key="create:current",
    )
    return ledger


def _preparation(prior_draft: dict[str, object], **overrides) -> StoredUnderstandingPreparation:
    request = SimpleNamespace(
        run_id="current",
        context_snapshot_ref="context:current",
        payload={
            "prior_run_id": "prior",
            "prior_draft": prior_draft,
            "reviewed_knowledge": ({"knowledge_ref": "knowledge:1"},),
        },
        input_refs=("input:concern", "input:follow-up"),
    )
    preparation = SimpleNamespace(
        request=request,
        eval_spec=SimpleNamespace(
            allowed_knowledge_refs=frozenset({"knowledge:1"}),
            allowed_evidence_refs=frozenset(request.input_refs),
        ),
    )
    values = {
        "preparation_ref": "preparation:current",
        "run_id": "current",
        "prior_run_id": "prior",
        "context_snapshot_ref": "context:current",
        "draft_version": "draft:v1",
        "candidate_id": "candidate:1",
        "expected_response_count": 4,
        "preparation": preparation,
    }
    values.update(overrides)
    return StoredUnderstandingPreparation(**values)


def _append_feedback(
    ledger: InMemoryExperienceRunLedger,
    scope: RunScope,
    actor: str,
    *,
    candidate: str = "candidate:1",
) -> None:
    ledger.append_interaction(
        scope=scope,
        run_id="prior",
        interaction_type=InteractionType.FEEDBACK,
        idempotency_key=f"feedback:{actor}:{candidate}",
        payload={
            "feedback_kind": "family_understanding",
            "feedback_version": "family-understanding-feedback.v2",
            "feedback_ref": f"feedback:{actor}",
            "adult_actor_ref": actor,
            "draft_version": "draft:v1",
            "candidate_id": candidate,
            "signal": "helpful",
            "understood_rating": 4,
            "response_relevance": 5,
            "felt_judged": False,
            "willing_to_continue": True,
            "correction_needed": True,
            "correction_ref": f"input:correction:{actor}",
            "correction_resolved": True,
        },
    )


@pytest.mark.asyncio
async def test_live_replay_filters_exact_candidate_and_hides_sensitive_refs() -> None:
    scope = _scope()
    ledger = _ledger()
    for actor in ("adult-1", "adult-2", "adult-3"):
        _append_feedback(ledger, scope, actor)
    _append_feedback(ledger, scope, "mismatch", candidate="candidate:other")
    prior = ledger.replay(scope=scope, run_id="prior")
    observed = await observe_replayed_revision_from_ledger(
        ledger=ledger,
        preparation_repository=Repository(_preparation(dict(prior.draft_payload))),
        scope=scope,
        prior_run_id="prior",
        current_run_id="current",
        preparation_ref="preparation:current",
    )
    assert observed.response_count == 3
    assert observed.coverage_rate == 0.75
    assert observed.selection_status == "ELIGIBLE"
    assert observed.rating_distribution == ((1, 0), (2, 0), (3, 0), (4, 3), (5, 0))
    assert observed.high_understanding_rate == 1.0
    assert observed.hypotheses_changed is True
    assert "correction_ref" not in observed.as_json()


@pytest.mark.asyncio
async def test_candidate_mismatch_is_not_measured_and_low_sample_hides_means() -> None:
    scope = _scope()
    ledger = _ledger()
    _append_feedback(ledger, scope, "adult-1", candidate="candidate:other")
    prior = ledger.replay(scope=scope, run_id="prior")
    observed = await observe_replayed_revision_from_ledger(
        ledger=ledger,
        preparation_repository=Repository(_preparation(dict(prior.draft_payload))),
        scope=scope,
        prior_run_id="prior",
        current_run_id="current",
        preparation_ref="preparation:current",
    )
    assert observed.selection_status == "NOT_MEASURED"
    assert observed.felt_understood_mean is None


@pytest.mark.asyncio
async def test_stale_active_snapshot_cannot_bypass_delete() -> None:
    scope = _scope()
    ledger = _ledger()
    stale = ledger.replay(scope=scope, run_id="prior")
    ledger.delete(
        scope=scope, run_id="prior", deletion_ref="delete:prior", idempotency_key="delete:prior"
    )
    with pytest.raises(ValueError, match="unavailable"):
        await observe_replayed_revision_from_ledger(
            ledger=ledger,
            preparation_repository=Repository(_preparation(dict(stale.draft_payload))),
            scope=scope,
            prior_run_id="prior",
            current_run_id="current",
            preparation_ref="preparation:current",
        )


@pytest.mark.asyncio
async def test_cross_scope_replay_is_rejected() -> None:
    good_scope = _scope()
    replay = _ledger(good_scope).replay(scope=good_scope, run_id="prior")

    class CrossScopeLedger:
        def replay(self, *, scope: RunScope, run_id: str):
            del scope, run_id
            return replay

    with pytest.raises(ValueError, match="cross-scope"):
        await observe_replayed_revision_from_ledger(
            ledger=CrossScopeLedger(),
            preparation_repository=Repository(_preparation(dict(replay.draft_payload))),
            scope=_scope("family-2"),
            prior_run_id="prior",
            current_run_id="current",
            preparation_ref="preparation:current",
        )


@pytest.mark.asyncio
async def test_fabricated_preparation_lineage_is_rejected() -> None:
    scope = _scope()
    ledger = _ledger()
    prior = ledger.replay(scope=scope, run_id="prior")
    fabricated = _preparation(dict(prior.draft_payload), run_id="other-current")
    with pytest.raises(ValueError, match="lineage"):
        await observe_replayed_revision_from_ledger(
            ledger=ledger,
            preparation_repository=Repository(fabricated),
            scope=scope,
            prior_run_id="prior",
            current_run_id="current",
            preparation_ref="preparation:current",
        )


def test_deleted_restart_snapshot_remains_unavailable() -> None:
    scope = _scope()
    ledger = _ledger()
    ledger.delete(
        scope=scope, run_id="prior", deletion_ref="delete:prior", idempotency_key="delete:prior"
    )
    deleted = ledger.replay(scope=scope, run_id="prior")
    restarted = RunReplaySnapshot(
        run_id=deleted.run_id,
        scope=deleted.scope,
        state=deleted.state,
        status=deleted.status,
        event_sequence=deleted.event_sequence,
        interactions=deleted.interactions,
        draft_payload=None,
        artifact_refs=(),
        deletion_state="deleted",
    )
    assert restarted.draft_payload is None
    assert restarted.deletion_state == "deleted"
