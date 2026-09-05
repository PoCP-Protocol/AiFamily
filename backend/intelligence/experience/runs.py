"""Durable, provider-agnostic state machine for a multimodal experience run.

The run is an execution record owned by the AI runtime.  It is deliberately
separate from the Family, Growth, Service, and Commerce domains: a run can
only produce a draft and an audit-friendly execution trace.  Promotion of a
draft into a business decision remains an explicit human-gated action outside
this module.

The in-memory implementation is a small contract seam for the first Web
vertical slice.  Its append-only event list and checkpoint shape are designed
so a database-backed event store can replace it without changing callers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal


class RunContractError(ValueError):
    """Base error for invalid or unsafe run operations."""


class RunConflictError(RunContractError):
    """Raised when an idempotency key is replayed with different content."""


class RunState(StrEnum):
    """Durable lifecycle states exposed to the Web experience client."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunEventType(StrEnum):
    """Events accepted by the state machine."""

    STARTED = "started"
    WAITING = "waiting"
    RESUMED = "resumed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CHECKPOINTED = "checkpointed"


DraftStatus = Literal["DRAFT"]


@dataclass(frozen=True, slots=True)
class RunEvent:
    """One append-only state transition or checkpoint marker.

    ``idempotency_key`` is intentionally caller supplied.  A retry with the
    same key and the same event body is a no-op; reusing it for another body is
    rejected instead of silently changing the run history.
    """

    event_id: str
    run_id: str
    event_type: RunEventType
    target_state: RunState
    payload: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.event_id or not self.run_id:
            raise RunContractError("event_id and run_id are required")
        if not isinstance(self.event_type, RunEventType):
            raise RunContractError("RUN_EVENT_TYPE_UNSUPPORTED")
        if not isinstance(self.target_state, RunState):
            raise RunContractError("RUN_STATE_UNSUPPORTED")
        if self.idempotency_key is not None and not self.idempotency_key:
            raise RunContractError("idempotency_key must not be empty")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class RunCheckpoint:
    """Replay point containing only opaque references and draft data.

    ``draft_payload`` is optional and is always labelled ``DRAFT``.  It is not
    a business fact and cannot be promoted by this runtime.  Media and large
    outputs should be represented by references in ``artifact_refs``.
    """

    checkpoint_id: str
    run_id: str
    event_sequence: int
    state: RunState
    payload: Mapping[str, Any] = field(default_factory=dict)
    artifact_refs: tuple[str, ...] = ()
    draft_payload: Mapping[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: DraftStatus = "DRAFT"

    def __post_init__(self) -> None:
        if not self.checkpoint_id or not self.run_id:
            raise RunContractError("checkpoint_id and run_id are required")
        if self.event_sequence < 0:
            raise RunContractError("event_sequence must not be negative")
        if not isinstance(self.state, RunState):
            raise RunContractError("RUN_STATE_UNSUPPORTED")
        if self.status != "DRAFT":
            raise RunContractError("checkpoint status must remain DRAFT")
        if any(not ref for ref in self.artifact_refs):
            raise RunContractError("artifact_refs must contain non-empty references")
        if len(set(self.artifact_refs)) != len(self.artifact_refs):
            raise RunContractError("artifact_refs must not contain duplicates")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        if self.draft_payload is not None:
            object.__setattr__(self, "draft_payload", MappingProxyType(dict(self.draft_payload)))

    @property
    def may_mutate_business_state(self) -> bool:
        """The runtime never turns a checkpoint into a canonical fact."""

        return False


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    """Immutable read model returned after every accepted event."""

    run_id: str
    tenant_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    request_ref: str
    state: RunState
    version: int
    latest_checkpoint_id: str | None
    status: DraftStatus = "DRAFT"

    @property
    def may_mutate_business_state(self) -> bool:
        return False


_ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.QUEUED: frozenset({RunState.RUNNING, RunState.CANCELLED}),
    RunState.RUNNING: frozenset(
        {RunState.WAITING, RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.WAITING: frozenset({RunState.RUNNING, RunState.FAILED, RunState.CANCELLED}),
    RunState.SUCCEEDED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}


def _event_fingerprint(event: RunEvent) -> str:
    body = {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "event_type": event.event_type.value,
        "target_state": event.target_state.value,
        "payload": event.payload,
        "idempotency_key": event.idempotency_key,
    }
    return json.dumps(body, sort_keys=True, default=str, separators=(",", ":"))


class DurableExperienceRun:
    """Append-only state machine for one multimodal Web experience run.

    The tenant/family/subject scope is an execution-isolation envelope.  It
    does not assert or write any Family/Growth business fact.
    """

    def __init__(
        self,
        *,
        run_id: str,
        tenant_id: str,
        family_id: str,
        subject_ids: tuple[str, ...],
        request_ref: str,
    ) -> None:
        if not run_id or not tenant_id or not family_id or not request_ref:
            raise RunContractError("run_id, tenant_id, family_id and request_ref are required")
        if not subject_ids or any(not subject_id for subject_id in subject_ids):
            raise RunContractError("subject_ids must contain non-empty references")
        if len(set(subject_ids)) != len(subject_ids):
            raise RunContractError("subject_ids must not contain duplicates")
        self._run_id = run_id
        self._tenant_id = tenant_id
        self._family_id = family_id
        self._subject_ids = tuple(subject_ids)
        self._request_ref = request_ref
        self._state = RunState.QUEUED
        self._events: list[RunEvent] = []
        self._event_fingerprints: dict[str, str] = {}
        self._event_ids: dict[str, str] = {}
        self._checkpoints: list[RunCheckpoint] = []
        self._checkpoint_fingerprints: dict[str, str] = {}

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def family_id(self) -> str:
        return self._family_id

    @property
    def subject_ids(self) -> tuple[str, ...]:
        return self._subject_ids

    @property
    def state(self) -> RunState:
        return self._state

    @property
    def version(self) -> int:
        return len(self._events)

    @property
    def events(self) -> tuple[RunEvent, ...]:
        return tuple(self._events)

    @property
    def checkpoints(self) -> tuple[RunCheckpoint, ...]:
        return tuple(self._checkpoints)

    @property
    def latest_checkpoint(self) -> RunCheckpoint | None:
        return self._checkpoints[-1] if self._checkpoints else None

    @property
    def snapshot(self) -> RunSnapshot:
        checkpoint = self.latest_checkpoint
        return RunSnapshot(
            run_id=self._run_id,
            tenant_id=self._tenant_id,
            family_id=self._family_id,
            subject_ids=self._subject_ids,
            request_ref=self._request_ref,
            state=self._state,
            version=self.version,
            latest_checkpoint_id=checkpoint.checkpoint_id if checkpoint else None,
        )

    def append(self, event: RunEvent) -> RunSnapshot:
        """Apply one event within this scope and return its isolated snapshot.

        The scope check prevents cross-run contamination; applying an event
        never writes a business fact and remains draft-only.
        """

        if event.run_id != self._run_id:
            raise RunContractError("RUN_ID_MISMATCH")
        key = event.idempotency_key or event.event_id
        fingerprint = _event_fingerprint(event)
        previous = self._event_fingerprints.get(key)
        if previous is not None:
            if previous != fingerprint:
                raise RunConflictError("IDEMPOTENCY_REPLAY_MISMATCH")
            return self.snapshot
        previous_by_id = self._event_ids.get(event.event_id)
        if previous_by_id is not None:
            if previous_by_id != fingerprint:
                raise RunConflictError("EVENT_REPLAY_MISMATCH")
            return self.snapshot
        if event.event_type is RunEventType.CHECKPOINTED:
            if event.target_state is not self._state:
                raise RunContractError("CHECKPOINT_STATE_MISMATCH")
        elif event.target_state not in _ALLOWED_TRANSITIONS[self._state]:
            raise RunContractError(
                f"INVALID_RUN_TRANSITION:{self._state.value}->{event.target_state.value}"
            )
        self._events.append(event)
        self._event_fingerprints[key] = fingerprint
        self._event_ids[event.event_id] = fingerprint
        self._state = event.target_state
        return self.snapshot

    def transition(
        self,
        target_state: RunState,
        *,
        event_id: str,
        payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> RunSnapshot:
        """Convenience API used by a worker while executing the run."""

        existing_key = idempotency_key or event_id
        existing = next(
            (
                event
                for event in self._events
                if event.idempotency_key == existing_key or event.event_id == event_id
            ),
            None,
        )
        event_type = (
            existing.event_type
            if existing is not None
            else {
                RunState.RUNNING: (
                    RunEventType.STARTED if self._state is RunState.QUEUED else RunEventType.RESUMED
                ),
                RunState.WAITING: RunEventType.WAITING,
                RunState.SUCCEEDED: RunEventType.SUCCEEDED,
                RunState.FAILED: RunEventType.FAILED,
                RunState.CANCELLED: RunEventType.CANCELLED,
            }.get(target_state)
        )
        if event_type is None:
            raise RunContractError("QUEUED cannot be re-entered")
        return self.append(
            RunEvent(
                event_id=event_id,
                run_id=self._run_id,
                event_type=event_type,
                target_state=target_state,
                payload=payload or {},
                idempotency_key=idempotency_key,
            )
        )

    def checkpoint(
        self,
        *,
        checkpoint_id: str,
        payload: Mapping[str, Any] | None = None,
        artifact_refs: tuple[str, ...] = (),
        draft_payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> RunCheckpoint:
        """Persist a replay point and idempotent marker within this scope.

        Checkpoint payloads are execution artifacts only; they cannot mutate a
        Family/Growth fact and any model result remains ``DRAFT``.
        """

        checkpoint = RunCheckpoint(
            checkpoint_id=checkpoint_id,
            run_id=self._run_id,
            event_sequence=self.version,
            state=self._state,
            payload=payload or {},
            artifact_refs=artifact_refs,
            draft_payload=draft_payload,
        )
        key = idempotency_key or checkpoint_id
        fingerprint = _event_fingerprint(
            RunEvent(
                event_id=checkpoint_id,
                run_id=self._run_id,
                event_type=RunEventType.CHECKPOINTED,
                target_state=self._state,
                payload={
                    "payload": checkpoint.payload,
                    "artifact_refs": checkpoint.artifact_refs,
                    "draft_payload": checkpoint.draft_payload,
                },
                idempotency_key=key,
            )
        )
        previous = self._checkpoint_fingerprints.get(key)
        if previous is not None:
            if previous != fingerprint:
                raise RunConflictError("CHECKPOINT_REPLAY_MISMATCH")
            existing = next(
                item for item in self._checkpoints if item.checkpoint_id == checkpoint_id
            )
            return existing
        self.append(
            RunEvent(
                event_id=checkpoint_id,
                run_id=self._run_id,
                event_type=RunEventType.CHECKPOINTED,
                target_state=self._state,
                payload={"checkpoint_id": checkpoint_id},
                idempotency_key=f"checkpoint-event:{key}",
            )
        )
        self._checkpoints.append(checkpoint)
        self._checkpoint_fingerprints[key] = fingerprint
        return checkpoint

    def replay(self) -> RunSnapshot:
        """Return the scoped projection after replaying its append-only log.

        The method is intentionally side-effect free.  It is the contract a
        durable adapter can use to rebuild a read model from persisted events;
        replay remains an execution read and does not write business facts.
        """

        state = RunState.QUEUED
        for event in self._events:
            if event.event_type is not RunEventType.CHECKPOINTED:
                if event.target_state not in _ALLOWED_TRANSITIONS[state]:
                    raise RunContractError("CORRUPT_RUN_EVENT_LOG")
                state = event.target_state
        return RunSnapshot(
            run_id=self._run_id,
            tenant_id=self._tenant_id,
            family_id=self._family_id,
            subject_ids=self._subject_ids,
            request_ref=self._request_ref,
            state=state,
            version=self.version,
            latest_checkpoint_id=self.latest_checkpoint.checkpoint_id
            if self.latest_checkpoint
            else None,
        )


__all__ = [
    "DurableExperienceRun",
    "RunCheckpoint",
    "RunConflictError",
    "RunContractError",
    "RunEvent",
    "RunEventType",
    "RunSnapshot",
    "RunState",
]
