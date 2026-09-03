"""Provider-neutral consumer that projects outbox events into achievements.

The consumer is deliberately narrower than the generic outbox worker: it
accepts only ``experience.<ExperienceEventType>`` envelopes and reconstructs
the immutable :class:`ExperienceEvent` contract before invoking
``AchievementEngine``.  It never calls a model provider and never writes a
Family/Journey/Commerce fact.  Invalid or unsupported envelopes raise a
permanent delivery error so the worker can route them to its dead-letter sink
instead of retrying malformed data forever.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from backend.intelligence.experience.achievement import (
    Achievement,
    AchievementEngine,
    AchievementProjectionPort,
)
from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceNode,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)
from backend.intelligence.experience.outbox_worker import (
    PermanentExperienceDeliveryError,
)
from backend.intelligence.experience.persistence import StoredExperienceMessage
from backend.intelligence.experience.projections import (
    AchievementNotificationProjection,
    ExperienceAnalyticsProjection,
)
from backend.intelligence.model_gateway.contracts import DataClass
from backend.platform.idempotency.keys import IdempotencyKey


class ExperienceAchievementEnvelopeError(PermanentExperienceDeliveryError):
    """A malformed/unsupported envelope cannot become valid by retrying."""


class ExperienceAchievementConsumer:
    """Project append-only ``ExperienceEvent`` messages into achievements.

    ``AchievementEngine`` owns the evidence-bound projection and is injected
    so a durable implementation can replace the in-memory projection without
    changing this outbox boundary.  Message IDs are remembered in-process as
    a fast path; the engine/projection remains the source of idempotent truth
    when a crash occurs between projection and outbox acknowledgement.
    """

    def __init__(
        self,
        engine: AchievementEngine | None = None,
        *,
        projection: AchievementProjectionPort | None = None,
        notifications: AchievementNotificationProjection | None = None,
        analytics: ExperienceAnalyticsProjection | None = None,
    ) -> None:
        if engine is not None and projection is not None:
            raise ValueError("ACHIEVEMENT_ENGINE_AND_PROJECTION_ARE_MUTUALLY_EXCLUSIVE")
        self.engine = engine or AchievementEngine(projection)
        self._notifications = notifications
        self._analytics = analytics
        self._processed_message_ids: set[str] = set()
        self._last_achievements: dict[str, tuple[Achievement, ...]] = {}

    async def consume(self, message: StoredExperienceMessage) -> None:
        """Validate, decode, and project one opaque outbox envelope."""

        if message.message_id in self._processed_message_ids:
            return
        event = decode_experience_event(message)
        if self._analytics is not None:
            await _resolve(self._analytics.record_event(event))
        # ``apply_async`` resolves both the synchronous InMemory projection and
        # the durable SQL projection through one provider-neutral composition
        # path.  The consumer therefore cannot accidentally drop a coroutine
        # or acknowledge the outbox before persistence has flushed.
        earned = await self.engine.apply_async(event)
        if self._analytics is not None:
            for achievement in earned:
                await _resolve(self._analytics.record_achievement(achievement))
        if self._notifications is not None:
            for achievement in earned:
                await _resolve(self._notifications.publish(achievement))
        self._last_achievements[message.message_id] = earned
        self._processed_message_ids.add(message.message_id)

    def achievements_for(self, message_id: str) -> tuple[Achievement, ...]:
        """Return achievements emitted by a successfully consumed message."""

        return self._last_achievements.get(message_id, ())


def decode_experience_event(message: StoredExperienceMessage) -> ExperienceEvent:
    """Safely reconstruct an ``ExperienceEvent`` from its JSON envelope.

    The persisted envelope is treated as untrusted input.  We require all
    scope/provenance/idempotency fields instead of filling defaults, reject
    nested media/memory objects until a dedicated parser exists, and compare
    the reconstructed scope with the denormalised outbox columns.
    """

    if not isinstance(message, StoredExperienceMessage):
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_MESSAGE_REQUIRED")
    prefix = "experience."
    if not message.event_type.startswith(prefix):
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_EVENT_TYPE_REQUIRED")
    event_type_value = message.event_type.removeprefix(prefix)
    try:
        event_type = ExperienceEventType(event_type_value)
    except ValueError as error:
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_EVENT_TYPE_UNSUPPORTED") from error

    payload = _mapping(message.payload, "payload")
    record = _mapping(payload.get("record"), "record")
    try:
        event = _decode_event(record, expected_type=event_type)
    except ExperienceAchievementEnvelopeError:
        raise
    except Exception as error:  # noqa: BLE001 - convert constructor failures to a DLQ error
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_EVENT_INVALID") from error

    _assert_message_scope(message, event)
    return event


async def _resolve(value):
    if inspect.isawaitable(value):
        await value


def _decode_event(
    record: Mapping[str, Any], *, expected_type: ExperienceEventType
) -> ExperienceEvent:
    raw_type = _required_str(record, "event_type")
    try:
        actual_type = ExperienceEventType(raw_type)
    except ValueError as error:
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_RECORD_EVENT_TYPE_INVALID") from error
    if actual_type is not expected_type:
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_EVENT_TYPE_MISMATCH")

    raw_scope = _mapping(record.get("scope"), "scope")
    scope = _decode_scope(raw_scope)
    provenance = _decode_provenance(_mapping(record.get("provenance"), "provenance"))
    raw_idempotency = _mapping(record.get("idempotency_key"), "idempotency_key")
    idempotency_key = IdempotencyKey(
        tenant_id=_required_str(raw_idempotency, "tenant_id"),
        value=_required_str(raw_idempotency, "value"),
    )
    raw_media = _optional_sequence(record.get("media_refs", ()), "media_refs")
    raw_memory = _optional_sequence(record.get("memory_refs", ()), "memory_refs")
    if raw_media or raw_memory:
        # Dropping these references would weaken deletion/provenance guarantees;
        # route to DLQ until the explicit nested parsers are added.
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_NESTED_REFS_UNSUPPORTED")

    occurred_at = _datetime(record.get("occurred_at"), "occurred_at")
    raw_payload = record.get("payload", {})
    event_payload = _mapping(raw_payload, "event.payload")
    try:
        return ExperienceEvent(
            event_id=_required_str(record, "event_id"),
            event_type=actual_type,
            node=ExperienceNode(_required_str(record, "node")),
            scope=scope,
            idempotency_key=idempotency_key,
            provenance=provenance,
            actor_id=_required_str(record, "actor_id"),
            occurred_at=occurred_at,
            payload=event_payload,
        )
    except Exception as error:  # noqa: BLE001 - preserve fail-closed DLQ semantics
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_EVENT_INVALID") from error


def _decode_scope(raw: Mapping[str, Any]) -> ExperienceScope:
    raw_subjects = raw.get("subject_ids")
    if not isinstance(raw_subjects, (list, tuple)):
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_SCOPE_SUBJECTS_INVALID")
    subjects = tuple(_string_sequence(raw_subjects, "scope.subject_ids"))
    raw_data_class = _required_str(raw, "data_class")
    raw_deletion = _mapping(raw.get("deletion_ref"), "scope.deletion_ref")
    try:
        return ExperienceScope(
            global_id=_required_str(raw, "global_id"),
            tenant_id=_required_str(raw, "tenant_id"),
            region_id=_required_str(raw, "region_id"),
            family_id=_required_str(raw, "family_id"),
            subject_ids=subjects,
            purpose=_required_str(raw, "purpose"),
            consent_version=_required_str(raw, "consent_version"),
            consent_granted=_required_bool(raw, "consent_granted"),
            data_class=cast(DataClass, raw_data_class),
            locale=_required_str(raw, "locale"),
            content_locale=_required_str(raw, "content_locale"),
            model_locale=_required_str(raw, "model_locale"),
            policy_locale=_required_str(raw, "policy_locale"),
            deletion_ref=DeletionRef(
                deletion_id=_required_str(raw_deletion, "deletion_id"),
                retention_policy=_required_str(raw_deletion, "retention_policy"),
                requested_at=_optional_datetime(
                    raw_deletion.get("requested_at"), "scope.deletion_ref.requested_at"
                ),
            ),
            correlation_id=_required_str(raw, "correlation_id"),
            causation_id=_required_str(raw, "causation_id"),
        )
    except ExperienceAchievementEnvelopeError:
        raise
    except Exception as error:  # noqa: BLE001
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_SCOPE_INVALID") from error


def _decode_provenance(raw: Mapping[str, Any]) -> ExperienceProvenance:
    try:
        return ExperienceProvenance(
            provenance_ref=_required_str(raw, "provenance_ref"),
            source_refs=tuple(_string_sequence(raw.get("source_refs"), "provenance.source_refs")),
            kind=ProvenanceKind(_required_str(raw, "kind")),
            policy_version=_required_str(raw, "policy_version"),
            context_snapshot_ref=_optional_str(
                raw.get("context_snapshot_ref"), "provenance.context_snapshot_ref"
            ),
            model_attempt_ref=_optional_str(
                raw.get("model_attempt_ref"), "provenance.model_attempt_ref"
            ),
            captured_at=_datetime(raw.get("captured_at"), "provenance.captured_at"),
        )
    except ExperienceAchievementEnvelopeError:
        raise
    except Exception as error:  # noqa: BLE001
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_PROVENANCE_INVALID") from error


def _assert_message_scope(message: StoredExperienceMessage, event: ExperienceEvent) -> None:
    scope = event.scope
    if (
        scope.tenant_id != message.tenant_id
        or scope.region_id != message.region_id
        or scope.family_id != message.family_id
        or frozenset(scope.subject_ids) != frozenset(message.subject_ids)
        or scope.purpose != message.purpose
        or scope.consent_version != message.consent_version
    ):
        raise ExperienceAchievementEnvelopeError("ACHIEVEMENT_SCOPE_MISMATCH")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExperienceAchievementEnvelopeError(
            f"{name.upper().replace('.', '_')}_MAPPING_REQUIRED"
        )
    return value


def _required_str(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ExperienceAchievementEnvelopeError(f"{key.upper()}_REQUIRED")
    return value


def _optional_str(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ExperienceAchievementEnvelopeError(f"{name.upper().replace('.', '_')}_INVALID")
    return value


def _required_bool(mapping: Mapping[str, Any], key: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise ExperienceAchievementEnvelopeError(f"{key.upper()}_REQUIRED")
    return value


def _string_sequence(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ExperienceAchievementEnvelopeError(f"{name.upper().replace('.', '_')}_REQUIRED")
    if any(not isinstance(item, str) or not item for item in value):
        raise ExperienceAchievementEnvelopeError(f"{name.upper().replace('.', '_')}_INVALID")
    return tuple(cast(str, item) for item in value)


def _optional_sequence(value: Any, name: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ExperienceAchievementEnvelopeError(f"ACHIEVEMENT_{name.upper()}_INVALID")
    return tuple(value)


def _datetime(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ExperienceAchievementEnvelopeError(f"{name.upper().replace('.', '_')}_REQUIRED")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExperienceAchievementEnvelopeError(
            f"{name.upper().replace('.', '_')}_INVALID"
        ) from error
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _optional_datetime(value: Any, name: str) -> datetime | None:
    if value is None:
        return None
    return _datetime(value, name)


__all__ = [
    "ExperienceAchievementConsumer",
    "ExperienceAchievementEnvelopeError",
    "decode_experience_event",
]
