from __future__ import annotations

import pytest

from backend.intelligence.experience.runs import (
    DurableExperienceRun,
    RunConflictError,
    RunContractError,
    RunEvent,
    RunEventType,
    RunState,
)


def _run() -> DurableExperienceRun:
    return DurableExperienceRun(
        run_id="run-001",
        tenant_id="tenant-001",
        family_id="family-001",
        subject_ids=("subject-001",),
        request_ref="request-001",
    )


def test_run_progresses_through_waiting_checkpoint_and_success() -> None:
    run = _run()

    assert run.state is RunState.QUEUED
    assert run.snapshot.family_id == "family-001"
    assert run.snapshot.subject_ids == ("subject-001",)
    assert run.transition(RunState.RUNNING, event_id="started").state is RunState.RUNNING
    assert run.transition(RunState.WAITING, event_id="waiting").state is RunState.WAITING
    checkpoint = run.checkpoint(
        checkpoint_id="cp-001",
        payload={"step": "drafted"},
        artifact_refs=("asset://image-001",),
        draft_payload={"title": "沟通练习"},
    )
    assert checkpoint.state is RunState.WAITING
    assert checkpoint.status == "DRAFT"
    assert checkpoint.may_mutate_business_state is False

    assert run.transition(RunState.RUNNING, event_id="resumed").state is RunState.RUNNING
    snapshot = run.transition(RunState.SUCCEEDED, event_id="succeeded")
    assert snapshot.state is RunState.SUCCEEDED
    assert snapshot.latest_checkpoint_id == "cp-001"
    assert snapshot.may_mutate_business_state is False
    assert run.replay() == snapshot


def test_event_retry_is_idempotent_and_conflicting_replay_is_rejected() -> None:
    run = _run()
    first = run.append(
        RunEvent(
            event_id="start-event",
            run_id=run.run_id,
            event_type=RunEventType.STARTED,
            target_state=RunState.RUNNING,
            payload={"worker": "web-experience"},
            idempotency_key="attempt-1",
        )
    )
    assert (
        run.append(
            RunEvent(
                event_id="start-event",
                run_id=run.run_id,
                event_type=RunEventType.STARTED,
                target_state=RunState.RUNNING,
                payload={"worker": "web-experience"},
                idempotency_key="attempt-1",
            )
        )
        == first
    )

    with pytest.raises(RunConflictError, match="IDEMPOTENCY_REPLAY_MISMATCH"):
        run.append(
            RunEvent(
                event_id="start-event",
                run_id=run.run_id,
                event_type=RunEventType.STARTED,
                target_state=RunState.RUNNING,
                payload={"worker": "different"},
                idempotency_key="attempt-1",
            )
        )

    # The convenience API preserves STARTED vs RESUMED on a retry after the
    # state has already advanced.
    assert (
        run.transition(
            RunState.RUNNING,
            event_id="start-event",
            payload={"worker": "web-experience"},
            idempotency_key="attempt-1",
        )
        == first
    )


def test_invalid_transition_and_cross_run_event_are_rejected() -> None:
    run = _run()
    with pytest.raises(RunContractError, match="INVALID_RUN_TRANSITION"):
        run.transition(RunState.SUCCEEDED, event_id="too-early")

    with pytest.raises(RunContractError, match="RUN_ID_MISMATCH"):
        run.append(
            RunEvent(
                event_id="other-run-event",
                run_id="run-999",
                event_type=RunEventType.STARTED,
                target_state=RunState.RUNNING,
            )
        )


def test_checkpoint_retry_is_idempotent_and_conflict_is_rejected() -> None:
    run = _run()
    run.transition(RunState.RUNNING, event_id="started")
    first = run.checkpoint(
        checkpoint_id="cp-001",
        payload={"cursor": 1},
        draft_payload={"recommendation": "DRAFT"},
    )
    assert (
        run.checkpoint(
            checkpoint_id="cp-001",
            payload={"cursor": 1},
            draft_payload={"recommendation": "DRAFT"},
        )
        == first
    )
    assert run.version == 2  # started + checkpoint marker

    with pytest.raises(RunConflictError, match="CHECKPOINT_REPLAY_MISMATCH"):
        run.checkpoint(
            checkpoint_id="cp-001",
            payload={"cursor": 2},
            draft_payload={"recommendation": "DRAFT"},
        )


def test_terminal_states_cannot_be_reentered() -> None:
    run = _run()
    run.transition(RunState.RUNNING, event_id="started")
    run.transition(RunState.CANCELLED, event_id="cancelled")
    with pytest.raises(RunContractError, match="INVALID_RUN_TRANSITION"):
        run.transition(RunState.RUNNING, event_id="retry")


def test_run_scope_requires_family_and_unique_subjects() -> None:
    with pytest.raises(RunContractError, match="family_id"):
        DurableExperienceRun(
            run_id="run-002",
            tenant_id="tenant-001",
            family_id="",
            subject_ids=("subject-001",),
            request_ref="request-002",
        )
    with pytest.raises(RunContractError, match="subject_ids must not contain duplicates"):
        DurableExperienceRun(
            run_id="run-003",
            tenant_id="tenant-001",
            family_id="family-001",
            subject_ids=("subject-001", "subject-001"),
            request_ref="request-003",
        )
