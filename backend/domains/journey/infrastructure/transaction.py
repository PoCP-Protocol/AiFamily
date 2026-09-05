"""Atomic Journey mutation runner.

Idempotency claim, domain repository writes, audit and outbox all execute on
the same ``AsyncConnection`` owned by ``AsyncEngine.begin()``. Any exception
rolls the complete mutation back; a stored response is returned without
running the domain operation again.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ..application.service import JourneyActor, JourneyService
from ..domain.errors import JourneyConflictError
from .sqlalchemy_policy import SqlAlchemyJourneyPolicy
from .sqlalchemy_repository import SqlAlchemyJourneyRepository

Mutation = Callable[[JourneyService], Awaitable[dict]]
ResourceId = str | Callable[[dict], str]


class JourneyTransactionRunner:
    def __init__(self, engine: AsyncEngine):
        self._engine = engine

    async def execute(
        self,
        *,
        actor: JourneyActor,
        action: str,
        resource_type: str,
        resource_id: ResourceId,
        event_name: str,
        idempotency_key: str,
        correlation_id: str,
        request_payload: dict[str, Any],
        operation: Mutation,
    ) -> dict:
        request_hash = _request_hash(actor, action, request_payload)
        async with self._engine.begin() as connection:
            replay = await _claim_idempotency(
                connection, action, idempotency_key, request_hash
            )
            if replay is not None:
                return replay

            service = JourneyService(
                SqlAlchemyJourneyRepository(connection), SqlAlchemyJourneyPolicy(connection)
            )
            response = await operation(service)
            resolved_resource_id = (
                resource_id(response) if callable(resource_id) else resource_id
            )
            occurred_at = datetime.now(UTC)
            await _append_audit(
                connection,
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resolved_resource_id,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                response=response,
            )
            await _append_outbox(
                connection,
                actor=actor,
                event_name=event_name,
                resource_type=resource_type,
                resource_id=resolved_resource_id,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
                response=response,
            )
            await _store_idempotency_response(connection, idempotency_key, response)
            return response


def _request_hash(actor: JourneyActor, action: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "action": action,
            "actor_id": actor.actor_id,
            "family_id": actor.family_id,
            "payload": payload,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def _claim_idempotency(
    connection: AsyncConnection, action: str, key: str, request_hash: str
) -> dict | None:
    await connection.execute(
        text(
            """
            insert into idempotency_keys(idempotency_key,action_name,request_hash)
            values (:key,:action,:request_hash)
            on conflict (idempotency_key) do nothing
            """
        ),
        {"key": key, "action": action, "request_hash": request_hash},
    )
    result = await connection.execute(
        text(
            """
            select action_name,request_hash,response_body from idempotency_keys
            where idempotency_key=:key for update
            """
        ),
        {"key": key},
    )
    row = result.first()
    if row is None or row.action_name != action or row.request_hash != request_hash:
        raise JourneyConflictError("idempotency_conflict")
    if row.response_body is None:
        return None
    if isinstance(row.response_body, str):
        return json.loads(row.response_body)
    return row.response_body


async def _append_audit(
    connection: AsyncConnection,
    *,
    actor: JourneyActor,
    action: str,
    resource_type: str,
    resource_id: str,
    correlation_id: str,
    idempotency_key: str,
    occurred_at: datetime,
    response: dict,
) -> None:
    metadata = json.dumps(
        {"occurred_at": occurred_at.isoformat(), "response": response}, ensure_ascii=False
    )
    await connection.execute(
        text(
            """
            insert into audit_logs(
              family_id,actor_type,actor_id,action_name,resource_type,resource_id,
              correlation_id,idempotency_key,result,metadata
            ) values (
              :family_id,'USER',:actor_id,:action,:resource_type,:resource_id,
              :correlation_id,:idempotency_key,'SUCCESS',cast(:metadata as jsonb)
            )
            """
        ),
        {
            "family_id": actor.family_id,
            "actor_id": actor.actor_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "metadata": metadata,
        },
    )


async def _append_outbox(
    connection: AsyncConnection,
    *,
    actor: JourneyActor,
    event_name: str,
    resource_type: str,
    resource_id: str,
    correlation_id: str,
    occurred_at: datetime,
    response: dict,
) -> None:
    event_id = str(uuid4())
    payload = json.dumps(
        {
            "event_id": event_id,
            "family_id": actor.family_id,
            "actor_id": actor.actor_id,
            "resource_id": resource_id,
            "occurred_at": occurred_at.isoformat(),
            "response": response,
        },
        ensure_ascii=False,
    )
    await connection.execute(
        text(
            """
            insert into outbox_events(
              aggregate_type,aggregate_id,event_name,event_version,event_id,
              correlation_id,payload,occurred_at
            ) values (
              :resource_type,:resource_id,:event_name,1,:event_id,
              :correlation_id,cast(:payload as jsonb),:occurred_at
            )
            """
        ),
        {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "event_name": event_name,
            "event_id": event_id,
            "correlation_id": correlation_id,
            "payload": payload,
            "occurred_at": occurred_at,
        },
    )


async def _store_idempotency_response(
    connection: AsyncConnection, key: str, response: dict
) -> None:
    await connection.execute(
        text(
            """
            update idempotency_keys set response_code=200,
              response_body=cast(:response_body as jsonb)
            where idempotency_key=:key
            """
        ),
        {"key": key, "response_body": json.dumps(response, ensure_ascii=False)},
    )
