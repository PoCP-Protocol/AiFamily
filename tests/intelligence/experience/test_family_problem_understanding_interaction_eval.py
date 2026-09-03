from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.intelligence.experience.family_problem_understanding_eval import (
    FamilyUnderstandingEvalSpec,
)
from backend.intelligence.experience.family_problem_understanding_feedback import (
    DEFAULT_FEEDBACK_EVAL_POLICY,
)
from backend.intelligence.experience.family_problem_understanding_interaction_eval import (
    CanonicalUnderstandingPreparationRepositoryAdapter,
    FamilyUnderstandingRevisionObserver,
    StoredUnderstandingPreparation,
    observe_replayed_revision_from_ledger,
)
from backend.intelligence.experience.family_problem_understanding_knowledge import (
    FamilyUnderstandingKnowledgeSelection,
    KnowledgeRetrievalTrace,
)
from backend.intelligence.experience.family_problem_understanding_preparation import (
    FamilyProblemUnderstandingPreparation,
)
from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
    InteractionType,
    RunHttpError,
    RunReplaySnapshot,
    RunScope,
)
from backend.intelligence.experience.sql_run_ledger import (
    SessionPerCallExperienceRunLedger,
)
from backend.intelligence.model_gateway.contracts import StructuredRequest

pytest_plugins = ("tests.intelligence.experience.test_multimodal_postgres_http_lifecycle",)


def _draft(statement: str) -> dict[str, object]:
    return {"hypotheses": [{"statement": statement}]}


class RecordStore:
    def __init__(self, record: StoredUnderstandingPreparation) -> None:
        self.record = record

    def load(self, *, scope_key, run_id: str, preparation_ref: str):
        del scope_key, run_id, preparation_ref
        return self.record


def _repository(record: StoredUnderstandingPreparation):
    return CanonicalUnderstandingPreparationRepositoryAdapter(RecordStore(record))


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
    request = StructuredRequest(
        use_case="family-understanding-multimodal",
        prompt_version="family-understanding.v1",
        schema_version="family-understanding-output.v2",
        data_class="SYNTHETIC",
        context_snapshot_ref="context:current",
        payload={
            "prior_run_id": "prior",
            "prior_draft": prior_draft,
            "reviewed_knowledge": ({"knowledge_ref": "knowledge:1"},),
        },
        output_schema={"type": "object"},
        input_refs=("input:concern", "input:follow-up"),
        request_id="current",
    )
    preparation = FamilyProblemUnderstandingPreparation(
        request=request,
        knowledge_selection=FamilyUnderstandingKnowledgeSelection(
            excerpts=(),
            trace=KnowledgeRetrievalTrace(
                purpose="family_problem_understanding",
                scope="family_growth",
                candidate_count=0,
                selected_claim_ids=("knowledge:1",),
                rejected_claim_ids=(),
                relevance_scores=(),
            ),
        ),
        eval_spec=FamilyUnderstandingEvalSpec(
            allowed_knowledge_refs=frozenset({"knowledge:1"}),
            allowed_evidence_refs=frozenset(request.input_refs),
        ),
    )
    values = {
        "preparation_ref": "preparation:current",
        "scope_key": _scope().key,
        "run_id": "current",
        "prior_run_id": "prior",
        "request_ref": "current",
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
    version: str = "family-understanding-feedback.v2",
) -> None:
    ledger.append_interaction(
        scope=scope,
        run_id="prior",
        interaction_type=InteractionType.FEEDBACK,
        idempotency_key=f"feedback:{actor}:{candidate}",
        payload={
            "feedback_kind": "family_understanding",
            "feedback_version": version,
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
    for index in range(10):
        actor = f"adult-{index}"
        _append_feedback(ledger, scope, actor)
    _append_feedback(ledger, scope, "mismatch", candidate="candidate:other")
    prior = ledger.replay(scope=scope, run_id="prior")
    observer = FamilyUnderstandingRevisionObserver(
        ledger,
        _repository(_preparation(dict(prior.draft_payload), expected_response_count=10)),
    )
    observed = await observer.observe(
        scope=scope,
        prior_run_id="prior",
        current_run_id="current",
        preparation_ref="preparation:current",
    )
    assert observed.response_count == 10
    assert observed.coverage_rate == 1.0
    assert observed.feedback_evidence_status == "DESCRIPTIVE_READY"
    assert observed.policy_version == DEFAULT_FEEDBACK_EVAL_POLICY.policy_version
    assert observed.rating_distribution == ((1, 0), (2, 0), (3, 0), (4, 10), (5, 0))
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
        preparation_repository=_repository(_preparation(dict(prior.draft_payload))),
        scope=scope,
        prior_run_id="prior",
        current_run_id="current",
        preparation_ref="preparation:current",
    )
    assert observed.feedback_evidence_status == "NOT_MEASURED"
    assert observed.felt_understood_mean is None


def test_feedback_v1_is_rejected_before_observation() -> None:
    with pytest.raises(RunHttpError, match="FEEDBACK_VERSION_INVALID"):
        _append_feedback(
            _ledger(),
            _scope(),
            "adult-old-version",
            version="family-understanding-feedback.v1",
        )


@pytest.mark.asyncio
async def test_arm_imbalance_uses_shared_policy_and_never_implies_selection() -> None:
    scope = _scope()
    ledger = _ledger()
    for index in range(10):
        _append_feedback(ledger, scope, f"adult-{index}")
    prior = ledger.replay(scope=scope, run_id="prior")
    observed = await observe_replayed_revision_from_ledger(
        ledger=ledger,
        preparation_repository=_repository(
            _preparation(dict(prior.draft_payload), expected_response_count=10)
        ),
        scope=scope,
        prior_run_id="prior",
        current_run_id="current",
        preparation_ref="preparation:current",
        response_count_by_arm={"a": 10, "b": 5},
        expected_response_count_by_arm={"a": 10, "b": 10},
    )
    assert observed.feedback_evidence_status == "ARM_IMBALANCED"
    assert observed.arm_coverage_gap == 0.5
    assert observed.felt_understood_mean is None
    assert "selection-eligible" not in observed.selection_bias


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
            preparation_repository=_repository(_preparation(dict(stale.draft_payload))),
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
            preparation_repository=_repository(_preparation(dict(replay.draft_payload))),
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
            preparation_repository=_repository(fabricated),
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


@pytest.mark.asyncio
async def test_postgres_delete_restart_observer_cannot_read_prior_draft(
    migrated_database_url: str,
) -> None:
    scope = RunScope("tenant-pg-observer", "family-pg-observer", ("guardian-pg",))
    engine = create_async_engine(migrated_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ledger = SessionPerCallExperienceRunLedger(factory)
    await ledger.create_draft(
        scope=scope,
        run_id="prior-pg-observer",
        request_ref="request:prior-pg-observer",
        draft_payload=_draft("活动转换可能影响开始。"),
        idempotency_key="create:prior-pg-observer",
    )
    await ledger.create_draft(
        scope=scope,
        run_id="current-pg-observer",
        request_ref="request:current-pg-observer",
        draft_payload=_draft("选择顺序可能影响开始。"),
        idempotency_key="create:current-pg-observer",
    )
    prior = await ledger.replay(scope=scope, run_id="prior-pg-observer")
    await ledger.append_interaction(
        scope=scope,
        run_id="prior-pg-observer",
        interaction_type=InteractionType.DELETE,
        payload={"deletion_ref": "delete:prior-pg-observer", "status": "deleted"},
        idempotency_key="delete:prior-pg-observer",
    )
    await engine.dispose()

    restarted_engine = create_async_engine(migrated_database_url)
    restarted = SessionPerCallExperienceRunLedger(
        async_sessionmaker(restarted_engine, expire_on_commit=False)
    )
    record = _preparation(
        dict(prior.draft_payload),
        scope_key=scope.key,
        run_id="current-pg-observer",
        prior_run_id="prior-pg-observer",
        request_ref="current-pg-observer",
    )
    request = record.preparation.request
    object.__setattr__(request, "request_id", "current-pg-observer")
    request.payload["prior_run_id"] = "prior-pg-observer"
    with pytest.raises(ValueError, match="unavailable"):
        await observe_replayed_revision_from_ledger(
            ledger=restarted,
            preparation_repository=_repository(record),
            scope=scope,
            prior_run_id="prior-pg-observer",
            current_run_id="current-pg-observer",
            preparation_ref="preparation:current",
        )
    await restarted_engine.dispose()
