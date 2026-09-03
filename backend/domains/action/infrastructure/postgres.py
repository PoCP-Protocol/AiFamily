"""PostgreSQL UI-09 GrowthAction application with audit/outbox idempotency."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from backend.domains.action.application.daily_action import (
    ActionActorScope,
    ActionEventScope,
    DailyActionCompletion,
    DailyActionProjection,
    DailyActionState,
    DailyActionTransition,
    completion_state,
    require_event_time,
    transition_state,
)
from backend.domains.action.domain.errors import (
    ActionConflictError,
    ActionForbiddenError,
    ActionNotFoundError,
    ActionValidationError,
)


async def _assert_can_manage(connection: AsyncConnection, actor: ActionActorScope) -> None:
    result = await connection.execute(
        text(
            """
            SELECT 1
            FROM family_memberships
            WHERE family_id = :family_id
              AND person_id = CAST(:actor_id AS uuid)
              AND status = 'ACTIVE'
              AND role IN ('OWNER_GUARDIAN', 'GUARDIAN')
            LIMIT 1
            """
        ),
        {"family_id": actor.family_id, "actor_id": actor.actor_id},
    )
    if result.first() is None:
        raise ActionForbiddenError("daily_action_family_manage_permission_required")


class SqlAlchemyDailyActionApplication:
    """Own GrowthAction facts; AI may supply draft text but never transition state."""

    def __init__(self, engine: AsyncEngine, *, clock: Callable[[], datetime] | None = None):
        if not isinstance(engine, AsyncEngine):
            raise TypeError("daily action application requires AsyncEngine")
        self._engine = engine
        self._clock = clock or (lambda: datetime.now(UTC))

    async def initialize_from_ai_plan(
        self,
        *,
        actor: ActionActorScope,
        tenant_id: str,
        plan_id: str,
        assignment_text: str,
        source_draft_id: str,
        source_draft_digest: str,
        source_provenance_ref: str,
        source_consent_version: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> DailyActionProjection:
        if not assignment_text.strip() or len(assignment_text) > 1000:
            raise ActionValidationError("daily_action_assignment_text_invalid")
        if len(source_draft_digest) != 64:
            raise ActionValidationError("daily_action_source_digest_invalid")
        payload = {
            "plan_id": plan_id,
            "assignment_text": assignment_text,
            "source_draft_id": source_draft_id,
            "source_draft_digest": source_draft_digest,
            "source_provenance_ref": source_provenance_ref,
            "source_consent_version": source_consent_version,
        }
        async with self._engine.begin() as connection:
            replay = await _claim_idempotency(
                connection,
                action="InitializeAiDailyAction",
                key=idempotency_key,
                actor=actor,
                payload=payload,
            )
            if replay is not None:
                return _projection_from_payload(replay["action"])
            await _assert_can_manage(connection, actor)
            plan = await connection.execute(
                text(
                    """
                    SELECT jp.plan_id, jp.onboarding_id, jp.priority_id, jp.current_phase,
                           gp.subject_person_id, gp.dimension_id
                    FROM family_journey_plans AS jp
                    JOIN growth_priorities AS gp
                      ON gp.priority_id = jp.priority_id
                     AND gp.family_id = jp.family_id
                     AND gp.status = 'ACTIVE'
                    WHERE jp.family_id = :family_id
                      AND jp.plan_id = :plan_id
                      AND jp.status = 'ACTIVE'
                    LIMIT 2
                    """
                ),
                {"family_id": actor.family_id, "plan_id": plan_id},
            )
            rows = plan.mappings().all()
            if len(rows) != 1 or rows[0]["subject_person_id"] is None:
                raise ActionNotFoundError("active_journey_plan_subject_not_found")
            row = rows[0]
            action_id = str(uuid4())
            now = _now(self._clock)
            await connection.execute(
                text(
                    """
                    INSERT INTO growth_actions(
                      action_id, family_id, journey_id, onboarding_id, priority_id,
                      journey_plan_id, journey_phase, subject_person_id, dimension_id,
                      action_type, instruction, assignment_text, status, execution_status,
                      assigned_to_person_id, assigned_at, due_date, day_index,
                      boundary, row_version, source_draft_id, source_draft_digest,
                      source_provenance_ref, source_consent_version
                    ) VALUES (
                      :action_id, :family_id, :onboarding_id, :onboarding_id, :priority_id,
                      :plan_id, :journey_phase, :subject_person_id, :dimension_id,
                      'AI_PLAN_DAILY_PRACTICE', :assignment_text, :assignment_text,
                      'ASSIGNED', 'NOT_STARTED', :subject_person_id, :now, :due_date, 1,
                      'ACTION_IS_NOT_OUTCOME', 1, :source_draft_id, :source_draft_digest,
                      :source_provenance_ref, :source_consent_version
                    )
                    ON CONFLICT (journey_plan_id, day_index)
                    WHERE journey_plan_id IS NOT NULL AND day_index IS NOT NULL
                    DO NOTHING
                    """
                ),
                {
                    "action_id": action_id,
                    "family_id": actor.family_id,
                    "onboarding_id": str(row["onboarding_id"]),
                    "priority_id": str(row["priority_id"]),
                    "plan_id": plan_id,
                    "journey_phase": str(row["current_phase"]),
                    "subject_person_id": str(row["subject_person_id"]),
                    "dimension_id": str(row["dimension_id"]),
                    "assignment_text": assignment_text.strip(),
                    "source_draft_id": source_draft_id,
                    "source_draft_digest": source_draft_digest,
                    "source_provenance_ref": source_provenance_ref,
                    "source_consent_version": source_consent_version,
                    "now": now,
                    "due_date": now.date(),
                },
            )
            action = await _required_action_by_plan_day(connection, plan_id, 1)
            response = {
                "action": action.as_dict(),
                "source_draft_id": source_draft_id,
                "source_provenance_ref": source_provenance_ref,
                "tenant_id": tenant_id,
                "result_state": "SUCCESS",
            }
            await _record_mutation(
                connection,
                actor=actor,
                tenant_id=tenant_id,
                action_name="InitializeAiDailyAction",
                event_name="AiDailyActionInitialized",
                action=action,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                before=None,
                after=response,
            )
            await _store_response(connection, idempotency_key, response)
            return action

    async def get_today(
        self,
        *,
        actor: ActionActorScope,
        tenant_id: str,
        subject_person_id: str,
        consent_version: str,
        approval_ref: str,
        correlation_id: str,
    ) -> dict[str, object]:
        async with self._engine.begin() as connection:
            await _assert_can_manage(connection, actor)
            result = await connection.execute(
                text(
                    """
                    SELECT ga.*
                    FROM growth_actions AS ga
                    JOIN family_journey_plans AS jp
                      ON jp.plan_id = ga.journey_plan_id
                     AND jp.family_id = ga.family_id
                     AND jp.status = 'ACTIVE'
                    WHERE ga.family_id = :family_id
                      AND ga.subject_person_id = :subject_person_id
                      AND ga.journey_plan_id IS NOT NULL
                      AND ga.execution_status NOT IN ('CANCELLED')
                    ORDER BY
                      CASE WHEN ga.due_date = CURRENT_DATE THEN 0 ELSE 1 END,
                      ga.day_index,
                      ga.created_at
                    LIMIT 1
                    """
                ),
                {
                    "family_id": actor.family_id,
                    "subject_person_id": subject_person_id,
                },
            )
            row = result.mappings().first()
            action = _projection(row) if row is not None else None
            await connection.execute(
                text(
                    """
                    INSERT INTO audit_logs(
                      family_id, actor_type, actor_id, action_name, resource_type,
                      resource_id, correlation_id, result, metadata
                    ) VALUES (
                      :family_id, 'PERSON', :actor_id, 'ReadDailyAction',
                      'GrowthAction', :resource_id, :correlation_id, 'SUCCESS',
                      CAST(:metadata AS jsonb)
                    )
                    """
                ),
                {
                    "family_id": actor.family_id,
                    "actor_id": actor.actor_id,
                    "resource_id": action.task_id if action else actor.family_id,
                    "correlation_id": correlation_id,
                    "metadata": json.dumps(
                        {
                            "tenant_id": tenant_id,
                            "subject_person_id": subject_person_id,
                            "accessed_fields": [
                                "assignment_text",
                                "execution_status",
                                "reflection",
                            ],
                            "access_purpose": "growth_tracking",
                            "approval_ref": approval_ref,
                            "consent_version": consent_version,
                        }
                    ),
                },
            )
            return {
                "tenant_id": tenant_id,
                "family_id": actor.family_id,
                "entry_state": "READY" if action else "EMPTY",
                "today_task": action.as_dict() if action else None,
                "today_tasks": [action.as_dict()] if action else [],
                "consent_version": consent_version,
                "boundary": "ACTION_IS_NOT_OUTCOME",
            }

    async def transition(
        self,
        *,
        actor: ActionActorScope,
        tenant_id: str,
        task_id: str,
        transition: DailyActionTransition,
        expected_task_version: int,
        event_scope: ActionEventScope,
        occurred_at: datetime,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict[str, object]:
        require_event_time(occurred_at)
        if expected_task_version < 1:
            raise ActionValidationError("daily_action_expected_version_invalid")
        payload = {
            "task_id": task_id,
            "transition": transition.value,
            "expected_task_version": expected_task_version,
        }
        async with self._engine.begin() as connection:
            replay = await _claim_idempotency(
                connection,
                action="ChangeDailyActionState",
                key=idempotency_key,
                actor=actor,
                payload=payload,
            )
            if replay is not None:
                return {**replay, "result_state": "REPLAYED"}
            await _assert_can_manage(connection, actor)
            current = await _required_action(connection, actor.family_id, task_id, lock=True)
            _assert_expected_version(current, expected_task_version)
            target = transition_state(current.execution_status, transition)
            timestamps = {
                "started_at": (
                    occurred_at
                    if transition
                    in {DailyActionTransition.START, DailyActionTransition.RESUME}
                    else None
                ),
                "paused_at": occurred_at if transition is DailyActionTransition.PAUSE else None,
                "cancelled_at": occurred_at if transition is DailyActionTransition.CANCEL else None,
            }
            await connection.execute(
                text(
                    """
                    UPDATE growth_actions
                    SET execution_status = :target,
                        started_at = COALESCE(started_at, :started_at),
                        paused_at = :paused_at,
                        cancelled_at = :cancelled_at,
                        row_version = row_version + 1
                    WHERE family_id = :family_id AND action_id = :task_id
                      AND row_version = :expected_task_version
                    """
                ),
                {
                    "target": target.value,
                    "started_at": timestamps["started_at"],
                    "paused_at": timestamps["paused_at"],
                    "cancelled_at": timestamps["cancelled_at"],
                    "family_id": actor.family_id,
                    "task_id": task_id,
                    "expected_task_version": expected_task_version,
                },
            )
            updated = await _required_action(connection, actor.family_id, task_id)
            response = {"action": updated.as_dict(), "result_state": "SUCCESS"}
            await _record_mutation(
                connection,
                actor=actor,
                tenant_id=tenant_id,
                action_name=f"{transition.value.title()}DailyAction",
                event_name=f"DailyAction{transition.value.title()}",
                action=updated,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                before=current.as_dict(),
                after=response,
                event_scope=event_scope,
                occurred_at=occurred_at,
            )
            await _store_response(connection, idempotency_key, response)
            return response

    async def check_in(
        self,
        *,
        actor: ActionActorScope,
        tenant_id: str,
        task_id: str,
        completion: DailyActionCompletion,
        reflection: str,
        expected_task_version: int,
        event_scope: ActionEventScope,
        occurred_at: datetime,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict[str, object]:
        require_event_time(occurred_at)
        if len(reflection) > 2000:
            raise ActionValidationError("daily_action_reflection_too_long")
        if expected_task_version < 1:
            raise ActionValidationError("daily_action_expected_version_invalid")
        payload = {
            "task_id": task_id,
            "completion": completion.value,
            "reflection": reflection,
            "expected_task_version": expected_task_version,
        }
        async with self._engine.begin() as connection:
            replay = await _claim_idempotency(
                connection,
                action="CheckInDailyAction",
                key=idempotency_key,
                actor=actor,
                payload=payload,
            )
            if replay is not None:
                return {**replay, "result_state": "REPLAYED"}
            await _assert_can_manage(connection, actor)
            current = await _required_action(connection, actor.family_id, task_id, lock=True)
            _assert_expected_version(current, expected_task_version)
            target = completion_state(current.execution_status, completion)
            await connection.execute(
                text(
                    """
                    UPDATE growth_actions
                    SET execution_status = :target,
                        status = :target,
                        completion_status = :target,
                        reflection = :reflection,
                        reflection_boundary = 'REFLECTION_IS_RAW_MATERIAL_NOT_OUTCOME',
                        completed_at = :completed_at,
                        row_version = row_version + 1
                    WHERE family_id = :family_id AND action_id = :task_id
                      AND row_version = :expected_task_version
                    """
                ),
                {
                    "target": target.value,
                    "reflection": reflection.strip() or None,
                    "completed_at": occurred_at,
                    "family_id": actor.family_id,
                    "task_id": task_id,
                    "expected_task_version": expected_task_version,
                },
            )
            updated = await _required_action(connection, actor.family_id, task_id)
            response = {"action": updated.as_dict(), "result_state": "SUCCESS"}
            await _record_mutation(
                connection,
                actor=actor,
                tenant_id=tenant_id,
                action_name="CheckInDailyAction",
                event_name="DailyActionCheckedIn",
                action=updated,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                before=current.as_dict(),
                after=response,
                event_scope=event_scope,
                occurred_at=occurred_at,
            )
            await _store_response(connection, idempotency_key, response)
            return response


def _assert_expected_version(
    current: DailyActionProjection,
    expected_task_version: int,
) -> None:
    if current.task_version != expected_task_version:
        raise ActionConflictError(
            f"daily_action_version_conflict:{expected_task_version}:{current.task_version}"
        )


async def _required_action(
    connection: AsyncConnection,
    family_id: str,
    task_id: str,
    *,
    lock: bool = False,
) -> DailyActionProjection:
    suffix = " FOR UPDATE" if lock else ""
    statement = (
        "SELECT * FROM growth_actions "
        f"WHERE family_id=:family_id AND action_id=:task_id{suffix}"
    )
    result = await connection.execute(
        text(statement),
        {"family_id": family_id, "task_id": task_id},
    )
    row = result.mappings().first()
    if row is None:
        raise ActionNotFoundError("daily_action_not_found")
    return _projection(row)


async def _required_action_by_plan_day(
    connection: AsyncConnection,
    plan_id: str,
    day_index: int,
) -> DailyActionProjection:
    result = await connection.execute(
        text(
            "SELECT * FROM growth_actions "
            "WHERE journey_plan_id=:plan_id AND day_index=:day_index LIMIT 2"
        ),
        {"plan_id": plan_id, "day_index": day_index},
    )
    rows = result.mappings().all()
    if len(rows) != 1:
        raise ActionConflictError("daily_action_plan_day_not_unique")
    return _projection(rows[0])


def _projection(row) -> DailyActionProjection:
    return DailyActionProjection(
        task_id=str(row["action_id"]),
        family_id=str(row["family_id"]),
        subject_person_id=str(row["subject_person_id"]),
        journey_plan_id=str(row["journey_plan_id"]),
        journey_phase=str(row["journey_phase"]),
        day_index=int(row["day_index"]),
        assignment_text=str(row["assignment_text"] or row["instruction"]),
        execution_status=DailyActionState(str(row["execution_status"])),
        task_version=int(row["row_version"]),
        due_date=row["due_date"].isoformat(),
        reflection=str(row["reflection"]) if row["reflection"] is not None else None,
        source_draft_id=(
            str(row["source_draft_id"]) if row["source_draft_id"] is not None else None
        ),
        source_draft_digest=(
            str(row["source_draft_digest"])
            if row["source_draft_digest"] is not None
            else None
        ),
        source_provenance_ref=(
            str(row["source_provenance_ref"])
            if row["source_provenance_ref"] is not None
            else None
        ),
        source_consent_version=(
            str(row["source_consent_version"])
            if row["source_consent_version"] is not None
            else None
        ),
    )


def _projection_from_payload(payload: dict[str, object]) -> DailyActionProjection:
    return DailyActionProjection(
        task_id=str(payload["task_id"]),
        family_id=str(payload.get("family_id", "replayed-family")),
        subject_person_id=str(payload.get("subject_person_id", "replayed-subject")),
        journey_plan_id=str(payload["journey_plan_id"]),
        journey_phase=str(payload["journey_phase"]),
        day_index=int(payload["day_index"]),
        assignment_text=str(payload["assignment_text"]),
        execution_status=DailyActionState(str(payload["execution_status"])),
        task_version=int(payload["task_version"]),
        due_date=str(payload["due_date"]),
        reflection=str(payload["reflection"]) if payload.get("reflection") else None,
        source_draft_id=(
            str(payload["source_draft_id"]) if payload.get("source_draft_id") else None
        ),
        source_draft_digest=(
            str(payload["source_draft_digest"])
            if payload.get("source_draft_digest")
            else None
        ),
        source_provenance_ref=(
            str(payload["source_provenance_ref"])
            if payload.get("source_provenance_ref")
            else None
        ),
        source_consent_version=(
            str(payload["source_consent_version"])
            if payload.get("source_consent_version")
            else None
        ),
    )


async def _claim_idempotency(
    connection: AsyncConnection,
    *,
    action: str,
    key: str,
    actor: ActionActorScope,
    payload: dict[str, object],
) -> dict[str, object] | None:
    if not key.strip() or len(key) > 128:
        raise ActionValidationError("invalid_idempotency_key")
    material = json.dumps(
        {"actor_id": actor.actor_id, "family_id": actor.family_id, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    request_hash = hashlib.sha256(material.encode()).hexdigest()
    await connection.execute(
        text(
            "INSERT INTO idempotency_keys(idempotency_key,action_name,request_hash) "
            "VALUES (:key,:action,:request_hash) ON CONFLICT (idempotency_key) DO NOTHING"
        ),
        {"key": key, "action": action, "request_hash": request_hash},
    )
    result = await connection.execute(
        text(
            "SELECT action_name,request_hash,response_body FROM idempotency_keys "
            "WHERE idempotency_key=:key FOR UPDATE"
        ),
        {"key": key},
    )
    row = result.first()
    if row is None or row.action_name != action or row.request_hash != request_hash:
        raise ActionConflictError("idempotency_conflict")
    if row.response_body is None:
        return None
    if isinstance(row.response_body, str):
        return json.loads(row.response_body)
    return row.response_body


async def _store_response(
    connection: AsyncConnection,
    key: str,
    response: dict[str, object],
) -> None:
    await connection.execute(
        text(
            "UPDATE idempotency_keys SET response_code=200, "
            "response_body=CAST(:response AS jsonb) WHERE idempotency_key=:key"
        ),
        {"key": key, "response": json.dumps(response, ensure_ascii=False)},
    )


async def _record_mutation(
    connection: AsyncConnection,
    *,
    actor: ActionActorScope,
    tenant_id: str,
    action_name: str,
    event_name: str,
    action: DailyActionProjection,
    correlation_id: str,
    idempotency_key: str,
    before: dict[str, object] | None,
    after: dict[str, object],
    event_scope: ActionEventScope | None = None,
    occurred_at: datetime | None = None,
) -> None:
    now = occurred_at.astimezone(UTC) if occurred_at is not None else datetime.now(UTC)
    metadata = {
        "tenant_id": tenant_id,
        "before": before,
        "after": after,
        "boundary": "ACTION_IS_NOT_OUTCOME",
    }
    event_payload = dict(after)
    event_payload["actor_id"] = actor.actor_id
    event_payload["source_provenance_ref"] = action.source_provenance_ref
    event_payload["source_draft_id"] = action.source_draft_id
    if event_scope is not None:
        if event_scope.tenant_id != tenant_id:
            raise ActionForbiddenError("daily_action_event_scope_tenant_mismatch")
        if event_scope.subject_person_id != action.subject_person_id:
            raise ActionForbiddenError("daily_action_event_scope_subject_mismatch")
        event_payload["experience_scope"] = event_scope.as_dict()
    await connection.execute(
        text(
            """
            INSERT INTO audit_logs(
              family_id,actor_type,actor_id,action_name,resource_type,resource_id,
              correlation_id,idempotency_key,result,metadata
            ) VALUES (
              :family_id,'PERSON',:actor_id,:action_name,'GrowthAction',:resource_id,
              :correlation_id,:idempotency_key,'SUCCESS',CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "family_id": actor.family_id,
            "actor_id": actor.actor_id,
            "action_name": action_name,
            "resource_id": action.task_id,
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "metadata": json.dumps(metadata, ensure_ascii=False),
        },
    )
    await connection.execute(
        text(
            """
            INSERT INTO outbox_events(
              aggregate_type,aggregate_id,event_name,event_version,event_id,
              correlation_id,payload,occurred_at
            ) VALUES (
              'GrowthAction',:aggregate_id,:event_name,1,:event_id,
              :correlation_id,CAST(:payload AS jsonb),:occurred_at
            )
            """
        ),
        {
            "aggregate_id": action.task_id,
            "event_name": event_name,
            "event_id": str(uuid4()),
            "correlation_id": correlation_id,
            "payload": json.dumps(event_payload, ensure_ascii=False),
            "occurred_at": now,
        },
    )


def _now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ActionValidationError("daily_action_clock_timezone_required")
    return value.astimezone(UTC)


__all__ = ["SqlAlchemyDailyActionApplication"]
