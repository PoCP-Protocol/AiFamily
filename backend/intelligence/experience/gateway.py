"""Application boundary for the Family experience closed loop.

The gateway is deliberately small and provider agnostic.  It is the common
write/read boundary that UI channels can use while the durable event stream,
projection worker, and model runtime are introduced.  It accepts only the
immutable experience contracts; it never writes Family, Journey, Service, or
Commerce facts.

The in-memory implementation is suitable for development and contract tests.
Its API is intentionally shaped like the future durable adapter so replacing
the storage implementation does not change the application boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from backend.intelligence.experience.contracts import (
    ExperienceContractError,
    ExperienceEvent,
    ExperienceScope,
    FeedbackSignal,
    FeedbackTargetType,
    RecommendationDecision,
    ScopeMismatchError,
)
from backend.platform.idempotency.keys import (
    IdempotencyKey,
    IdempotencyStore,
    InMemoryIdempotencyStore,
)

type ExperienceRecord = ExperienceEvent | RecommendationDecision | FeedbackSignal


@dataclass(frozen=True, slots=True)
class ExperienceTimeline:
    """A tenant/family/subject-scoped view of the append-only experience log."""

    scope: ExperienceScope
    records: tuple[ExperienceRecord, ...]

    @property
    def events(self) -> tuple[ExperienceEvent, ...]:
        return tuple(record for record in self.records if isinstance(record, ExperienceEvent))

    @property
    def decisions(self) -> tuple[RecommendationDecision, ...]:
        return tuple(
            record for record in self.records if isinstance(record, RecommendationDecision)
        )

    @property
    def feedback(self) -> tuple[FeedbackSignal, ...]:
        return tuple(record for record in self.records if isinstance(record, FeedbackSignal))


class ExperienceGateway:
    """Unified experience application boundary with idempotent writes.

    A repeated request with the same tenant-scoped idempotency key returns the
    original immutable record.  Reusing a key for a different record is
    rejected, which prevents a retry or client bug from changing history.
    """

    def __init__(self, idempotency_store: IdempotencyStore | None = None) -> None:
        self._idempotency = idempotency_store or InMemoryIdempotencyStore()
        self._records_by_key: dict[str, ExperienceRecord] = {}
        self._records_by_target: dict[tuple[str, str], ExperienceRecord] = {}
        self._records: list[ExperienceRecord] = []
        self._sequence: dict[int, int] = {}

    def record_event(self, event: ExperienceEvent) -> ExperienceEvent:
        """Append an interaction event and return its canonical instance."""

        stored = self._append(event, event.idempotency_key)
        assert isinstance(stored, ExperienceEvent)
        return stored

    def publish_decision(self, decision: RecommendationDecision) -> RecommendationDecision:
        """Append an explainable recommendation decision."""

        stored = self._append(decision, decision.idempotency_key)
        assert isinstance(stored, RecommendationDecision)
        return stored

    def record_feedback(self, feedback: FeedbackSignal) -> FeedbackSignal:
        """Append feedback only when its target exists in the same scope."""

        if feedback.target_type is FeedbackTargetType.ACTION_PROPOSAL:
            raise ExperienceContractError("ACTION_PROPOSAL_TARGET_NOT_REGISTERED")
        target = self._records_by_target.get((feedback.tenant_id, feedback.target_id))
        if target is None:
            raise ExperienceContractError("EXPERIENCE_TARGET_NOT_FOUND")
        if feedback.target_type is FeedbackTargetType.EVENT and not isinstance(
            target, ExperienceEvent
        ):
            raise ExperienceContractError("FEEDBACK_TARGET_TYPE_MISMATCH")
        if feedback.target_type is FeedbackTargetType.RECOMMENDATION and not isinstance(
            target, RecommendationDecision
        ):
            raise ExperienceContractError("FEEDBACK_TARGET_TYPE_MISMATCH")
        feedback.assert_targets(target)
        stored = self._append(feedback, feedback.idempotency_key)
        assert isinstance(stored, FeedbackSignal)
        return stored

    def timeline(self, scope: ExperienceScope, *, limit: int | None = None) -> ExperienceTimeline:
        """Read records for one exact scope, newest records last.

        The exact region, consent version, and subject set are part of the
        lookup key.  A same-family record from another regional cell or subject
        set is therefore not accidentally joined into the response.
        """

        if not isinstance(scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        records = [record for record in self._records if _same_read_scope(record, scope)]
        records.sort(
            key=lambda record: (
                _datetime_sort_value(record_time(record)),
                self._sequence[id(record)],
            )
        )
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be non-negative")
            records = records[-limit:] if limit else []
        return ExperienceTimeline(scope=scope, records=tuple(records))

    def get_target(self, target_id: str, scope: ExperienceScope) -> ExperienceRecord:
        """Return a target only when it belongs to the requested exact scope."""

        target = self._records_by_target.get((scope.tenant_id, target_id))
        if target is None:
            raise ExperienceContractError("EXPERIENCE_TARGET_NOT_FOUND")
        if not _same_read_scope(target, scope):
            raise ScopeMismatchError("EXPERIENCE_TARGET_SCOPE_MISMATCH")
        return target

    def _append(self, record: ExperienceRecord, key: IdempotencyKey) -> ExperienceRecord:
        scoped_key = key.scoped_value
        existing = self._records_by_key.get(scoped_key)
        if existing is not None:
            if not _same_idempotent_record(existing, record):
                raise ExperienceContractError("IDEMPOTENCY_REPLAY_MISMATCH")
            return existing
        if not self._idempotency.check_and_reserve(key):
            raise ExperienceContractError("IDEMPOTENCY_RESERVATION_CONFLICT")

        target_id = _target_id(record)
        if target_id is not None:
            target_key = (record.tenant_id, target_id)
            previous = self._records_by_target.get(target_key)
            if previous is not None and previous != record:
                raise ExperienceContractError("EXPERIENCE_TARGET_ID_COLLISION")
            self._records_by_target[target_key] = record

        self._records_by_key[scoped_key] = record
        self._sequence[id(record)] = len(self._records)
        self._records.append(record)
        return record


def _target_id(record: ExperienceRecord) -> str | None:
    if isinstance(record, ExperienceEvent):
        return record.event_id
    if isinstance(record, RecommendationDecision):
        return record.decision_id
    return None


def _same_idempotent_record(left: ExperienceRecord, right: ExperienceRecord) -> bool:
    """Compare retry intent while ignoring generated event timestamps.

    A retry reconstructs the immutable contract and therefore receives new
    server timestamps for the record and its provenance.  Those timestamps are
    not client intent and must not turn a valid idempotent retry into a
    conflict; every other field remains part of the equality check.
    """

    if type(left) is not type(right):
        return False
    if isinstance(left, ExperienceEvent) and isinstance(right, ExperienceEvent):
        return left == replace(
            right,
            occurred_at=left.occurred_at,
            provenance=replace(
                right.provenance,
                captured_at=left.provenance.captured_at,
            ),
        )
    if isinstance(left, RecommendationDecision) and isinstance(right, RecommendationDecision):
        return left == replace(
            right,
            created_at=left.created_at,
            provenance=replace(
                right.provenance,
                captured_at=left.provenance.captured_at,
            ),
        )
    if isinstance(left, FeedbackSignal) and isinstance(right, FeedbackSignal):
        return left == replace(
            right,
            occurred_at=left.occurred_at,
            provenance=replace(
                right.provenance,
                captured_at=left.provenance.captured_at,
            ),
        )
    return left == right


def record_time(record: ExperienceRecord) -> datetime:
    if isinstance(record, RecommendationDecision):
        return record.created_at
    return record.occurred_at


def _datetime_sort_value(value: datetime) -> float:
    """Sort aware and legacy-naive timestamps without changing the record."""

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _same_read_scope(record: ExperienceRecord, scope: ExperienceScope) -> bool:
    return (
        record.tenant_id == scope.tenant_id
        and record.region_id == scope.region_id
        and record.family_id == scope.family_id
        and frozenset(record.subject_ids) == frozenset(scope.subject_ids)
        and record.purpose == scope.purpose
        and record.consent_version == scope.consent_version
    )


__all__ = ["ExperienceGateway", "ExperienceRecord", "ExperienceTimeline", "record_time"]
