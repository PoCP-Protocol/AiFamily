"""FamilyBeliefState Query Service (AIFAMILY-WM-005).

The one read path an Agent actually uses:

    Atom Store + Conflict Store + Unknown Store
        -> BeliefStateQueryService.get_current_belief_state(scope)
        -> FamilyBeliefState
        -> (future) Task Context Projector -> ContextSnapshot -> Agent

This module performs the I/O `belief_state.assemble_belief_state()`
deliberately does not: fetching atoms/conflicts/open-unknowns from their
three separate durable stores under one caller-supplied `ContextScope`, then
composing them into a single `FamilyBeliefState`. All three stores enforce
their own tenant/family/purpose/consent checks independently — this service
adds no additional authorization logic, only assembly.

Uses structural `Protocol` types for its repository dependencies rather than
importing the concrete `Postgres*Repository` classes, per the AI Runtime
isolation guard (`tests/architecture/test_ai_runtime_isolation.py`) — see
`unknown_resolution.py` for the same pattern and why it exists.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .belief_state import FamilyBeliefState, assemble_belief_state
from .conflict_engine import WorldStateConflict
from .contracts import ContextScope
from .world_state import FamilyWorldStateSnapshot, UnknownState, WorldStateAtom


class _WorldStateReader(Protocol):
    async def get_state(
        self,
        *,
        scope: ContextScope,
        valid_at: datetime | None = None,
        known_at: datetime | None = None,
    ) -> tuple[WorldStateAtom, ...]: ...


class _ConflictReader(Protocol):
    async def list_conflicts(self, *, scope: ContextScope) -> tuple[WorldStateConflict, ...]: ...


class _UnknownReader(Protocol):
    async def list_open(self, *, scope: ContextScope) -> tuple[UnknownState, ...]: ...


class BeliefStateQueryService:
    """Assembles a `FamilyBeliefState` from the three World Model stores.

    Holds no connection/session itself — each repository argument already
    owns its own `AsyncConnection` (mirrors how `PostgresWorldStateRepository`
    et al. are constructed elsewhere in this package), so this service is a
    pure composition point, not a new persistence boundary.
    """

    def __init__(
        self,
        *,
        world_state_repository: _WorldStateReader,
        conflict_repository: _ConflictReader,
        unknown_repository: _UnknownReader,
    ) -> None:
        self._world_state_repository = world_state_repository
        self._conflict_repository = conflict_repository
        self._unknown_repository = unknown_repository

    async def get_current_belief_state(
        self,
        *,
        scope: ContextScope,
        snapshot_ref: str,
        valid_at: datetime | None = None,
        known_at: datetime | None = None,
        generated_at: datetime,
    ) -> FamilyBeliefState:
        """`valid_at`/`known_at` default to "now" inside `get_state()` when
        omitted — see its own docstring for the bitemporal distinction. This
        method does not resolve that default itself so both repository and
        caller stay in agreement about what "now" means for a given call.
        """

        atoms = await self._world_state_repository.get_state(
            scope=scope, valid_at=valid_at, known_at=known_at
        )
        conflicts = await self._conflict_repository.list_conflicts(scope=scope)
        open_unknowns = await self._unknown_repository.list_open(scope=scope)

        snapshot = FamilyWorldStateSnapshot(
            snapshot_ref=snapshot_ref,
            scope=scope,
            as_of=valid_at or generated_at,
            generated_at=generated_at,
            atoms=atoms,
            unknowns=open_unknowns,
        )
        return assemble_belief_state(snapshot, conflicts=conflicts)


__all__ = ["BeliefStateQueryService"]
