"""Transactional-outbox-shaped delivery and analytics projection primitives.

The production platform will replace the in-memory queues with a durable
database/outbox and a worker.  The contracts here keep the important behavior
already testable: idempotent enqueue, publish-after-projection, replay safety,
and exact tenant/family scope reads.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal

from backend.intelligence.experience.achievement import Achievement
from backend.intelligence.experience.contracts import (
    ExperienceContractError,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceScope,
    FeedbackSignal,
    RecommendationDecision,
)
from backend.intelligence.experience.experiments import ExperimentAssignment
from backend.intelligence.experience.features import FeatureKind, FeatureSignal

type PipelineRecord = (
    ExperienceEvent
    | RecommendationDecision
    | FeedbackSignal
    | FeatureSignal
    | ExperimentAssignment
    | Achievement
)


@dataclass(frozen=True, slots=True)
class ExperienceOutboxMessage:
    """One immutable message waiting for a projection worker."""

    message_id: str
    event_type: str
    record: PipelineRecord
    scope: ExperienceScope
    schema_version: str = "experience.v1"
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None

    @property
    def published(self) -> bool:
        return self.published_at is not None


class InMemoryExperienceOutbox:
    """Idempotent append-only outbox for dev/test and replay tests."""

    def __init__(self) -> None:
        self._messages_by_key: dict[str, ExperienceOutboxMessage] = {}
        self._messages: list[ExperienceOutboxMessage] = []

    def append(self, record: PipelineRecord) -> ExperienceOutboxMessage:
        key = record.idempotency_key.scoped_value
        existing = self._messages_by_key.get(key)
        if existing is not None:
            if existing.record != record:
                raise ExperienceContractError("IDEMPOTENCY_REPLAY_MISMATCH")
            return existing
        message = ExperienceOutboxMessage(
            message_id=f"outbox:{hashlib.sha256(key.encode('utf-8')).hexdigest()}",
            event_type=_event_type(record),
            record=record,
            scope=record.scope,
        )
        self._messages_by_key[key] = message
        self._messages.append(message)
        return message

    def pending(self, *, limit: int | None = None) -> tuple[ExperienceOutboxMessage, ...]:
        messages = [message for message in self._messages if not message.published]
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be non-negative")
            messages = messages[:limit]
        return tuple(messages)

    def mark_published(
        self,
        message_id: str,
        *,
        published_at: datetime | None = None,
    ) -> ExperienceOutboxMessage:
        for index, message in enumerate(self._messages):
            if message.message_id == message_id:
                if message.published:
                    return message
                updated = replace(message, published_at=published_at or datetime.now(UTC))
                self._messages[index] = updated
                self._messages_by_key[updated.record.idempotency_key.scoped_value] = updated
                return updated
        raise ExperienceContractError("OUTBOX_MESSAGE_NOT_FOUND")

    def publish_next(self, projector: AnalyticsProjection, *, limit: int = 100) -> int:
        """Project pending messages, marking each only after success."""

        published = 0
        for message in self.pending(limit=limit):
            projector.apply(message)
            self.mark_published(message.message_id)
            published += 1
        return published


class AnalyticsProjection:
    """Replay-safe operational projection; never computes a family score."""

    def __init__(self) -> None:
        self._processed: set[str] = set()
        self._feature_totals: defaultdict[tuple[tuple[str, ...], FeatureKind], Decimal] = (
            defaultdict(lambda: Decimal("0"))
        )
        self._event_counts: defaultdict[tuple[tuple[str, ...], str], int] = defaultdict(int)
        self._assignments: dict[tuple[str, str, str], ExperimentAssignment] = {}
        self._achievements: dict[tuple[tuple[str, ...], str], Achievement] = {}

    def apply(self, message: ExperienceOutboxMessage) -> None:
        if message.message_id in self._processed:
            return
        record = message.record
        key = _scope_key(message.scope)
        if isinstance(record, FeatureSignal):
            self._feature_totals[(key, record.kind)] += record.value
        elif isinstance(record, ExperienceEvent):
            self._event_counts[(key, str(record.event_type))] += 1
        elif isinstance(record, ExperimentAssignment):
            self._assignments[
                (record.scope.tenant_id, record.experiment_id, record.scope.family_id)
            ] = record
        elif isinstance(record, Achievement):
            self._achievements[(key, record.key.value)] = record
        self._processed.add(message.message_id)

    def feature_total(self, scope: ExperienceScope, kind: FeatureKind) -> Decimal | None:
        value = self._feature_totals.get((_scope_key(scope), kind))
        return value if value else None

    def event_count(self, scope: ExperienceScope, event_type: ExperienceEventType) -> int:
        return self._event_counts.get((_scope_key(scope), str(event_type)), 0)

    def assignment(
        self,
        experiment_id: str,
        scope: ExperienceScope,
    ) -> ExperimentAssignment | None:
        assignment = self._assignments.get((scope.tenant_id, experiment_id, scope.family_id))
        if assignment is None or _scope_key(assignment.scope) != _scope_key(scope):
            return None
        return assignment

    def achievements(self, scope: ExperienceScope) -> tuple[Achievement, ...]:
        """Return the family's evidence-bound achievements in earned order."""

        records = [
            achievement
            for (scope_key, _), achievement in self._achievements.items()
            if scope_key == _scope_key(scope)
        ]
        return tuple(sorted(records, key=lambda item: item.earned_at))


class ExperiencePipeline:
    """Small application facade joining append, outbox, and projection."""

    def __init__(
        self,
        outbox: InMemoryExperienceOutbox | None = None,
        projection: AnalyticsProjection | None = None,
    ) -> None:
        self.outbox = outbox or InMemoryExperienceOutbox()
        self.projection = projection or AnalyticsProjection()

    def ingest(self, record: PipelineRecord) -> ExperienceOutboxMessage:
        return self.outbox.append(record)

    def publish(self, *, limit: int = 100) -> int:
        return self.outbox.publish_next(self.projection, limit=limit)


def _event_type(record: PipelineRecord) -> str:
    if isinstance(record, ExperienceEvent):
        return f"experience.{record.event_type}"
    if isinstance(record, RecommendationDecision):
        return "experience.recommendation_decision"
    if isinstance(record, FeedbackSignal):
        return "experience.feedback_signal"
    if isinstance(record, FeatureSignal):
        return f"feature.{record.kind}"
    if isinstance(record, Achievement):
        return f"experience.achievement.{record.key}"
    return "experiment.assignment"


def _scope_key(scope: ExperienceScope) -> tuple[str, ...]:
    return (
        scope.tenant_id,
        scope.region_id,
        scope.family_id,
        *sorted(scope.subject_ids),
        scope.purpose,
        scope.consent_version,
    )


__all__ = [
    "AnalyticsProjection",
    "ExperienceOutboxMessage",
    "ExperiencePipeline",
    "InMemoryExperienceOutbox",
    "PipelineRecord",
]
