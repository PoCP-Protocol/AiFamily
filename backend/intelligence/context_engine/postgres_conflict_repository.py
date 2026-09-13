"""PostgreSQL store for `WorldStateConflict` (AIFAMILY-WM-004A).

Schema is created by
``database/migrations/versions/0081_ai_family_world_conflicts.py``. One
repository instance owns one ``AsyncConnection``; the caller owns the
transaction boundary (mirrors ``postgres_world_state_repository.py``).

Append-then-update-status only: a conflict's identity (`conflict_id`,
`atom_id_a`/`atom_id_b`, `conflict_type`) never changes after insert — only
`status`/`resolution_note` can be updated, and only by a human/policy
decision (never by this module deciding who was right).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .conflict_engine import ConflictStatus, ConflictType, WorldStateConflict
from .contracts import ContextContractError, ContextScope, ContextScopeError

_INSERT_CONFLICT_SQL = text(
    """
    INSERT INTO ai_family_world_conflicts (
        conflict_id, tenant_id, family_id, predicate, atom_id_a, atom_id_b,
        conflict_type, status, resolution_note, purpose, consent_version,
        data_class, detected_at
    ) VALUES (
        :conflict_id, :tenant_id, :family_id, :predicate, :atom_id_a, :atom_id_b,
        :conflict_type, :status, :resolution_note, :purpose, :consent_version,
        :data_class, :detected_at
    )
    ON CONFLICT (conflict_id) DO NOTHING
    """
)

_SELECT_BY_SCOPE_SQL = text(
    """
    SELECT * FROM ai_family_world_conflicts
    WHERE tenant_id = :tenant_id AND family_id = :family_id
    ORDER BY detected_at ASC
    """
)


class PostgresConflictRepository:
    """Async store for detected conflicts, scoped to one connection."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def append_conflict(self, conflict: WorldStateConflict) -> None:
        """Persist a detected conflict. Idempotent by `conflict_id` (a
        deterministic function of the two atom ids) — detecting the same
        pair twice does not create a duplicate row."""

        await self._connection.execute(
            _INSERT_CONFLICT_SQL,
            {
                "conflict_id": conflict.conflict_id,
                "tenant_id": conflict.scope.tenant_id,
                "family_id": conflict.scope.family_id,
                "predicate": conflict.predicate,
                "atom_id_a": conflict.atom_ids[0],
                "atom_id_b": conflict.atom_ids[1],
                "conflict_type": conflict.conflict_type.value,
                "status": conflict.status.value,
                "resolution_note": conflict.resolution_note,
                "purpose": conflict.scope.purpose,
                "consent_version": conflict.scope.consent_version,
                "data_class": conflict.scope.data_class.value,
                "detected_at": conflict.detected_at,
            },
        )

    async def list_conflicts(self, *, scope: ContextScope) -> tuple[WorldStateConflict, ...]:
        scope.assert_active()
        result = await self._connection.execute(
            _SELECT_BY_SCOPE_SQL,
            {"tenant_id": scope.tenant_id, "family_id": scope.family_id},
        )
        conflicts: list[WorldStateConflict] = []
        for row in result.mappings().all():
            mapping = dict(row)
            if mapping["purpose"] != scope.purpose:
                raise ContextContractError("WORLD_STATE_PURPOSE_MISMATCH")
            if mapping["consent_version"] != scope.consent_version:
                raise ContextContractError("WORLD_STATE_CONSENT_VERSION_MISMATCH")
            if mapping["tenant_id"] != scope.tenant_id or mapping["family_id"] != scope.family_id:
                raise ContextScopeError("CROSS_FAMILY_WORLD_STATE_READ")
            conflicts.append(
                WorldStateConflict(
                    conflict_id=mapping["conflict_id"],
                    scope=scope,
                    predicate=mapping["predicate"],
                    atom_ids=(mapping["atom_id_a"], mapping["atom_id_b"]),
                    conflict_type=ConflictType(mapping["conflict_type"]),
                    detected_at=mapping["detected_at"],
                    status=ConflictStatus(mapping["status"]),
                    resolution_note=mapping["resolution_note"],
                )
            )
        return tuple(conflicts)


__all__ = ["PostgresConflictRepository"]
