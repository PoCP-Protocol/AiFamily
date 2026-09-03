"""Relay GrowthAction domain events into the governed Experience outbox."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceNode,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)
from backend.intelligence.experience.persistence import SqlAlchemyExperienceOutbox
from backend.intelligence.experience.pipeline import ExperienceOutboxMessage
from backend.intelligence.model_gateway.contracts import DataClass
from backend.platform.consent.versioning import (
    ConsentVersionEntry,
    canonical_consent_version,
)
from backend.platform.idempotency.keys import IdempotencyKey

_EVENT_TYPES = {
    "DailyActionStart": ExperienceEventType.ACTION_STARTED,
    "DailyActionResume": ExperienceEventType.ACTION_RESUMED,
    "DailyActionPause": ExperienceEventType.ACTION_PAUSED,
    "DailyActionCancel": ExperienceEventType.ACTION_SKIPPED,
}


@dataclass(frozen=True, slots=True)
class GrowthActionRelayReport:
    inspected: int
    published: int
    consent_discarded: int
    failed: int
    dead_lettered: int


@dataclass(frozen=True, slots=True)
class GrowthActionExperienceRelay:
    """One bounded workflow-worker tick with atomic copy-and-ack semantics."""

    session_factory: async_sessionmaker[AsyncSession]
    consumer_name: str = "growth-action-to-experience.v1"
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("growth action relay requires async_sessionmaker")
        if not self.consumer_name.strip():
            raise ValueError("growth action relay consumer_name is required")
        if self.max_attempts < 1:
            raise ValueError("growth action relay max_attempts must be positive")

    async def run_once(self, *, limit: int = 100) -> GrowthActionRelayReport:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("growth action relay limit must be positive")
        published = 0
        discarded = 0
        failed = 0
        dead_lettered = 0
        async with self.session_factory() as session, session.begin():
            rows = (
                await session.execute(
                    text(
                            """
                            SELECT oe.outbox_id, oe.event_id, oe.aggregate_id,
                                   oe.event_name, oe.correlation_id, oe.payload,
                                   oe.occurred_at
                            FROM outbox_events AS oe
                            LEFT JOIN domain_outbox_consumer_deliveries AS delivery
                              ON delivery.outbox_id = oe.outbox_id
                             AND delivery.consumer_name = :consumer_name
                            WHERE oe.aggregate_type = 'GrowthAction'
                              AND oe.event_name IN (
                                'DailyActionStart', 'DailyActionResume',
                                'DailyActionPause', 'DailyActionCancel',
                                'DailyActionCheckedIn'
                              )
                              AND (delivery.status IS NULL OR delivery.status = 'RETRY')
                            ORDER BY oe.created_at, oe.outbox_id
                            FOR UPDATE OF oe SKIP LOCKED
                            LIMIT :limit
                            """
                    ),
                    {"limit": limit, "consumer_name": self.consumer_name},
                )
            ).mappings().all()
            outbox = SqlAlchemyExperienceOutbox(session)
            for row in rows:
                try:
                    async with session.begin_nested():
                        decoded = _decode_source(row)
                        if not await _consent_is_current(session, decoded):
                            await _audit_consent_discard(session, decoded)
                            await _record_delivery(
                                session,
                                outbox_id=str(row["outbox_id"]),
                                consumer_name=self.consumer_name,
                                status="DISCARDED",
                            )
                            discarded += 1
                            continue
                        message = _experience_message(decoded)
                        await outbox.append(message)
                        await _record_delivery(
                            session,
                            outbox_id=str(row["outbox_id"]),
                            consumer_name=self.consumer_name,
                            status="DELIVERED",
                        )
                        published += 1
                except Exception as error:  # noqa: BLE001 - isolate poison messages
                    terminal = await _record_failure(
                        session,
                        outbox_id=str(row["outbox_id"]),
                        consumer_name=self.consumer_name,
                        max_attempts=self.max_attempts,
                        error=error,
                    )
                    failed += 1
                    dead_lettered += int(terminal)
        return GrowthActionRelayReport(
            inspected=len(rows),
            published=published,
            consent_discarded=discarded,
            failed=failed,
            dead_lettered=dead_lettered,
        )


@dataclass(frozen=True, slots=True)
class _DecodedActionEvent:
    outbox_id: str
    event_id: str
    action_id: str
    event_name: str
    event_type: ExperienceEventType
    actor_id: str
    correlation_id: str
    occurred_at: datetime
    scope: dict[str, str]
    action: dict[str, Any]
    source_provenance_ref: str | None
    source_draft_id: str | None


def _decode_source(row) -> _DecodedActionEvent:
    payload = row["payload"]
    if not isinstance(payload, dict):
        raise ValueError("GROWTH_ACTION_RELAY_PAYLOAD_INVALID")
    scope = payload.get("experience_scope")
    action = payload.get("action")
    if not isinstance(scope, dict) or not isinstance(action, dict):
        raise ValueError("GROWTH_ACTION_RELAY_SCOPE_REQUIRED")
    event_name = str(row["event_name"])
    event_type = _event_type(event_name, action)
    required_scope = (
        "tenant_id",
        "region_id",
        "subject_person_id",
        "purpose",
        "consent_version",
        "deletion_ref",
        "locale",
    )
    if any(not str(scope.get(key) or "").strip() for key in required_scope):
        raise ValueError("GROWTH_ACTION_RELAY_SCOPE_INCOMPLETE")
    actor_id = str(payload.get("actor_id") or "")
    if not actor_id:
        raise ValueError("GROWTH_ACTION_RELAY_ACTOR_REQUIRED")
    occurred_at = row["occurred_at"]
    if not isinstance(occurred_at, datetime):
        raise ValueError("GROWTH_ACTION_RELAY_TIME_INVALID")
    return _DecodedActionEvent(
        outbox_id=str(row["outbox_id"]),
        event_id=str(row["event_id"]),
        action_id=str(row["aggregate_id"]),
        event_name=event_name,
        event_type=event_type,
        actor_id=actor_id,
        correlation_id=str(row["correlation_id"]),
        occurred_at=occurred_at,
        scope={key: str(scope[key]) for key in required_scope},
        action=dict(action),
        source_provenance_ref=(
            str(payload["source_provenance_ref"])
            if payload.get("source_provenance_ref")
            else None
        ),
        source_draft_id=(
            str(payload["source_draft_id"]) if payload.get("source_draft_id") else None
        ),
    )


def _event_type(event_name: str, action: dict[str, Any]) -> ExperienceEventType:
    if event_name == "DailyActionCheckedIn":
        execution_status = action.get("execution_status")
        if execution_status == "COMPLETED":
            return ExperienceEventType.ACTION_COMPLETED
        if execution_status == "PARTIAL":
            return ExperienceEventType.ACTION_PARTIAL
        if execution_status == "NOT_COMPLETED":
            return ExperienceEventType.ACTION_NOT_COMPLETED
        raise ValueError("GROWTH_ACTION_RELAY_COMPLETION_STATUS_INVALID")
    try:
        return _EVENT_TYPES[event_name]
    except KeyError as error:
        raise ValueError("GROWTH_ACTION_RELAY_EVENT_UNSUPPORTED") from error


def _experience_message(source: _DecodedActionEvent) -> ExperienceOutboxMessage:
    scope = ExperienceScope(
        global_id=(
            f"action-experience:{source.scope['tenant_id']}:"
            f"{source.action['family_id']}:"
            f"{source.scope['consent_version']}"
        ),
        tenant_id=source.scope["tenant_id"],
        region_id=source.scope["region_id"],
        family_id=str(source.action["family_id"]),
        subject_ids=(source.scope["subject_person_id"],),
        purpose=source.scope["purpose"],
        consent_version=source.scope["consent_version"],
        consent_granted=True,
        data_class=cast(DataClass, "MINOR_PERSONAL_DATA"),
        locale=source.scope["locale"],
        content_locale=source.scope["locale"],
        model_locale=source.scope["locale"],
        policy_locale=source.scope["locale"],
        deletion_ref=DeletionRef(
            deletion_id=source.scope["deletion_ref"],
            retention_policy="consent-bound",
        ),
        correlation_id=source.correlation_id,
        causation_id=f"growth-action-outbox:{source.event_id}",
    )
    refs = [f"growth-action:{source.action_id}", f"domain-outbox:{source.event_id}"]
    if source.source_draft_id:
        refs.append(f"growth-plan-draft:{source.source_draft_id}")
    if source.source_provenance_ref:
        refs.append(source.source_provenance_ref)
    event = ExperienceEvent(
        event_id=f"growth-action:{source.event_id}",
        event_type=source.event_type,
        node=ExperienceNode.N5,
        scope=scope,
        idempotency_key=IdempotencyKey(
            tenant_id=scope.tenant_id,
            value=f"growth-action-event:{source.event_id}",
        ),
        provenance=ExperienceProvenance(
            provenance_ref=f"growth-action-event:{source.event_id}",
            source_refs=tuple(refs),
            kind=ProvenanceKind.HUMAN,
            policy_version="growth-action-experience.v1",
            captured_at=source.occurred_at.astimezone(UTC),
        ),
        actor_id=source.actor_id,
        occurred_at=source.occurred_at.astimezone(UTC),
        payload={
            "action_id": source.action_id,
            "source_event_name": source.event_name,
            "journey_plan_id": source.action.get("journey_plan_id"),
            "journey_phase": source.action.get("journey_phase"),
            "day_index": source.action.get("day_index"),
            "execution_status": source.action.get("execution_status"),
            "boundary": "EXPERIENCE_SIGNAL_NOT_GROWTH_OUTCOME",
        },
    )
    return ExperienceOutboxMessage(
        message_id=f"growth-action-relay:{source.event_id}",
        event_type=f"experience.{event.event_type.value}",
        record=event,
        scope=scope,
        schema_version="experience.v1",
        enqueued_at=source.occurred_at.astimezone(UTC),
    )


async def _consent_is_current(
    session: AsyncSession,
    source: _DecodedActionEvent,
) -> bool:
    rows = (
        await session.execute(
        text(
            """
            SELECT c.consent_id, c.guardian_person_id, c.status,
                   c.policy_version, c.granted_at, c.withdrawn_at, p.birth_date
            FROM consents AS c
            JOIN persons AS p ON p.person_id=c.subject_person_id
            WHERE c.family_id=:family_id
              AND c.subject_person_id=:subject_id
              AND c.purpose=:purpose
            ORDER BY c.granted_at DESC, c.consent_id DESC
            """
        ),
        {
            "family_id": source.action["family_id"],
            "subject_id": source.scope["subject_person_id"],
            "purpose": source.scope["purpose"].upper(),
        },
        )
    ).mappings().all()
    if not rows:
        return False
    current_grant = any(
        str(row["status"]).upper() == "GRANTED" and row["withdrawn_at"] is None
        for row in rows
    )
    if not current_grant:
        return False
    version_entries: list[ConsentVersionEntry] = []
    for row in rows:
        granted_at = row["granted_at"]
        birth_date = row["birth_date"]
        if not isinstance(granted_at, datetime) or birth_date is None:
            return False
        age = granted_at.date().year - birth_date.year - (
            (granted_at.date().month, granted_at.date().day)
            < (birth_date.month, birth_date.day)
        )
        version_entries.append(
            ConsentVersionEntry(
                consent_id=str(row["consent_id"]),
                status=str(row["status"]),
                granted_at=granted_at,
                guardian_person_id=str(row["guardian_person_id"]),
                subject_age=age,
                policy_version=str(row["policy_version"]),
            )
        )
    current_version = canonical_consent_version(version_entries)
    return current_version == source.scope["consent_version"]


async def _audit_consent_discard(
    session: AsyncSession,
    source: _DecodedActionEvent,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO audit_logs(
              family_id, actor_type, actor_id, action_name, resource_type,
              resource_id, correlation_id, result, metadata
            ) VALUES (
              :family_id, 'SYSTEM', 'workflow-worker',
              'DiscardGrowthActionExperienceEvent', 'GrowthAction', :resource_id,
              :correlation_id, 'DENIED', CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "family_id": source.action["family_id"],
            "resource_id": source.action_id,
            "correlation_id": source.correlation_id,
            "metadata": (
                '{"reason":"CURRENT_CONSENT_REQUIRED",'
                '"boundary":"NO_EXPERIENCE_DERIVATIVE_CREATED"}'
            ),
        },
    )


async def _record_delivery(
    session: AsyncSession,
    *,
    outbox_id: str,
    consumer_name: str,
    status: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO domain_outbox_consumer_deliveries(
              outbox_id, consumer_name, status, attempts, updated_at, delivered_at
            ) VALUES (
              CAST(:outbox_id AS uuid), :consumer_name, :status, 1,
              CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (outbox_id, consumer_name) DO UPDATE
            SET status=EXCLUDED.status,
                attempts=domain_outbox_consumer_deliveries.attempts+1,
                last_error=NULL,
                updated_at=CURRENT_TIMESTAMP,
                delivered_at=CURRENT_TIMESTAMP
            """
        ),
        {
            "outbox_id": outbox_id,
            "consumer_name": consumer_name,
            "status": status,
        },
    )


async def _record_failure(
    session: AsyncSession,
    *,
    outbox_id: str,
    consumer_name: str,
    max_attempts: int,
    error: Exception,
) -> bool:
    reason = f"{type(error).__name__}: {error}"[:500]
    status = await session.scalar(
        text(
            """
            INSERT INTO domain_outbox_consumer_deliveries(
              outbox_id, consumer_name, status, attempts, last_error, updated_at
            ) VALUES (
              CAST(:outbox_id AS uuid), :consumer_name,
              CASE WHEN :max_attempts <= 1 THEN 'DEAD_LETTERED' ELSE 'RETRY' END,
              1, :last_error, CURRENT_TIMESTAMP
            )
            ON CONFLICT (outbox_id, consumer_name) DO UPDATE
            SET attempts=domain_outbox_consumer_deliveries.attempts+1,
                status=CASE
                  WHEN domain_outbox_consumer_deliveries.attempts+1 >= :max_attempts
                    THEN 'DEAD_LETTERED'
                  ELSE 'RETRY'
                END,
                last_error=:last_error,
                updated_at=CURRENT_TIMESTAMP
            RETURNING status
            """
        ),
        {
            "outbox_id": outbox_id,
            "consumer_name": consumer_name,
            "max_attempts": max_attempts,
            "last_error": reason,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO audit_logs(
              actor_type, actor_id, action_name, resource_type, resource_id,
              correlation_id, result, metadata
            ) VALUES (
              'SYSTEM', 'workflow-worker', 'RelayGrowthActionExperienceEvent',
              'OutboxEvent', :resource_id, :correlation_id, 'FAILED',
              CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "resource_id": outbox_id,
            "correlation_id": f"growth-action-relay:{outbox_id}",
            "metadata": json.dumps(
                {"reason": "RELAY_FAILED", "detail": reason},
                ensure_ascii=False,
            ),
        },
    )
    return status == "DEAD_LETTERED"


__all__ = ["GrowthActionExperienceRelay", "GrowthActionRelayReport"]
