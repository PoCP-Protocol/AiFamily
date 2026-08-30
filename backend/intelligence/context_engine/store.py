"""In-memory Context Broker adapter.

The adapter is intentionally small, but it enforces the same scope and
retention checks a durable implementation must preserve.  It stores technical
observations/snapshots only; no domain repository or canonical fact is touched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .contracts import (
    ContextContractError,
    ContextScope,
    ContextScopeError,
    ContextSnapshot,
    StateObservation,
)


class ContextBroker:
    """Build and read immutable, purpose-scoped context projections."""

    def __init__(self) -> None:
        self._observations: dict[tuple[str, str], StateObservation] = {}
        self._snapshots: dict[str, ContextSnapshot] = {}
        self._snapshot_sequence = 0

    def append(self, observation: StateObservation) -> None:
        """Append one observation; duplicate IDs are isolated per tenant."""

        if not isinstance(observation, StateObservation):
            raise ContextContractError("STATE_OBSERVATION_REQUIRED")
        key = (observation.tenant_id, observation.observation_id)
        if key in self._observations:
            raise ContextContractError("OBSERVATION_ID_ALREADY_EXISTS")
        self._observations[key] = observation

    def snapshot(
        self,
        tenant_id: str | None = None,
        subject_id: str | None = None,
        *,
        scope: ContextScope | None = None,
        now: datetime | None = None,
        snapshot_ttl: timedelta = timedelta(minutes=15),
    ) -> ContextSnapshot:
        """Return a minimal projection for an explicit scope.

        ``tenant_id`` and ``subject_id`` remain accepted as convenience filters,
        but a complete ``ContextScope`` is mandatory.  This prevents a caller
        from accidentally creating a global/default-family context.
        """

        if scope is None:
            raise ContextContractError("CONTEXT_SCOPE_REQUIRED")
        scope.assert_active()
        if tenant_id is not None and tenant_id != scope.tenant_id:
            raise ContextScopeError("CROSS_TENANT_CONTEXT_QUERY")
        if subject_id is not None and subject_id not in scope.subject_ids:
            raise ContextScopeError("CONTEXT_SUBJECT_QUERY_DENIED")
        if snapshot_ttl <= timedelta(0):
            raise ContextContractError("SNAPSHOT_TTL_INVALID")
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ContextContractError("snapshot timestamp requires a timezone")
        selected = []
        for item in self._observations.values():
            if item.tenant_id != scope.tenant_id:
                continue
            if item.family_id != scope.family_id:
                continue
            if item.subject_id not in scope.subject_ids:
                continue
            if subject_id is not None and item.subject_id != subject_id:
                continue
            if item.purpose != scope.purpose or item.consent_version != scope.consent_version:
                continue
            if not item.consent_granted or item.is_expired(current):
                continue
            selected.append(item)
        observations = tuple(
            sorted(selected, key=lambda item: (item.observed_at, item.observation_id))
        )
        self._snapshot_sequence += 1
        snapshot = ContextSnapshot(
            snapshot_ref=(
                f"context:{scope.tenant_id}:{scope.family_id}:"
                f"{current.isoformat()}:{self._snapshot_sequence}"
            ),
            scope=scope,
            generated_at=current,
            observations=observations,
            expires_at=current + snapshot_ttl,
            provenance="context-broker:state-observation",
            deletion_ref=scope.deletion_ref,
            source_refs=tuple(ref for item in observations for ref in item.evidence_refs),
        )
        self._snapshots[snapshot.snapshot_ref] = snapshot
        return snapshot

    def read(
        self,
        snapshot_ref: str,
        scope: ContextScope,
        *,
        now: datetime | None = None,
    ) -> ContextSnapshot:
        """Read a prior snapshot only inside the same active scope."""

        scope.assert_active()
        snapshot = self._snapshots.get(snapshot_ref)
        if snapshot is None:
            raise ContextContractError("CONTEXT_SNAPSHOT_NOT_FOUND")
        if snapshot.tenant_id != scope.tenant_id:
            raise ContextScopeError("CROSS_TENANT_CONTEXT_SNAPSHOT")
        if snapshot.family_id != scope.family_id:
            raise ContextScopeError("CROSS_FAMILY_CONTEXT_SNAPSHOT")
        if frozenset(snapshot.subject_ids) != frozenset(scope.subject_ids):
            raise ContextScopeError("CROSS_SUBJECT_CONTEXT_SNAPSHOT")
        if snapshot.purpose != scope.purpose:
            raise ContextContractError("CONTEXT_PURPOSE_MISMATCH")
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            raise ContextContractError("snapshot timestamp requires a timezone")
        if snapshot.expires_at <= moment:
            raise ContextContractError("CONTEXT_SNAPSHOT_EXPIRED")
        return snapshot

    def delete_subject(self, tenant_id: str, subject_id: str) -> int:
        """Delete observations and snapshots for one tenant-scoped subject."""

        observation_keys = [
            key
            for key, item in self._observations.items()
            if item.tenant_id == tenant_id and item.subject_id == subject_id
        ]
        for key in observation_keys:
            del self._observations[key]
        snapshot_refs = [
            ref
            for ref, snapshot in self._snapshots.items()
            if snapshot.tenant_id == tenant_id and subject_id in snapshot.subject_ids
        ]
        for ref in snapshot_refs:
            del self._snapshots[ref]
        return len(observation_keys)


class InMemoryContextStore(ContextBroker):
    """Backward-compatible name for the deterministic test adapter."""


__all__ = ["ContextBroker", "InMemoryContextStore"]
