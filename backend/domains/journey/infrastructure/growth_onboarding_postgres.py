"""PostgreSQL adapters for the GrowthIntent -> Onboarding slice.

The reader is a Journey-owned query port.  It does not import or instantiate
the Assessment repository.  The historical ``growth_journeys`` table has no
intent column, so the repository writes and reads the governed
``growth_onboarding_intent_bindings`` record in the same transaction.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from backend.platform.persistence.session import get_engine, is_postgres_url

from ..application.growth_onboarding import (
    GrowthOnboardingApplication,
    GrowthOnboardingDependencies,
    Operation,
    StartGrowthOnboardingCommand,
    growth_onboarding_audit_event,
    idempotency_storage_key,
    request_hash,
)
from ..domain.growth_onboarding import (
    CONFIRMED_INTENT_BOUNDARY,
    GROWTH_ONBOARDING_ACTION,
    GROWTH_ONBOARDING_EVENT,
    ConfirmedGrowthIntent,
    GrowthOnboarding,
    GrowthOnboardingConflictError,
    GrowthOnboardingForbiddenError,
    GrowthOnboardingScope,
)


class SqlAlchemyConfirmedGrowthIntentReader:
    """Read only the canonical facts that prove a human-confirmed intent."""

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def load_confirmed_growth_intent(
        self, scope: GrowthOnboardingScope, intent_id: str
    ) -> ConfirmedGrowthIntent | None:
        result = await self._connection.execute(
            text(
                """
                select gi.intent_id,gi.family_id,gi.subject_person_id,gi.need_type,
                       gi.goal_text,gi.required_capability_keys,gi.status,
                       gi.confirmed_by,gi.confirmed_at,gi.boundary
                from growth_intents gi
                join tenant_family_bindings tfb on tfb.family_id=gi.family_id
                where gi.intent_id=cast(:intent_id as uuid)
                  and gi.family_id=cast(:family_id as uuid)
                  and tfb.tenant_id=cast(:tenant_id as uuid)
                  and tfb.status='ACTIVE'
                  and tfb.effective_from<=CURRENT_TIMESTAMP
                  and (tfb.effective_to is null or tfb.effective_to>CURRENT_TIMESTAMP)
                  and gi.status='OPEN'
                  and gi.confirmed_by is not null
                  and gi.confirmed_at is not null
                  and gi.boundary=:boundary
                """
            ),
            {
                "intent_id": intent_id,
                "family_id": scope.family_id,
                "tenant_id": scope.tenant_id,
                "boundary": CONFIRMED_INTENT_BOUNDARY,
            },
        )
        row = result.first()
        if row is None:
            return None
        return ConfirmedGrowthIntent(
            intent_id=str(row.intent_id),
            tenant_id=scope.tenant_id,
            family_id=str(row.family_id),
            subject_person_id=str(row.subject_person_id),
            need_type=row.need_type,
            goal_text=row.goal_text,
            required_capability_keys=tuple(row.required_capability_keys),
            status=str(row.status),
            confirmed_by=str(row.confirmed_by) if row.confirmed_by is not None else None,
            confirmed_at=row.confirmed_at,
            boundary=str(row.boundary),
        )


class SqlAlchemyGrowthOnboardingRepository:
    """Persist journey state and the intent binding as one unit."""

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def save_if_absent(
        self, onboarding: GrowthOnboarding
    ) -> tuple[GrowthOnboarding, bool]:
        insert_result = await self._connection.execute(
            text(
                """
                insert into growth_journeys(
                  journey_id,family_id,journey_type,phase,status,started_at,version
                ) values (
                  cast(:onboarding_id as uuid),cast(:family_id as uuid),
                  :journey_type,:phase,:status,:started_at,:version
                ) on conflict (journey_id) do nothing
                """
            ),
            {
                "onboarding_id": onboarding.onboarding_id,
                "family_id": onboarding.family_id,
                "journey_type": onboarding.journey_type,
                "phase": onboarding.phase,
                "status": onboarding.status,
                "started_at": onboarding.started_at,
                "version": onboarding.version,
            },
        )
        await self._connection.execute(
            text(
                """
                insert into growth_onboarding_intent_bindings(
                  tenant_family_binding_id,tenant_id,family_id,intent_id,
                  onboarding_id,subject_person_id
                )
                select tfb.tenant_family_binding_id,tfb.tenant_id,tfb.family_id,
                       cast(:intent_id as uuid),cast(:onboarding_id as uuid),
                       cast(:subject_person_id as uuid)
                from tenant_family_bindings tfb
                where tfb.tenant_id=cast(:tenant_id as uuid)
                  and tfb.family_id=cast(:family_id as uuid)
                  and tfb.status='ACTIVE'
                  and tfb.effective_from<=CURRENT_TIMESTAMP
                  and (tfb.effective_to is null or tfb.effective_to>CURRENT_TIMESTAMP)
                on conflict (tenant_id,family_id,intent_id) do nothing
                """
            ),
            {
                "tenant_id": onboarding.tenant_id,
                "family_id": onboarding.family_id,
                "intent_id": onboarding.intent_id,
                "onboarding_id": onboarding.onboarding_id,
                "subject_person_id": onboarding.subject_person_id,
            },
        )
        result = await self._connection.execute(
            text(
                """
                select b.binding_id,b.tenant_id,b.family_id,b.intent_id,
                       b.onboarding_id,b.subject_person_id,
                       j.journey_type,j.phase,j.status,j.started_at,j.version
                from growth_onboarding_intent_bindings b
                join growth_journeys j on j.journey_id=b.onboarding_id
                where b.tenant_id=cast(:tenant_id as uuid)
                  and b.family_id=cast(:family_id as uuid)
                  and b.intent_id=cast(:intent_id as uuid)
                for update
                """
            ),
            {
                "tenant_id": onboarding.tenant_id,
                "family_id": onboarding.family_id,
                "intent_id": onboarding.intent_id,
            },
        )
        row = result.first()
        if row is None or str(row.onboarding_id) != onboarding.onboarding_id:
            raise GrowthOnboardingConflictError("intent_onboarding_binding_invalid")
        if str(row.subject_person_id) != onboarding.subject_person_id:
            raise GrowthOnboardingConflictError("intent_onboarding_binding_invalid")
        return (
            GrowthOnboarding(
                onboarding_id=str(row.onboarding_id),
                tenant_id=str(row.tenant_id),
                family_id=str(row.family_id),
                intent_id=str(row.intent_id),
                subject_person_id=str(row.subject_person_id),
                journey_type=row.journey_type,
                phase=row.phase,
                status=row.status,
                started_by_actor_id=onboarding.started_by_actor_id,
                started_at=row.started_at,
                version=row.version,
                binding_id=str(row.binding_id),
            ),
            insert_result.rowcount == 1,
        )


class SqlAlchemyGrowthOnboardingPolicy:
    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def assert_can_start(self, scope: GrowthOnboardingScope) -> None:
        result = await self._connection.execute(
            text(
                """
                select 1
                from tenant_family_bindings tfb
                join family_memberships fm on fm.family_id=tfb.family_id
                where tfb.tenant_id=cast(:tenant_id as uuid)
                  and tfb.family_id=cast(:family_id as uuid)
                  and tfb.status='ACTIVE'
                  and tfb.effective_from<=CURRENT_TIMESTAMP
                  and (tfb.effective_to is null or tfb.effective_to>CURRENT_TIMESTAMP)
                  and fm.person_id::text=:actor_id
                  and fm.status='ACTIVE'
                  and fm.role in ('OWNER_GUARDIAN','GUARDIAN')
                limit 1
                """
            ),
            {
                "tenant_id": scope.tenant_id,
                "family_id": scope.family_id,
                "actor_id": scope.actor_id,
            },
        )
        if result.first() is None:
            raise GrowthOnboardingForbiddenError("actor_family_scope_denied")


class SqlAlchemyGrowthOnboardingConsent:
    """Live canonical consent check; no expiry column is invented.

    The baseline consent contract has no ``expires_at``.  Its equivalent
    effective-window proof is: the row is GRANTED, it was granted already,
    and it has not been withdrawn.  EXPIRED and WITHDRAWN rows fail by status.
    The tenant-family join is mandatory even though family ids are globally
    unique today; it is the authorization boundary for this query.
    """

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def assert_granted(
        self,
        scope: GrowthOnboardingScope,
        subject_person_id: str,
        purpose: str,
    ) -> None:
        result = await self._connection.execute(
            text(
                """
                select 1
                from consents c
                join tenant_family_bindings tfb on tfb.family_id=c.family_id
                where c.family_id=cast(:family_id as uuid)
                  and c.subject_person_id=cast(:subject_person_id as uuid)
                  and c.purpose=:purpose
                  and c.status='GRANTED'
                  and c.granted_at<=CURRENT_TIMESTAMP
                  and c.withdrawn_at is null
                  and tfb.tenant_id=cast(:tenant_id as uuid)
                  and tfb.status='ACTIVE'
                  and tfb.effective_from<=CURRENT_TIMESTAMP
                  and (tfb.effective_to is null or tfb.effective_to>CURRENT_TIMESTAMP)
                limit 1
                """
            ),
            {
                "tenant_id": scope.tenant_id,
                "family_id": scope.family_id,
                "subject_person_id": subject_person_id,
                "purpose": purpose,
            },
        )
        if result.first() is None:
            raise GrowthOnboardingForbiddenError(f"missing_consent:{purpose}")


AuditWriter = Callable[
    [AsyncConnection, StartGrowthOnboardingCommand, dict, datetime], Awaitable[None]
]
OutboxWriter = Callable[
    [AsyncConnection, StartGrowthOnboardingCommand, dict, datetime], Awaitable[None]
]


class PostgresGrowthOnboardingTransaction:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        audit_writer: AuditWriter | None = None,
        outbox_writer: OutboxWriter | None = None,
    ) -> None:
        self._engine = engine
        self._audit_writer = audit_writer or _append_audit
        self._outbox_writer = outbox_writer or _append_outbox

    async def execute(self, command: StartGrowthOnboardingCommand, operation: Operation) -> dict:
        request_hash_value = request_hash(command)
        async with self._engine.begin() as connection:
            replay = await _claim_idempotency(
                connection, command, request_hash_value
            )
            if replay is not None:
                return {**replay, "replayed": True}
            dependencies = GrowthOnboardingDependencies(
                intent_reader=SqlAlchemyConfirmedGrowthIntentReader(connection),
                repository=SqlAlchemyGrowthOnboardingRepository(connection),
                policy=SqlAlchemyGrowthOnboardingPolicy(connection),
                consent=SqlAlchemyGrowthOnboardingConsent(connection),
            )
            response = await operation(dependencies)
            occurred_at = datetime.now(UTC)
            await self._audit_writer(connection, command, response, occurred_at)
            await self._outbox_writer(connection, command, response, occurred_at)
            await _store_idempotency_response(
                connection, command, response
            )
            return response


async def _claim_idempotency(
    connection: AsyncConnection,
    command: StartGrowthOnboardingCommand,
    request_hash_value: str,
) -> dict | None:
    storage_key = idempotency_storage_key(command)
    await connection.execute(
        text(
            """
            insert into idempotency_keys(idempotency_key,action_name,request_hash)
            values (:key,:action,:request_hash)
            on conflict (idempotency_key) do nothing
            """
        ),
        {
            "key": storage_key,
            "action": GROWTH_ONBOARDING_ACTION,
            "request_hash": request_hash_value,
        },
    )
    result = await connection.execute(
        text(
            """
            select action_name,request_hash,response_body
            from idempotency_keys where idempotency_key=:key for update
            """
        ),
        {"key": storage_key},
    )
    row = result.first()
    if row is None:
        raise GrowthOnboardingConflictError("idempotency_conflict")
    if row.action_name != GROWTH_ONBOARDING_ACTION or row.request_hash != request_hash_value:
        raise GrowthOnboardingConflictError("idempotency_conflict")
    if row.response_body is None:
        return None
    if isinstance(row.response_body, str):
        return json.loads(row.response_body)
    return row.response_body


async def _append_audit(
    connection: AsyncConnection,
    command: StartGrowthOnboardingCommand,
    response: dict,
    occurred_at: datetime,
) -> None:
    event = growth_onboarding_audit_event(command, response, occurred_at)
    await connection.execute(
        text(
            """
            insert into platform_audit_events(
              actor_id,tenant_id,action,resource_type,resource_id,reason,
              correlation_id,occurred_at,action_kind,before,after
            ) values (
              :actor_id,:tenant_id,:action,:resource_type,:resource_id,:reason,
              :correlation_id,:occurred_at,:action_kind,
              cast(:before as json),cast(:after as json)
            )
            """
        ),
        {
            "actor_id": event.actor_id,
            "tenant_id": event.tenant_id,
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "reason": event.reason,
            "correlation_id": event.correlation_id,
            "occurred_at": event.timestamp,
            "action_kind": event.action_kind.value,
            "before": json.dumps(event.before, ensure_ascii=False)
            if event.before is not None
            else None,
            "after": json.dumps(event.after, ensure_ascii=False)
            if event.after is not None
            else None,
        },
    )


async def _append_outbox(
    connection: AsyncConnection,
    command: StartGrowthOnboardingCommand,
    response: dict,
    occurred_at: datetime,
) -> None:
    event = response["event"]
    await connection.execute(
        text(
            """
            insert into outbox_events(
              aggregate_type,aggregate_id,event_name,event_version,event_id,
              correlation_id,payload,occurred_at
            ) values (
              'GrowthOnboarding',:aggregate_id,:event_name,:event_version,
              cast(:event_id as uuid),:correlation_id,cast(:payload as jsonb),
              :occurred_at
            ) on conflict (event_id) do nothing
            """
        ),
        {
            "aggregate_id": event["onboarding_id"],
            "event_name": GROWTH_ONBOARDING_EVENT,
            "event_version": event["event_version"],
            "event_id": event["event_id"],
            "correlation_id": command.correlation_id,
            "payload": json.dumps(event, ensure_ascii=False),
            "occurred_at": occurred_at,
        },
    )


async def _store_idempotency_response(
    connection: AsyncConnection, command: StartGrowthOnboardingCommand, response: dict
) -> None:
    await connection.execute(
        text(
            """
            update idempotency_keys set response_code=200,
              response_body=cast(:response_body as jsonb)
            where idempotency_key=:key
            """
        ),
        {
            "key": idempotency_storage_key(command),
            "response_body": json.dumps(response, ensure_ascii=False),
        },
    )


def build_postgres_growth_onboarding_application(
    database_url: str,
) -> GrowthOnboardingApplication:
    if not is_postgres_url(database_url):
        raise RuntimeError("growth_onboarding_production_requires_postgresql")
    return GrowthOnboardingApplication(
        PostgresGrowthOnboardingTransaction(get_engine(database_url))
    )


__all__ = [
    "PostgresGrowthOnboardingTransaction",
    "SqlAlchemyConfirmedGrowthIntentReader",
    "SqlAlchemyGrowthOnboardingConsent",
    "SqlAlchemyGrowthOnboardingPolicy",
    "SqlAlchemyGrowthOnboardingRepository",
    "build_postgres_growth_onboarding_application",
]
