"""Durable event reader used by the Engagement AI application boundary.

The reader reuses the transactional experience outbox as the source of truth.
It only reconstructs events that match the caller's denormalized tenant/family
scope and requested event ids; malformed envelopes fail closed instead of being
passed to a model.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.intelligence.experience.achievement_consumer import decode_experience_event
from backend.intelligence.experience.contracts import (
    ExperienceContractError,
    ExperienceEvent,
    ExperienceScope,
    assert_scope_compatible,
)
from backend.intelligence.experience.persistence import (
    ExperienceOutboxRow,
    StoredExperienceMessage,
)


class SqlAlchemyEngagementEventReader:
    """Read scope-bound events from the durable experience outbox."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(
        self, *, scope: ExperienceScope, event_ids: tuple[str, ...]
    ) -> tuple[ExperienceEvent, ...]:
        if not isinstance(scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not event_ids or len(set(event_ids)) != len(event_ids):
            raise ExperienceContractError("EXPERIENCE_EVENT_IDS_MUST_BE_UNIQUE")
        if scope.deletion_ref.requested_at is not None:
            raise ExperienceContractError("EXPERIENCE_SCOPE_DELETED")

        event_id_expression = ExperienceOutboxRow.payload["record"]["event_id"].as_string()
        statement = (
            select(ExperienceOutboxRow)
            .where(
                ExperienceOutboxRow.tenant_id == scope.tenant_id,
                ExperienceOutboxRow.region_id == scope.region_id,
                ExperienceOutboxRow.family_id == scope.family_id,
                ExperienceOutboxRow.consent_version == scope.consent_version,
                event_id_expression.in_(event_ids),
            )
            .order_by(ExperienceOutboxRow.enqueued_at, ExperienceOutboxRow.message_id)
        )
        result = await self._session.execute(statement)
        by_id: dict[str, ExperienceEvent] = {}
        for row in result.scalars():
            try:
                event = decode_experience_event(
                    StoredExperienceMessage(
                        message_id=row.message_id,
                        event_type=row.event_type,
                        tenant_id=row.tenant_id,
                        region_id=row.region_id,
                        family_id=row.family_id,
                        subject_ids=tuple(row.subject_ids),
                        purpose=row.purpose,
                        consent_version=row.consent_version,
                        idempotency_key=row.idempotency_key,
                        schema_version=row.schema_version,
                        payload=dict(row.payload),
                        enqueued_at=row.enqueued_at,
                        published_at=row.published_at,
                    )
                )
                assert_scope_compatible(scope, event)
            except Exception as error:  # noqa: BLE001 - persisted envelopes fail closed
                raise ExperienceContractError("EXPERIENCE_EVENT_READER_INVALID") from error
            by_id[event.event_id] = event

        if set(by_id) != set(event_ids):
            raise ExperienceContractError("EXPERIENCE_EVENTS_NOT_FOUND")
        return tuple(by_id[event_id] for event_id in event_ids)


__all__ = ["SqlAlchemyEngagementEventReader"]
