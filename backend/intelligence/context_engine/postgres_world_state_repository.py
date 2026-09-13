"""PostgreSQL Atom Store for the Family World State Kernel (AIFAMILY-WM-001,
made source-idempotent in AIFAMILY-WM-003.6).

Schema is created by
``database/migrations/versions/0080_ai_family_world_atoms.py`` (+
``0082_ai_family_world_atoms_projection_identity.py`` for the
``projection_key``/``semantic_fingerprint``/``projection_version`` columns).
One repository instance owns one ``AsyncConnection``; the caller owns the
transaction boundary (mirrors ``backend/domains/family_need/infrastructure/
postgres_repository.py``).

Append-only by construction: there is no `update_atom` method. Predicate
governance is enforced here, not inside `WorldStateAtom.__post_init__` — see
`predicate_registry.py` module docstring for why.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from .contracts import ContextContractError, ContextScope, ContextScopeError, DataClass
from .predicate_registry import PredicateRegistry
from .projection_identity import build_projection_key, build_semantic_fingerprint
from .world_state import (
    BeliefBand,
    UncertaintyBand,
    WorldStateActorType,
    WorldStateAtom,
    WorldStateAtomStatus,
    WorldStateEpistemicKind,
)

_INSERT_ATOM_SQL = text(
    """
    INSERT INTO ai_family_world_atoms (
        atom_id, tenant_id, family_id, subject_ids, epistemic_kind,
        predicate, value_ref, asserted_by, attributed_actor_type,
        provenance, source_refs, evidence_refs, observed_at, valid_from,
        valid_until, recorded_at, status, supersedes, purpose,
        consent_version, data_class, projection_key, semantic_fingerprint,
        projection_version, support_level, contradiction_level, uncertainty
    ) VALUES (
        :atom_id, :tenant_id, :family_id, :subject_ids, :epistemic_kind,
        :predicate, :value_ref, :asserted_by, :attributed_actor_type,
        :provenance, :source_refs, :evidence_refs, :observed_at, :valid_from,
        :valid_until, :recorded_at, :status, :supersedes, :purpose,
        :consent_version, :data_class, :projection_key, :semantic_fingerprint,
        :projection_version, :support_level, :contradiction_level, :uncertainty
    )
    ON CONFLICT (projection_key) DO NOTHING
    RETURNING atom_id
    """
)

_SELECT_BY_PROJECTION_KEY_SQL = text(
    "SELECT * FROM ai_family_world_atoms WHERE projection_key = :projection_key"
)

_SELECT_BY_SCOPE_SQL = text(
    """
    SELECT * FROM ai_family_world_atoms
    WHERE tenant_id = :tenant_id AND family_id = :family_id
      AND status = 'ACTIVE'
      AND valid_from <= :valid_at
      AND (valid_until IS NULL OR valid_until > :valid_at)
      AND recorded_at <= :known_at
    ORDER BY recorded_at ASC
    """
)

_SELECT_BY_ID_SQL = text("SELECT * FROM ai_family_world_atoms WHERE atom_id = :atom_id")


class WorldStatePersistenceError(ValueError):
    """Raised on predicate governance violations or storage-level conflicts."""


class ProjectionIdentityConflictError(WorldStatePersistenceError):
    """Raised when the same authoritative source (same `projection_key`) is
    projected again with *different* asserted content (a different
    `semantic_fingerprint`). This must never be silently resolved by
    overwriting either version — see AIFAMILY-WM-003.6 §6 Case C."""


class AppendAtomOutcome(StrEnum):
    INSERTED = "INSERTED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


@dataclass(frozen=True, slots=True)
class AppendAtomResult:
    outcome: AppendAtomOutcome
    atom_id: str
    projection_key: str


class PostgresWorldStateRepository:
    """Async Atom Store adapter, scoped to one connection per instance."""

    def __init__(
        self,
        connection: AsyncConnection,
        *,
        predicate_registry: PredicateRegistry | None = None,
    ) -> None:
        self._connection = connection
        self._predicate_registry = predicate_registry or PredicateRegistry.from_yaml()

    async def append_atom(
        self,
        atom: WorldStateAtom,
        *,
        source_ref: str,
        source_version: str,
        projection_version: str,
    ) -> AppendAtomResult:
        """Persist an atom under a semantic projection identity.

        `source_ref`/`source_version` identify the authoritative domain
        record this atom was projected from (see each adapter's docstring
        for what stable identity it uses — never `datetime.now()`, never a
        random value); `projection_version` identifies the adapter contract
        version. None of the three may be derived from `atom.atom_id` or any
        timestamp — `projection_key`/`semantic_fingerprint` are computed
        entirely by `projection_identity.py` from these plus the atom's own
        semantic fields.

        Returns `INSERTED` the first time a given projection identity is
        seen, `IDEMPOTENT_REPLAY` (with the *existing* row's `atom_id`, not
        the caller's) if the exact same source has already been projected
        with identical content, and raises `ProjectionIdentityConflictError`
        if the same source now claims different content — never overwrites.
        """

        self._predicate_registry.validate(atom.predicate)
        projection_key = build_projection_key(
            tenant_id=atom.scope.tenant_id,
            family_id=atom.scope.family_id,
            subject_ids=atom.subject_ids,
            predicate=atom.predicate,
            epistemic_kind=atom.epistemic_kind.value,
            source_ref=source_ref,
            source_version=source_version,
            projection_version=projection_version,
        )
        semantic_fingerprint = build_semantic_fingerprint(
            family_id=atom.scope.family_id,
            subject_ids=atom.subject_ids,
            predicate=atom.predicate,
            epistemic_kind=atom.epistemic_kind.value,
            value_ref=atom.value_ref,
            asserted_by=atom.asserted_by,
            valid_from=atom.valid_from,
            valid_until=atom.valid_until,
            source_refs=atom.source_refs,
            evidence_refs=atom.evidence_refs,
            data_class=atom.scope.data_class.value,
            projection_version=projection_version,
            support_level=atom.support_level.value if atom.support_level else None,
            contradiction_level=(
                atom.contradiction_level.value if atom.contradiction_level else None
            ),
            uncertainty=atom.uncertainty.value if atom.uncertainty else None,
        )

        params = {
            "atom_id": atom.atom_id,
            "tenant_id": atom.scope.tenant_id,
            "family_id": atom.scope.family_id,
            "subject_ids": _dump(list(atom.subject_ids)),
            "epistemic_kind": atom.epistemic_kind.value,
            "predicate": atom.predicate,
            "value_ref": atom.value_ref,
            "asserted_by": atom.asserted_by,
            "attributed_actor_type": atom.attributed_actor_type.value,
            "provenance": atom.provenance,
            "source_refs": _dump(list(atom.source_refs)),
            "evidence_refs": _dump(list(atom.evidence_refs)),
            "observed_at": atom.observed_at,
            "valid_from": atom.valid_from,
            "valid_until": atom.valid_until,
            "recorded_at": atom.recorded_at,
            "status": atom.status.value,
            "supersedes": atom.supersedes,
            "purpose": atom.scope.purpose,
            "consent_version": atom.scope.consent_version,
            "data_class": atom.scope.data_class.value,
            "projection_key": projection_key,
            "semantic_fingerprint": semantic_fingerprint,
            "projection_version": projection_version,
            "support_level": atom.support_level.value if atom.support_level else None,
            "contradiction_level": (
                atom.contradiction_level.value if atom.contradiction_level else None
            ),
            "uncertainty": atom.uncertainty.value if atom.uncertainty else None,
        }

        try:
            # A SAVEPOINT (nested transaction), not the outer transaction:
            # this repository does not own the transaction boundary (see
            # module docstring), so a lost race here must only unwind this
            # statement, never the caller's whole transaction.
            async with self._connection.begin_nested():
                result = await self._connection.execute(_INSERT_ATOM_SQL, params)
        except IntegrityError:
            # A concurrent transaction won the race between our INSERT
            # attempt and its own — ON CONFLICT DO NOTHING only suppresses
            # the conflict when postgres can prove no trigger/deferred
            # constraint interference, so a real race can still surface as
            # an IntegrityError instead of an empty RETURNING set. Resolve
            # it exactly the same way as the ON CONFLICT DO NOTHING path.
            return await self._resolve_against_existing(projection_key, semantic_fingerprint, atom)

        inserted_row = result.mappings().one_or_none()
        if inserted_row is not None:
            return AppendAtomResult(
                outcome=AppendAtomOutcome.INSERTED,
                atom_id=atom.atom_id,
                projection_key=projection_key,
            )
        return await self._resolve_against_existing(projection_key, semantic_fingerprint, atom)

    async def _resolve_against_existing(
        self,
        projection_key: str,
        semantic_fingerprint: str,
        atom: WorldStateAtom,
    ) -> AppendAtomResult:
        existing = await self._connection.execute(
            _SELECT_BY_PROJECTION_KEY_SQL, {"projection_key": projection_key}
        )
        existing_row = existing.mappings().one_or_none()
        if existing_row is None:
            # Should not happen: ON CONFLICT DO NOTHING implies a row exists.
            raise WorldStatePersistenceError(
                f"projection_key {projection_key} vanished between insert and lookup"
            )
        if existing_row["semantic_fingerprint"] != semantic_fingerprint:
            raise ProjectionIdentityConflictError(
                "world_state_projection_identity_conflict: "
                f"projection_key={projection_key} atom_id={atom.atom_id} "
                "claims different content than the already-stored projection "
                f"(existing atom_id={existing_row['atom_id']})"
            )
        return AppendAtomResult(
            outcome=AppendAtomOutcome.IDEMPOTENT_REPLAY,
            atom_id=existing_row["atom_id"],
            projection_key=projection_key,
        )

    async def get_atom(self, atom_id: str, *, scope: ContextScope) -> WorldStateAtom | None:
        result = await self._connection.execute(_SELECT_BY_ID_SQL, {"atom_id": atom_id})
        row = result.mappings().one_or_none()
        if row is None:
            return None
        mapping = dict(row)
        _assert_row_readable_by(mapping, scope)
        return _row_to_atom(mapping, _storage_scope_for_row(mapping))

    async def get_state(
        self,
        *,
        scope: ContextScope,
        valid_at: datetime | None = None,
        known_at: datetime | None = None,
    ) -> tuple[WorldStateAtom, ...]:
        """Bitemporal read: `valid_at` asks "what was true then", `known_at`
        asks "what had AiFamily already learned by then" — the two may differ
        and callers may legitimately want either one independently.

        A row whose `subject_ids` only partially overlaps `scope.subject_ids`
        (some in scope, some not) is skipped rather than raised on — a
        multi-subject snapshot query must be able to narrow to what it can
        see without failing outright on every atom that also touches someone
        outside the caller's scope. Full authorization (tenant/family/
        purpose/consent) is still enforced per row.
        """

        scope.assert_active()
        resolved_valid_at = valid_at or datetime.now(UTC)
        resolved_known_at = known_at or datetime.now(UTC)
        result = await self._connection.execute(
            _SELECT_BY_SCOPE_SQL,
            {
                "tenant_id": scope.tenant_id,
                "family_id": scope.family_id,
                "valid_at": resolved_valid_at,
                "known_at": resolved_known_at,
            },
        )
        atoms: list[WorldStateAtom] = []
        for row in result.mappings().all():
            mapping = dict(row)
            row_subject_ids = _load(mapping["subject_ids"])
            if not set(row_subject_ids).issubset(set(scope.subject_ids)):
                continue
            _assert_row_readable_by(mapping, scope)
            atoms.append(_row_to_atom(mapping, _storage_scope_for_row(mapping)))
        return tuple(atoms)


def _dump(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _load(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = json.loads(value)
    return tuple(value)


def _assert_row_readable_by(mapping: dict, scope: ContextScope) -> None:
    """Authorization check against the row's *own* recorded envelope —
    deliberately not via `WorldStateAtom.assert_readable_by`, which requires
    the atom's `subject_ids` to already be a subset of the scope it was
    constructed with (a property this function establishes, not assumes)."""

    scope.assert_active()
    if mapping["tenant_id"] != scope.tenant_id:
        raise ContextScopeError("CROSS_TENANT_WORLD_STATE_READ")
    if mapping["family_id"] != scope.family_id:
        raise ContextScopeError("CROSS_FAMILY_WORLD_STATE_READ")
    if mapping["purpose"] != scope.purpose:
        raise ContextContractError("WORLD_STATE_PURPOSE_MISMATCH")
    if mapping["consent_version"] != scope.consent_version:
        raise ContextContractError("WORLD_STATE_CONSENT_VERSION_MISMATCH")
    if not scope.consent_granted:
        raise ContextContractError("CONSENT_REVOKED")


def _storage_scope_for_row(mapping: dict) -> ContextScope:
    """Rebuild the minimal scope a persisted atom needs to satisfy its own
    `__post_init__` (its `subject_ids` must be a subset of `scope.subject_ids`).
    This is not an authorization decision — `_assert_row_readable_by` already
    made that decision against the caller's real scope before this is called.
    """

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
        correlation_id="world-state-storage-scope",
        causation_id="world-state-storage-scope",
    )


def _row_to_atom(mapping: dict, scope: ContextScope) -> WorldStateAtom:
    return WorldStateAtom(
        atom_id=mapping["atom_id"],
        scope=scope,
        subject_ids=_load(mapping["subject_ids"]),
        epistemic_kind=WorldStateEpistemicKind(mapping["epistemic_kind"]),
        predicate=mapping["predicate"],
        value_ref=mapping["value_ref"],
        asserted_by=mapping["asserted_by"],
        attributed_actor_type=WorldStateActorType(mapping["attributed_actor_type"]),
        provenance=mapping["provenance"],
        observed_at=mapping["observed_at"],
        recorded_at=mapping["recorded_at"],
        valid_from=mapping["valid_from"],
        valid_until=mapping["valid_until"],
        source_refs=_load(mapping["source_refs"]),
        evidence_refs=_load(mapping["evidence_refs"]),
        status=WorldStateAtomStatus(mapping["status"]),
        supersedes=mapping["supersedes"],
        support_level=BeliefBand(mapping["support_level"])
        if mapping.get("support_level")
        else None,
        contradiction_level=(
            BeliefBand(mapping["contradiction_level"])
            if mapping.get("contradiction_level")
            else None
        ),
        uncertainty=(
            UncertaintyBand(mapping["uncertainty"]) if mapping.get("uncertainty") else None
        ),
    )


__all__ = [
    "AppendAtomOutcome",
    "AppendAtomResult",
    "PostgresWorldStateRepository",
    "ProjectionIdentityConflictError",
    "WorldStatePersistenceError",
]
