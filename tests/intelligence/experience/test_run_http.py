from __future__ import annotations

import pytest

from backend.intelligence.experience.run_http import (
    InMemoryExperienceRunLedger,
    InteractionType,
    RunHttpConflictError,
    RunHttpError,
    RunScope,
    fingerprint_request,
)
from backend.intelligence.experience.runs import RunState


def _scope(
    *, tenant_id: str = "tenant-1", family_id: str = "family-1", subjects=("child-1",)
) -> RunScope:
    return RunScope(tenant_id=tenant_id, family_id=family_id, subject_ids=tuple(subjects))


def _ledger() -> InMemoryExperienceRunLedger:
    return InMemoryExperienceRunLedger()


def _create(ledger: InMemoryExperienceRunLedger, *, scope: RunScope | None = None):
    return ledger.create_draft(
        scope=scope or _scope(),
        run_id="run-1",
        request_ref="request-1",
        draft_payload={"status": "DRAFT", "headline": "一个可调整的尝试"},
        artifact_refs=("media:sha256:abc",),
        idempotency_key="create-key",
    )


def test_create_draft_records_durable_run_and_draft_checkpoint() -> None:
    snapshot = _create(_ledger())

    assert snapshot.state is RunState.SUCCEEDED
    assert snapshot.status == "DRAFT"
    assert snapshot.draft_payload == {"status": "DRAFT", "headline": "一个可调整的尝试"}
    assert snapshot.artifact_refs == ("media:sha256:abc",)
    assert snapshot.event_sequence == 3
    assert snapshot.may_mutate_business_state is False


def test_create_and_interaction_retries_are_idempotent() -> None:
    ledger = _ledger()
    first = _create(ledger)
    replay = _create(ledger)
    assert replay == first

    receipt = ledger.record_decision(
        scope=_scope(), run_id="run-1", decision="accepted", idempotency_key="decision-1"
    )
    repeated = ledger.record_decision(
        scope=_scope(), run_id="run-1", decision="accepted", idempotency_key="decision-1"
    )
    assert receipt.status == "recorded"
    assert repeated.status == "replayed"
    assert repeated.idempotency_replayed is True
    assert len(ledger.replay(scope=_scope(), run_id="run-1").entries) == 1


def test_preflight_reserves_before_gateway_and_finalize_replays_response() -> None:
    ledger = _ledger()
    fingerprint = fingerprint_request({"prompt_version": "prompt.v1", "payload": {"x": 1}})
    reservation = ledger.preflight_create(
        scope=_scope(),
        run_id="run-preflight-1",
        request_ref="request-preflight-1",
        request_fingerprint=fingerprint,
        idempotency_key="create-preflight-1",
    )
    assert reservation.status == "reserved"

    in_progress = ledger.preflight_create(
        scope=_scope(),
        run_id="run-preflight-1",
        request_ref="request-preflight-1",
        request_fingerprint=fingerprint,
        idempotency_key="create-preflight-1",
    )
    assert in_progress.status == "in_progress"

    snapshot = ledger.finalize_create(
        reservation,
        draft_payload={"status": "DRAFT", "headline": "可回放"},
        response_payload={"run_id": "run-preflight-1", "status": "DRAFT"},
    )
    assert snapshot.status == "DRAFT"
    replay = ledger.preflight_create(
        scope=_scope(),
        run_id="run-preflight-1",
        request_ref="request-preflight-1",
        request_fingerprint=fingerprint,
        idempotency_key="create-preflight-1",
    )
    assert replay.status == "replay"
    assert replay.response_payload == {"run_id": "run-preflight-1", "status": "DRAFT"}


def test_failed_preflight_can_be_released_and_retried_without_stale_run() -> None:
    ledger = _ledger()
    reservation = ledger.preflight_create(
        scope=_scope(),
        run_id="run-preflight-retry",
        request_ref="request-preflight-retry",
        request_fingerprint="fingerprint-v1",
        idempotency_key="create-preflight-retry",
    )
    ledger.release_create(reservation)
    retry = ledger.preflight_create(
        scope=_scope(),
        run_id="run-preflight-retry",
        request_ref="request-preflight-retry",
        request_fingerprint="fingerprint-v1",
        idempotency_key="create-preflight-retry",
    )
    assert retry.status == "reserved"


def test_deleted_run_scrubs_previously_stored_create_response() -> None:
    ledger = _ledger()
    fingerprint = "fingerprint-delete-response"
    reservation = ledger.preflight_create(
        scope=_scope(),
        run_id="run-preflight-delete",
        request_ref="request-preflight-delete",
        request_fingerprint=fingerprint,
        idempotency_key="create-preflight-delete",
    )
    ledger.finalize_create(
        reservation,
        draft_payload={"status": "DRAFT", "headline": "仅供草案"},
        response_payload={"run_id": "run-preflight-delete", "output": {"headline": "仅供草案"}},
    )
    ledger.delete(
        scope=_scope(),
        run_id="run-preflight-delete",
        deletion_ref="delete-preflight-delete",
        idempotency_key="delete-preflight-delete",
    )

    replay = ledger.preflight_create(
        scope=_scope(),
        run_id="run-preflight-delete",
        request_ref="request-preflight-delete",
        request_fingerprint=fingerprint,
        idempotency_key="create-preflight-delete",
    )
    assert replay.status == "replay"
    assert replay.snapshot is not None
    assert replay.snapshot.deletion_state == "deleted"
    assert replay.response_payload is None


def test_preflight_rejects_same_key_with_different_request_before_gateway() -> None:
    ledger = _ledger()
    ledger.preflight_create(
        scope=_scope(),
        run_id="run-preflight-conflict",
        request_ref="request-preflight-conflict",
        request_fingerprint="fingerprint-v1",
        idempotency_key="create-preflight-conflict",
    )
    with pytest.raises(RunHttpConflictError, match="IDEMPOTENCY_REPLAY_MISMATCH"):
        ledger.preflight_create(
            scope=_scope(),
            run_id="run-preflight-conflict",
            request_ref="request-preflight-conflict",
            request_fingerprint="fingerprint-v2",
            idempotency_key="create-preflight-conflict",
        )


def test_idempotency_conflict_and_scope_mismatch_are_rejected() -> None:
    ledger = _ledger()
    _create(ledger)
    with pytest.raises(RunHttpConflictError, match="IDEMPOTENCY_REPLAY_MISMATCH"):
        ledger.create_draft(
            scope=_scope(),
            run_id="run-1",
            request_ref="request-1",
            draft_payload={"status": "DRAFT", "headline": "改写"},
            artifact_refs=("media:sha256:abc",),
            idempotency_key="create-key",
        )
    with pytest.raises(RunHttpError, match="RUN_SCOPE_MISMATCH"):
        ledger.replay(scope=_scope(tenant_id="tenant-2"), run_id="run-1")


def test_decision_feedback_and_human_review_are_append_only_entries() -> None:
    ledger = _ledger()
    _create(ledger)
    decision = ledger.record_decision(
        scope=_scope(), run_id="run-1", decision="rewrite", idempotency_key="decision-1"
    )
    feedback = ledger.record_feedback(
        scope=_scope(),
        run_id="run-1",
        signal="not_helpful",
        idempotency_key="feedback-1",
        payload={"reason": "节奏太快", "draft_version": "draft-1"},
    )
    human = ledger.request_human(
        scope=_scope(), run_id="run-1", reason="需要人工解释", idempotency_key="human-1"
    )

    assert decision.interaction.interaction_type is InteractionType.DECISION
    assert feedback.interaction.interaction_type is InteractionType.FEEDBACK
    assert human.interaction.interaction_type is InteractionType.HUMAN_REVIEW
    entries = ledger.replay(scope=_scope(), run_id="run-1").entries
    assert tuple(entry.sequence for entry in entries) == (4, 5, 6)
    assert entries[-1].payload["status"] == "human_review"


def test_delete_hides_draft_and_artifacts_and_blocks_new_mutations() -> None:
    ledger = _ledger()
    _create(ledger)
    deleted = ledger.delete(
        scope=_scope(), run_id="run-1", deletion_ref="deletion-1", idempotency_key="delete-1"
    )
    snapshot = ledger.replay(scope=_scope(), run_id="run-1")

    assert deleted.status == "deleted"
    assert snapshot.deletion_state == "deleted"
    assert snapshot.draft_payload is None
    assert snapshot.artifact_refs == ()
    with pytest.raises(RunHttpError, match="RUN_DELETED"):
        ledger.record_feedback(
            scope=_scope(),
            run_id="run-1",
            signal="helpful",
            idempotency_key="feedback-after-delete",
        )
    repeated = ledger.delete(
        scope=_scope(), run_id="run-1", deletion_ref="deletion-1", idempotency_key="delete-1"
    )
    assert repeated.status == "replayed"
    assert repeated.idempotency_replayed is True


def test_draft_and_artifact_safety_guards_are_fail_closed() -> None:
    ledger = _ledger()
    with pytest.raises(RunHttpError, match="FORBIDDEN_FACT_OR_RANKING"):
        ledger.create_draft(
            scope=_scope(),
            run_id="run-1",
            request_ref="request-1",
            draft_payload={"family_score": 100},
            idempotency_key="create-key",
        )
    with pytest.raises(RunHttpError, match="DRAFT_STATUS_MUST_REMAIN_DRAFT"):
        ledger.create_draft(
            scope=_scope(),
            run_id="run-2",
            request_ref="request-2",
            draft_payload={"status": "APPROVED"},
            idempotency_key="create-key-2",
        )
    with pytest.raises(RunHttpError, match="ARTIFACT_REFERENCE_INVALID"):
        ledger.create_draft(
            scope=_scope(),
            run_id="run-3",
            request_ref="request-3",
            draft_payload={"status": "DRAFT"},
            artifact_refs=("data:image/png;base64,abc",),
            idempotency_key="create-key-3",
        )


def test_unknown_run_and_invalid_interaction_status_are_rejected() -> None:
    ledger = _ledger()
    with pytest.raises(RunHttpError, match="RUN_NOT_FOUND"):
        ledger.replay(scope=_scope(), run_id="missing")
    _create(ledger)
    with pytest.raises(RunHttpError, match="DECISION_STATUS_UNSUPPORTED"):
        ledger.append_interaction(
            scope=_scope(),
            run_id="run-1",
            interaction_type=InteractionType.DECISION,
            payload={"decision": "approved"},
            idempotency_key="bad-decision",
        )
