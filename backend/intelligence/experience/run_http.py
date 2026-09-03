"""Provider-neutral HTTP-facing ledger for one Web experience run.

The ledger is an application seam for the future HTTP routes.  It owns no
domain repository and never calls a model gateway.  A generated result is
stored only as a ``DRAFT`` checkpoint; user decisions, feedback, human review,
and deletion are append-only interaction entries on the same run.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal, Protocol

from backend.intelligence.experience.runs import (
    DurableExperienceRun,
    RunCheckpoint,
    RunConflictError,
    RunContractError,
    RunState,
)


class RunHttpError(ValueError):
    """Base error for an invalid, unauthorized, or unavailable run."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class RunHttpConflictError(RunHttpError):
    """Raised when an idempotency key is reused with a different payload."""


class InteractionType(StrEnum):
    DECISION = "decision"
    FEEDBACK = "feedback"
    HUMAN_REVIEW = "human_review"
    DELETE = "delete"
    EVALUATION = "evaluation"


DecisionStatus = Literal["pending_human_confirmation", "accepted", "rewrite", "rejected"]
FeedbackStatus = Literal["recorded", "replayed"]
DeletionState = Literal["active", "deleted"]
DraftPreflightStatus = Literal["reserved", "replay", "in_progress"]


@dataclass(frozen=True, slots=True)
class RunScope:
    """Tenant/family/subject isolation envelope required on every mutation/read."""

    tenant_id: str
    family_id: str
    subject_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.family_id:
            raise RunHttpError("SCOPE_REQUIRED")
        if not self.subject_ids or any(not item for item in self.subject_ids):
            raise RunHttpError("SUBJECT_SCOPE_REQUIRED")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise RunHttpError("SUBJECT_SCOPE_MUST_BE_UNIQUE")

    @property
    def key(self) -> tuple[str, str, tuple[str, ...]]:
        return self.tenant_id, self.family_id, tuple(sorted(self.subject_ids))


@dataclass(frozen=True, slots=True)
class RunInteractionEntry:
    """Append-only user interaction bound to one run and exact scope."""

    event_id: str
    run_id: str
    scope: RunScope
    interaction_type: InteractionType
    payload: Mapping[str, Any]
    idempotency_key: str
    sequence: int
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.event_id or not self.run_id or not self.idempotency_key:
            raise RunHttpError("INTERACTION_ID_REQUIRED")
        if not isinstance(self.interaction_type, InteractionType):
            raise RunHttpError("INTERACTION_TYPE_UNSUPPORTED")
        if self.sequence <= 0:
            raise RunHttpError("INTERACTION_SEQUENCE_INVALID")
        _assert_safe_mapping(self.payload)
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class InteractionReceipt:
    """Mutation result suitable for a future HTTP response."""

    run_id: str
    interaction: RunInteractionEntry
    status: Literal["recorded", "replayed", "deleted"]
    idempotency_replayed: bool = False


@dataclass(frozen=True, slots=True)
class RunReplaySnapshot:
    """Read-only projection; deleted runs intentionally omit draft/artifacts."""

    run_id: str
    scope: RunScope
    state: RunState
    status: Literal["DRAFT"]
    event_sequence: int
    interactions: tuple[RunInteractionEntry, ...]
    draft_payload: Mapping[str, Any] | None
    artifact_refs: tuple[str, ...]
    deletion_state: DeletionState

    def __post_init__(self) -> None:
        if self.status != "DRAFT":
            raise RunHttpError("RUN_STATUS_MUST_REMAIN_DRAFT")
        if self.event_sequence < 0:
            raise RunHttpError("RUN_EVENT_SEQUENCE_INVALID")
        if self.deletion_state == "deleted" and (
            self.draft_payload is not None or self.artifact_refs
        ):
            raise RunHttpError("DELETED_REPLAY_MUST_NOT_EXPOSE_DRAFT")
        if self.draft_payload is not None:
            _assert_draft_payload(self.draft_payload)
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))

    @property
    def entries(self) -> tuple[RunInteractionEntry, ...]:
        """Alias used by the Web replay contract."""

        return self.interactions

    @property
    def may_mutate_business_state(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class DraftPreflight:
    """Gateway admission result for a draft create request.

    ``reserved`` is the only state that may proceed to model invocation.  A
    replay carries the previously materialized HTTP response so callers can
    return it without invoking a provider again.  ``in_progress`` is returned
    to a concurrent caller for the same run and is deliberately not a second
    reservation.
    """

    scope: RunScope
    run_id: str
    request_ref: str
    request_fingerprint: str
    idempotency_key: str
    status: DraftPreflightStatus
    snapshot: RunReplaySnapshot | None = None
    response_payload: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status == "replay" and self.snapshot is None:
            raise RunHttpError("DRAFT_REPLAY_SNAPSHOT_REQUIRED")
        if self.status == "reserved" and self.snapshot is not None:
            raise RunHttpError("DRAFT_RESERVATION_SNAPSHOT_INVALID")
        if self.response_payload is not None:
            _assert_safe_mapping(self.response_payload)
            object.__setattr__(
                self, "response_payload", MappingProxyType(dict(self.response_payload))
            )


class ExperienceRunLedger(Protocol):
    """Port implemented by in-memory or durable AI-runtime ledgers."""

    def preflight_create(
        self,
        *,
        scope: RunScope,
        run_id: str,
        request_ref: str,
        request_fingerprint: str,
        idempotency_key: str,
    ) -> DraftPreflight: ...

    def finalize_create(
        self,
        reservation: DraftPreflight,
        *,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        response_payload: Mapping[str, Any] | None = None,
    ) -> RunReplaySnapshot: ...

    def release_create(self, reservation: DraftPreflight) -> None: ...

    def create_draft(
        self,
        *,
        scope: RunScope,
        run_id: str,
        request_ref: str,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        idempotency_key: str,
    ) -> RunReplaySnapshot: ...

    def append_interaction(
        self,
        *,
        scope: RunScope,
        run_id: str,
        interaction_type: InteractionType,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> InteractionReceipt: ...

    def record_evaluation(
        self,
        *,
        scope: RunScope,
        run_id: str,
        report_ref: str,
        case_version: str,
        idempotency_key: str,
        payload: Mapping[str, Any] | None = None,
    ) -> InteractionReceipt: ...

    def replay(self, *, scope: RunScope, run_id: str) -> RunReplaySnapshot: ...


@dataclass(slots=True)
class _RunRecord:
    scope: RunScope
    run: DurableExperienceRun
    checkpoint: RunCheckpoint
    create_request_ref: str
    interactions: list[RunInteractionEntry] = field(default_factory=list)
    idempotency: dict[str, str] = field(default_factory=dict)
    idempotency_results: dict[str, InteractionReceipt | RunReplaySnapshot] = field(
        default_factory=dict
    )
    create_response_payload: Mapping[str, Any] | None = None
    deleted: bool = False


class InMemoryExperienceRunLedger:
    """Scope-isolated, append-only ledger for the first Web vertical slice."""

    def __init__(self) -> None:
        self._records: dict[tuple[tuple[str, str, tuple[str, ...]], str], _RunRecord] = {}
        self._pending_creates: dict[
            tuple[tuple[str, str, tuple[str, ...]], str], DraftPreflight
        ] = {}

    def preflight_create(
        self,
        *,
        scope: RunScope,
        run_id: str,
        request_ref: str,
        request_fingerprint: str,
        idempotency_key: str,
    ) -> DraftPreflight:
        """Reserve a run before Gateway invocation.

        The reservation is process-local for the in-memory implementation;
        durable adapters must enforce the same uniqueness under a transaction.
        No provider call is made here.
        """

        self._assert_scope(scope)
        self._validate_ids(run_id, request_ref, idempotency_key, request_fingerprint)
        record_key = (scope.key, run_id)
        existing = self._records.get(record_key)
        if existing is not None:
            previous = existing.idempotency.get(idempotency_key)
            if previous is None:
                raise RunHttpConflictError("RUN_ALREADY_EXISTS")
            if previous != request_fingerprint or existing.create_request_ref != request_ref:
                raise RunHttpConflictError("IDEMPOTENCY_REPLAY_MISMATCH")
            snapshot = self._snapshot(existing)
            return DraftPreflight(
                scope=scope,
                run_id=run_id,
                request_ref=request_ref,
                request_fingerprint=request_fingerprint,
                idempotency_key=idempotency_key,
                status="replay",
                snapshot=snapshot,
                response_payload=(None if existing.deleted else existing.create_response_payload),
            )
        if any(key[1] == run_id for key in self._records):
            raise RunHttpError("RUN_SCOPE_MISMATCH")

        pending = self._pending_creates.get(record_key)
        if pending is not None:
            if pending.idempotency_key == idempotency_key:
                if (
                    pending.request_fingerprint != request_fingerprint
                    or pending.request_ref != request_ref
                ):
                    raise RunHttpConflictError("IDEMPOTENCY_REPLAY_MISMATCH")
                return DraftPreflight(
                    scope=scope,
                    run_id=run_id,
                    request_ref=request_ref,
                    request_fingerprint=request_fingerprint,
                    idempotency_key=idempotency_key,
                    status="in_progress",
                )
            raise RunHttpConflictError("DRAFT_CREATE_IN_PROGRESS")

        reservation = DraftPreflight(
            scope=scope,
            run_id=run_id,
            request_ref=request_ref,
            request_fingerprint=request_fingerprint,
            idempotency_key=idempotency_key,
            status="reserved",
        )
        self._pending_creates[record_key] = reservation
        return reservation

    def finalize_create(
        self,
        reservation: DraftPreflight,
        *,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        response_payload: Mapping[str, Any] | None = None,
    ) -> RunReplaySnapshot:
        """Commit a reserved draft and its optional HTTP response projection."""

        if reservation.status != "reserved":
            if reservation.status == "replay" and reservation.snapshot is not None:
                return reservation.snapshot
            raise RunHttpConflictError("DRAFT_CREATE_IN_PROGRESS")
        record_key = (reservation.scope.key, reservation.run_id)
        pending = self._pending_creates.get(record_key)
        if pending != reservation:
            raise RunHttpConflictError("DRAFT_RESERVATION_NOT_FOUND")
        try:
            _assert_draft_payload(draft_payload)
            _assert_artifacts(artifact_refs)
            if response_payload is not None:
                _assert_safe_mapping(response_payload)
        except RunHttpError:
            self.release_create(reservation)
            raise

        run = DurableExperienceRun(
            run_id=reservation.run_id,
            tenant_id=reservation.scope.tenant_id,
            family_id=reservation.scope.family_id,
            subject_ids=reservation.scope.subject_ids,
            request_ref=reservation.request_ref,
        )
        try:
            run.transition(RunState.RUNNING, event_id=f"{reservation.run_id}:started")
            checkpoint = run.checkpoint(
                checkpoint_id=f"{reservation.run_id}:draft",
                artifact_refs=artifact_refs,
                draft_payload=dict(draft_payload),
            )
            run.transition(RunState.SUCCEEDED, event_id=f"{reservation.run_id}:succeeded")
        except (RunContractError, RunConflictError) as exc:
            self.release_create(reservation)
            raise RunHttpError("DRAFT_CREATE_FAILED", str(exc)) from exc

        record = _RunRecord(
            scope=reservation.scope,
            run=run,
            checkpoint=checkpoint,
            create_request_ref=reservation.request_ref,
            create_response_payload=(
                MappingProxyType(dict(response_payload)) if response_payload is not None else None
            ),
        )
        record.idempotency[reservation.idempotency_key] = reservation.request_fingerprint
        snapshot = self._snapshot(record)
        record.idempotency_results[reservation.idempotency_key] = snapshot
        self._records[record_key] = record
        self._pending_creates.pop(record_key, None)
        return snapshot

    def release_create(self, reservation: DraftPreflight) -> None:
        """Release a failed reservation so the same key can safely retry."""

        record_key = (reservation.scope.key, reservation.run_id)
        pending = self._pending_creates.get(record_key)
        if pending == reservation:
            self._pending_creates.pop(record_key, None)

    def create_draft(
        self,
        *,
        scope: RunScope,
        run_id: str,
        request_ref: str,
        draft_payload: Mapping[str, Any],
        artifact_refs: tuple[str, ...] = (),
        idempotency_key: str,
    ) -> RunReplaySnapshot:
        fingerprint = _fingerprint(
            {
                "operation": "create_draft",
                "request_ref": request_ref,
                "draft_payload": draft_payload,
                "artifact_refs": artifact_refs,
            }
        )
        reservation = self.preflight_create(
            scope=scope,
            run_id=run_id,
            request_ref=request_ref,
            request_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
        )
        if reservation.status == "replay" and reservation.snapshot is not None:
            return reservation.snapshot
        if reservation.status != "reserved":
            raise RunHttpConflictError("DRAFT_CREATE_IN_PROGRESS")
        return self.finalize_create(
            reservation,
            draft_payload=draft_payload,
            artifact_refs=artifact_refs,
        )

    def append_interaction(
        self,
        *,
        scope: RunScope,
        run_id: str,
        interaction_type: InteractionType,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> InteractionReceipt:
        self._assert_scope(scope)
        self._validate_ids(run_id, run_id, idempotency_key)
        if not isinstance(interaction_type, InteractionType):
            raise RunHttpError("INTERACTION_TYPE_UNSUPPORTED")
        _assert_safe_mapping(payload)
        self._validate_interaction_payload(interaction_type, payload)
        record = self._get_record(scope, run_id)
        fingerprint = _fingerprint(
            {
                "operation": interaction_type.value,
                "payload": payload,
            }
        )
        replayed = record.idempotency.get(idempotency_key)
        if replayed is not None:
            if replayed != fingerprint:
                raise RunHttpConflictError("IDEMPOTENCY_REPLAY_MISMATCH")
            result = record.idempotency_results[idempotency_key]
            if not isinstance(result, InteractionReceipt):
                raise RunHttpError("IDEMPOTENCY_RESULT_CORRUPT")
            return InteractionReceipt(
                run_id=result.run_id,
                interaction=result.interaction,
                status="replayed",
                idempotency_replayed=True,
            )
        if record.deleted and interaction_type is not InteractionType.DELETE:
            raise RunHttpError("RUN_DELETED")

        entry = RunInteractionEntry(
            event_id=f"{run_id}:interaction:{len(record.interactions) + 1}",
            run_id=run_id,
            scope=scope,
            interaction_type=interaction_type,
            payload=dict(payload),
            idempotency_key=idempotency_key,
            sequence=record.run.version + len(record.interactions) + 1,
        )
        record.interactions.append(entry)
        record.idempotency[idempotency_key] = fingerprint
        if interaction_type is InteractionType.DELETE:
            record.deleted = True
            record.create_response_payload = None
        receipt = InteractionReceipt(
            run_id=run_id,
            interaction=entry,
            status="deleted" if interaction_type is InteractionType.DELETE else "recorded",
        )
        record.idempotency_results[idempotency_key] = receipt
        return receipt

    def replay(self, *, scope: RunScope, run_id: str) -> RunReplaySnapshot:
        """Read only; this method has no gateway dependency or side effects."""

        self._assert_scope(scope)
        return self._snapshot(self._get_record(scope, run_id))

    def record_decision(
        self,
        *,
        scope: RunScope,
        run_id: str,
        decision: DecisionStatus,
        idempotency_key: str,
        payload: Mapping[str, Any] | None = None,
    ) -> InteractionReceipt:
        body = dict(payload or {})
        body["decision"] = decision
        return self.append_interaction(
            scope=scope,
            run_id=run_id,
            interaction_type=InteractionType.DECISION,
            payload=body,
            idempotency_key=idempotency_key,
        )

    def record_feedback(
        self,
        *,
        scope: RunScope,
        run_id: str,
        signal: str,
        idempotency_key: str,
        payload: Mapping[str, Any] | None = None,
    ) -> InteractionReceipt:
        body = dict(payload or {})
        body["signal"] = signal
        return self.append_interaction(
            scope=scope,
            run_id=run_id,
            interaction_type=InteractionType.FEEDBACK,
            payload=body,
            idempotency_key=idempotency_key,
        )

    def record_evaluation(
        self,
        *,
        scope: RunScope,
        run_id: str,
        report_ref: str,
        case_version: str,
        idempotency_key: str,
        payload: Mapping[str, Any] | None = None,
    ) -> InteractionReceipt:
        """Persist an aggregate evaluation projection beside the run.

        The report itself remains owned by the evaluation subsystem; the Run
        ledger stores only a bounded, media-free projection and its immutable
        reference so later feedback can be joined without copying responses.
        """

        body = dict(payload or {})
        body["report_ref"] = report_ref
        body["case_version"] = case_version
        body.setdefault("education_outcome_status", "NOT_MEASURED")
        return self.append_interaction(
            scope=scope,
            run_id=run_id,
            interaction_type=InteractionType.EVALUATION,
            payload=body,
            idempotency_key=idempotency_key,
        )

    def request_human(
        self,
        *,
        scope: RunScope,
        run_id: str,
        reason: str,
        idempotency_key: str,
    ) -> InteractionReceipt:
        if not reason.strip():
            raise RunHttpError("HUMAN_REVIEW_REASON_REQUIRED")
        return self.append_interaction(
            scope=scope,
            run_id=run_id,
            interaction_type=InteractionType.HUMAN_REVIEW,
            payload={"reason": reason, "status": "human_review"},
            idempotency_key=idempotency_key,
        )

    def delete(
        self,
        *,
        scope: RunScope,
        run_id: str,
        deletion_ref: str,
        idempotency_key: str,
    ) -> InteractionReceipt:
        if not deletion_ref.strip():
            raise RunHttpError("DELETION_REF_REQUIRED")
        return self.append_interaction(
            scope=scope,
            run_id=run_id,
            interaction_type=InteractionType.DELETE,
            payload={"deletion_ref": deletion_ref, "status": "deleted"},
            idempotency_key=idempotency_key,
        )

    def _get_record(self, scope: RunScope, run_id: str) -> _RunRecord:
        record = self._records.get((scope.key, run_id))
        if record is None:
            if any(key[1] == run_id for key in self._records):
                raise RunHttpError("RUN_SCOPE_MISMATCH")
            raise RunHttpError("RUN_NOT_FOUND")
        if record.scope.key != scope.key:
            raise RunHttpError("RUN_SCOPE_MISMATCH")
        return record

    def _snapshot(self, record: _RunRecord) -> RunReplaySnapshot:
        if record.deleted:
            return RunReplaySnapshot(
                run_id=record.run.run_id,
                scope=record.scope,
                state=record.run.state,
                status="DRAFT",
                event_sequence=record.run.version + len(record.interactions),
                interactions=tuple(record.interactions),
                draft_payload=None,
                artifact_refs=(),
                deletion_state="deleted",
            )
        return RunReplaySnapshot(
            run_id=record.run.run_id,
            scope=record.scope,
            state=record.run.state,
            status="DRAFT",
            event_sequence=record.run.version + len(record.interactions),
            interactions=tuple(record.interactions),
            draft_payload=record.checkpoint.draft_payload,
            artifact_refs=record.checkpoint.artifact_refs,
            deletion_state="active",
        )

    @staticmethod
    def _assert_scope(scope: RunScope) -> None:
        if not isinstance(scope, RunScope):
            raise RunHttpError("SCOPE_REQUIRED")

    @staticmethod
    def _validate_ids(*values: str) -> None:
        if any(not value for value in values):
            raise RunHttpError("RUN_ID_AND_IDEMPOTENCY_REQUIRED")

    @staticmethod
    def _validate_interaction_payload(
        interaction_type: InteractionType, payload: Mapping[str, Any]
    ) -> None:
        if interaction_type is InteractionType.DECISION and payload.get("decision") not in {
            "pending_human_confirmation",
            "accepted",
            "rewrite",
            "rejected",
        }:
            raise RunHttpError("DECISION_STATUS_UNSUPPORTED")
        if (
            interaction_type is InteractionType.HUMAN_REVIEW
            and payload.get("status") != "human_review"
        ):
            raise RunHttpError("HUMAN_REVIEW_STATUS_INVALID")
        if interaction_type is InteractionType.DELETE and payload.get("status") != "deleted":
            raise RunHttpError("DELETION_STATUS_INVALID")
        if interaction_type is InteractionType.FEEDBACK:
            _validate_feedback_payload(payload)
        if interaction_type is InteractionType.EVALUATION:
            _validate_evaluation_payload(payload)


def _validate_feedback_payload(payload: Mapping[str, Any]) -> None:
    """Validate optional evaluation/model references without resolving them.

    The ledger records references only; it must not fetch benchmark reports or
    infer model identity from a client payload.  A stable ``benchmark:``
    namespace is enough to make the linkage auditable while leaving report
    storage and ownership to the evaluation subsystem.
    """

    if payload.get("signal") not in {"helpful", "not_helpful", "request_human"}:
        raise RunHttpError("FEEDBACK_SIGNAL_UNSUPPORTED")
    if payload.get("feedback_kind") == "family_understanding":
        _validate_family_understanding_feedback(payload)
    for field_name in (
        "reason",
        "draft_version",
        "attempt_id",
        "candidate_id",
        "model_version",
        "benchmark_report_ref",
    ):
        value = payload.get(field_name)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise RunHttpError("FEEDBACK_REFERENCE_INVALID")
    benchmark_ref = payload.get("benchmark_report_ref")
    if benchmark_ref is not None and not benchmark_ref.startswith("benchmark:"):
        raise RunHttpError("BENCHMARK_REPORT_REF_INVALID")
    event_refs = payload.get("real_event_refs")
    if event_refs is not None and (
        not isinstance(event_refs, (list, tuple))
        or any(not isinstance(ref, str) or not ref.strip() or len(ref) > 256 for ref in event_refs)
    ):
        raise RunHttpError("REAL_EVENT_REFS_INVALID")


def _validate_family_understanding_feedback(payload: Mapping[str, Any]) -> None:
    if payload.get("feedback_version") != "family-understanding-feedback.v1":
        raise RunHttpError("FAMILY_UNDERSTANDING_FEEDBACK_VERSION_INVALID")
    rating = payload.get("understood_rating")
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        raise RunHttpError("FAMILY_UNDERSTANDING_RATING_INVALID")
    for field_name in ("felt_judged", "willing_to_continue", "correction_needed"):
        if not isinstance(payload.get(field_name), bool):
            raise RunHttpError("FAMILY_UNDERSTANDING_FEEDBACK_FLAG_INVALID")
    correction_ref = payload.get("correction_ref")
    has_correction_ref = isinstance(correction_ref, str) and bool(correction_ref.strip())
    if bool(payload["correction_needed"]) != has_correction_ref:
        raise RunHttpError("FAMILY_UNDERSTANDING_CORRECTION_REF_INVALID")


def _validate_evaluation_payload(payload: Mapping[str, Any]) -> None:
    """Validate the media-free projection stored with a Durable Run."""

    report_ref = payload.get("report_ref")
    case_version = payload.get("case_version")
    if (
        not isinstance(report_ref, str)
        or not report_ref.startswith("benchmark:")
        or len(report_ref) > 256
        or not report_ref.strip()
    ):
        raise RunHttpError("BENCHMARK_REPORT_REF_INVALID")
    if not isinstance(case_version, str) or not case_version.strip() or len(case_version) > 128:
        raise RunHttpError("EVALUATION_CASE_VERSION_INVALID")
    if payload.get("education_outcome_status") != "NOT_MEASURED":
        raise RunHttpError("EDUCATION_OUTCOME_MUST_REMAIN_NOT_MEASURED")
    summaries = payload.get("summaries")
    if summaries is not None and (
        not isinstance(summaries, (list, tuple))
        or any(not isinstance(summary, Mapping) for summary in summaries)
    ):
        raise RunHttpError("EVALUATION_SUMMARIES_INVALID")
    release_gate = payload.get("release_gate")
    if release_gate is not None:
        if not isinstance(release_gate, Mapping):
            raise RunHttpError("EVALUATION_RELEASE_GATE_INVALID")
        if release_gate.get("status") not in {"ELIGIBLE", "BLOCKED"}:
            raise RunHttpError("EVALUATION_RELEASE_GATE_INVALID")
        reasons = release_gate.get("reasons", ())
        if not isinstance(reasons, (list, tuple)) or any(
            not isinstance(reason, str) or not reason.strip() for reason in reasons
        ):
            raise RunHttpError("EVALUATION_RELEASE_GATE_INVALID")


def _fingerprint(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def fingerprint_request(value: Mapping[str, Any]) -> str:
    """Return a stable digest for generation intent, never raw media bytes."""

    _assert_safe_mapping(value)
    return _fingerprint(value)


_FORBIDDEN_KEYS = frozenset(
    {
        "family_score",
        "family_rank",
        "ranking",
        "score",
        "rank",
        "canonical_fact",
        "authoritative_fact",
    }
)


def _assert_safe_mapping(value: Any) -> None:
    if isinstance(value, Mapping):
        if _FORBIDDEN_KEYS.intersection(str(key).lower() for key in value):
            raise RunHttpError("RUN_PAYLOAD_FORBIDDEN_FACT_OR_RANKING")
        for nested in value.values():
            _assert_safe_mapping(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_safe_mapping(nested)


def _assert_draft_payload(value: Mapping[str, Any]) -> None:
    _assert_safe_mapping(value)
    for key, nested in value.items():
        if str(key).lower() in {"status", "draft_status"} and nested != "DRAFT":
            raise RunHttpError("RUN_DRAFT_STATUS_MUST_REMAIN_DRAFT")
        if isinstance(nested, Mapping):
            _assert_draft_payload(nested)
        elif isinstance(nested, (list, tuple)):
            for item in nested:
                if isinstance(item, Mapping):
                    _assert_draft_payload(item)


def _assert_artifacts(values: tuple[str, ...]) -> None:
    if any(not value or value.lower().startswith("data:") for value in values):
        raise RunHttpError("ARTIFACT_REFERENCE_INVALID")
    if len(set(values)) != len(values):
        raise RunHttpError("ARTIFACT_REFERENCES_MUST_BE_UNIQUE")


__all__ = [
    "DecisionStatus",
    "DeletionState",
    "DraftPreflight",
    "DraftPreflightStatus",
    "ExperienceRunLedger",
    "FeedbackStatus",
    "InMemoryExperienceRunLedger",
    "InteractionReceipt",
    "InteractionType",
    "RunHttpConflictError",
    "RunHttpError",
    "RunInteractionEntry",
    "RunReplaySnapshot",
    "RunScope",
    "fingerprint_request",
]
