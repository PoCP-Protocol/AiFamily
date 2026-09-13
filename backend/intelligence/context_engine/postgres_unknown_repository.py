"""PostgreSQL durable store for `UnknownState` (AIFAMILY-WM-004C, B10).

`UnknownState` is the only canonical ignorance object in this kernel — this
module persists that one representation; it does not define a second. The
`unknown_key` UNIQUE constraint (schema: `0084_ai_family_world_unknowns.py`)
is what makes duplicate generation (same cognitive gap under different
wording, or a genuine concurrent race) collapse to one row at the database
layer, mirroring the `projection_key` discipline in
`postgres_world_state_repository.py`.

Resolution discipline (B11): `resolve()` requires `resolution_refs` to be
non-empty and, critically, disjoint from the Unknown's own `blocking_refs` —
an AI citing the very evidence that was already insufficient to answer the
question is not "new evidence", it is self-resolution, and is rejected here
rather than trusted to the caller's judgement.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from .contracts import ContextContractError, ContextScope, ContextScopeError, DataClass
from .world_state import UnknownState, UnknownStatus

_INSERT_UNKNOWN_SQL = text(
    """
    INSERT INTO ai_family_world_unknowns (
        unknown_id, tenant_id, family_id, subject_ids, question,
        why_it_matters, target_predicate, decision_impact, answerability,
        urgency, preferred_source, blocking_refs, unknown_key, source_refs,
        priority, status, resolution_refs, purpose, consent_version,
        data_class, created_at, resolved_at
    ) VALUES (
        :unknown_id, :tenant_id, :family_id, :subject_ids, :question,
        :why_it_matters, :target_predicate, :decision_impact, :answerability,
        :urgency, :preferred_source, :blocking_refs, :unknown_key, :source_refs,
        :priority, :status, :resolution_refs, :purpose, :consent_version,
        :data_class, :created_at, :resolved_at
    )
    ON CONFLICT (unknown_key) DO NOTHING
    RETURNING unknown_id
    """
)

_SELECT_BY_UNKNOWN_KEY_SQL = text(
    "SELECT * FROM ai_family_world_unknowns WHERE unknown_key = :unknown_key"
)

_SELECT_BY_ID_SQL = text("SELECT * FROM ai_family_world_unknowns WHERE unknown_id = :unknown_id")

_SELECT_OPEN_BY_SCOPE_SQL = text(
    """
    SELECT * FROM ai_family_world_unknowns
    WHERE tenant_id = :tenant_id AND family_id = :family_id AND status = 'OPEN'
    ORDER BY created_at ASC
    """
)

_UPDATE_STATUS_SQL = text(
    """
    UPDATE ai_family_world_unknowns
    SET status = :status, resolution_refs = :resolution_refs, resolved_at = :resolved_at
    WHERE unknown_id = :unknown_id
    """
)


class UnknownPersistenceError(ValueError):
    """Raised on identity conflicts or resolution-discipline violations."""


class UnknownIdentityConflictError(UnknownPersistenceError):
    """Same `unknown_key` already exists with different core content —
    should not happen (identity is derived from that same content), kept as
    a fail-closed guard rather than a silent overwrite."""


class AiSelfResolutionRejectedError(UnknownPersistenceError):
    """B11: an Unknown cannot be resolved using only the evidence that was
    already insufficient to answer it (its own `blocking_refs`) — resolution
    requires genuinely new evidence refs."""


class PostgresUnknownRepository:
    """Async Unknown Store adapter, scoped to one connection per instance."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def create(self, unknown: UnknownState) -> UnknownState:
        if unknown.unknown_key is None:
            raise ContextContractError("UNKNOWN_KEY_REQUIRED_FOR_PERSISTENCE")

        params = {
            "unknown_id": unknown.unknown_id,
            "tenant_id": unknown.scope.tenant_id,
            "family_id": unknown.scope.family_id,
            "subject_ids": _dump(list(unknown.subject_ids)),
            "question": unknown.question,
            "why_it_matters": unknown.why_it_matters,
            "target_predicate": unknown.target_predicate,
            "decision_impact": unknown.decision_impact,
            "answerability": unknown.answerability,
            "urgency": unknown.urgency,
            "preferred_source": unknown.preferred_source,
            "blocking_refs": _dump(list(unknown.blocking_refs)),
            "unknown_key": unknown.unknown_key,
            "source_refs": _dump(list(unknown.source_refs)),
            "priority": unknown.priority,
            "status": unknown.status.value,
            "resolution_refs": _dump(list(unknown.resolution_refs)),
            "purpose": unknown.scope.purpose,
            "consent_version": unknown.scope.consent_version,
            "data_class": unknown.scope.data_class.value,
            "created_at": unknown.created_at,
            "resolved_at": unknown.resolved_at,
        }

        try:
            async with self._connection.begin_nested():
                result = await self._connection.execute(_INSERT_UNKNOWN_SQL, params)
        except IntegrityError:
            return await self._resolve_against_existing(unknown)

        inserted_row = result.mappings().one_or_none()
        if inserted_row is not None:
            return unknown
        return await self._resolve_against_existing(unknown)

    async def _resolve_against_existing(self, unknown: UnknownState) -> UnknownState:
        existing = await self._connection.execute(
            _SELECT_BY_UNKNOWN_KEY_SQL, {"unknown_key": unknown.unknown_key}
        )
        existing_row = existing.mappings().one_or_none()
        if existing_row is None:
            raise UnknownPersistenceError(
                f"unknown_key {unknown.unknown_key} vanished between insert and lookup"
            )
        mapping = dict(existing_row)
        return _row_to_unknown(mapping, _storage_scope_for_row(mapping))

    async def get(self, unknown_id: str, *, scope: ContextScope) -> UnknownState | None:
        result = await self._connection.execute(_SELECT_BY_ID_SQL, {"unknown_id": unknown_id})
        row = result.mappings().one_or_none()
        if row is None:
            return None
        mapping = dict(row)
        _assert_row_readable_by(mapping, scope)
        return _row_to_unknown(mapping, _storage_scope_for_row(mapping))

    async def list_open(self, *, scope: ContextScope) -> tuple[UnknownState, ...]:
        scope.assert_active()
        result = await self._connection.execute(
            _SELECT_OPEN_BY_SCOPE_SQL,
            {"tenant_id": scope.tenant_id, "family_id": scope.family_id},
        )
        unknowns: list[UnknownState] = []
        for row in result.mappings().all():
            mapping = dict(row)
            _assert_row_readable_by(mapping, scope)
            unknowns.append(_row_to_unknown(mapping, _storage_scope_for_row(mapping)))
        return tuple(unknowns)

    async def resolve(
        self,
        unknown_id: str,
        *,
        scope: ContextScope,
        resolution_refs: tuple[str, ...],
        resolved_at: datetime,
    ) -> UnknownState:
        """B11: `resolution_refs` must be non-empty and must not be a subset
        of the Unknown's own `blocking_refs` — citing only the evidence that
        was already there when the question was raised is not resolution,
        it is the AI closing its own gap without new information."""

        if not resolution_refs:
            raise ContextContractError("RESOLVED_UNKNOWN_REQUIRES_RESOLUTION_REFS")

        current = await self.get(unknown_id, scope=scope)
        if current is None:
            raise UnknownPersistenceError(f"unknown_id {unknown_id} not found")

        if set(resolution_refs) <= set(current.blocking_refs):
            raise AiSelfResolutionRejectedError(
                "UNKNOWN_SELF_RESOLUTION_REJECTED: resolution_refs must include "
                "evidence beyond the Unknown's own blocking_refs"
            )

        await self._connection.execute(
            _UPDATE_STATUS_SQL,
            {
                "unknown_id": unknown_id,
                "status": UnknownStatus.RESOLVED.value,
                "resolution_refs": _dump(list(resolution_refs)),
                "resolved_at": resolved_at,
            },
        )
        return await self.get(unknown_id, scope=scope)  # type: ignore[return-value]

    async def dismiss(self, unknown_id: str, *, scope: ContextScope) -> UnknownState:
        current = await self.get(unknown_id, scope=scope)
        if current is None:
            raise UnknownPersistenceError(f"unknown_id {unknown_id} not found")
        await self._connection.execute(
            _UPDATE_STATUS_SQL,
            {
                "unknown_id": unknown_id,
                "status": UnknownStatus.DISMISSED.value,
                "resolution_refs": _dump([]),
                "resolved_at": None,
            },
        )
        return await self.get(unknown_id, scope=scope)  # type: ignore[return-value]

    async def mark_stale(self, unknown_id: str, *, scope: ContextScope) -> UnknownState:
        current = await self.get(unknown_id, scope=scope)
        if current is None:
            raise UnknownPersistenceError(f"unknown_id {unknown_id} not found")
        await self._connection.execute(
            _UPDATE_STATUS_SQL,
            {
                "unknown_id": unknown_id,
                "status": UnknownStatus.STALE.value,
                "resolution_refs": _dump([]),
                "resolved_at": None,
            },
        )
        return await self.get(unknown_id, scope=scope)  # type: ignore[return-value]


def _dump(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _load(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = json.loads(value)
    return tuple(value)


def _assert_row_readable_by(mapping: dict, scope: ContextScope) -> None:
    scope.assert_active()
    if mapping["tenant_id"] != scope.tenant_id:
        raise ContextScopeError("CROSS_TENANT_UNKNOWN_READ")
    if mapping["family_id"] != scope.family_id:
        raise ContextScopeError("CROSS_FAMILY_UNKNOWN_READ")
    if mapping["purpose"] != scope.purpose:
        raise ContextContractError("UNKNOWN_PURPOSE_MISMATCH")
    if mapping["consent_version"] != scope.consent_version:
        raise ContextContractError("UNKNOWN_CONSENT_VERSION_MISMATCH")
    if not scope.consent_granted:
        raise ContextContractError("CONSENT_REVOKED")


def _storage_scope_for_row(mapping: dict) -> ContextScope:
    """Rebuild the minimal scope a persisted Unknown needs to satisfy its
    own `__post_init__` (its `subject_ids` must be a subset of
    `scope.subject_ids`) — mirrors `postgres_world_state_repository.
    _storage_scope_for_row`. Not an authorization decision:
    `_assert_row_readable_by` already made that decision against the
    caller's real scope before this is called."""

    subject_ids = _load(mapping["subject_ids"])
    return ContextScope(
        tenant_id=mapping["tenant_id"],
        region_id="CN",
        family_id=mapping["family_id"],
        subject_ids=subject_ids,
        purpose=mapping["purpose"],
        consent_version=mapping["consent_version"],
        consent_granted=True,
        data_class=DataClass(mapping["data_class"]),
        locale="zh-CN",
        deletion_ref=f"delete:{mapping['family_id']}",
        correlation_id="unknown-storage-scope",
        causation_id="unknown-storage-scope",
    )


def _row_to_unknown(mapping: dict, scope: ContextScope) -> UnknownState:
    return UnknownState(
        unknown_id=mapping["unknown_id"],
        scope=scope,
        subject_ids=_load(mapping["subject_ids"]),
        question=mapping["question"],
        why_it_matters=mapping["why_it_matters"],
        target_predicate=mapping["target_predicate"],
        decision_impact=mapping["decision_impact"],
        answerability=mapping["answerability"],
        urgency=mapping["urgency"],
        preferred_source=mapping["preferred_source"],
        blocking_refs=_load(mapping["blocking_refs"]),
        unknown_key=mapping["unknown_key"],
        source_refs=_load(mapping["source_refs"]),
        priority=mapping["priority"],
        status=UnknownStatus(mapping["status"]),
        resolution_refs=_load(mapping["resolution_refs"]),
        created_at=mapping["created_at"],
        resolved_at=mapping["resolved_at"],
    )


__all__ = [
    "AiSelfResolutionRejectedError",
    "PostgresUnknownRepository",
    "UnknownIdentityConflictError",
    "UnknownPersistenceError",
]
