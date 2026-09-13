"""Canonical single-connection wiring for `BeliefStateQueryService` (AIFAMILY-WM-005B, PART P).

Nothing stops a caller from constructing `PostgresWorldStateRepository`,
`PostgresConflictRepository` and `PostgresUnknownRepository` against three
*different* connections and handing them to `BeliefStateQueryService` — that
would let the Atom Store, Conflict Store and Unknown Store reads land in
different transactions, reintroducing exactly the read-consistency risk
AIFAMILY-WM-005B closes at the semantic layer (one `read_at`). This module is
the one production entry point that makes the single-connection invariant
the easy, obvious path instead of something every caller has to remember.

Lives under `backend/apps/family_api/`, not `backend/intelligence/`:
`tests/architecture/test_ai_runtime_isolation.py` forbids any module under
`backend/intelligence/` from importing a concrete `*Repository` symbol
(even one of this package's own persistence adapters, not a business
domain's) — `BeliefStateQueryService` itself stays inside
`backend/intelligence/context_engine/` using structural `Protocol` types;
this file is the wiring point *outside* that boundary that actually
constructs the concrete repositories, mirroring where
`growth_plan_ai_wiring.py` sits relative to the AI Runtime it wires.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncConnection

from backend.intelligence.context_engine.belief_state_query_service import (
    BeliefStateQueryService,
)
from backend.intelligence.context_engine.postgres_conflict_repository import (
    PostgresConflictRepository,
)
from backend.intelligence.context_engine.postgres_unknown_repository import (
    PostgresUnknownRepository,
)
from backend.intelligence.context_engine.postgres_world_state_repository import (
    PostgresWorldStateRepository,
)


@asynccontextmanager
async def build_belief_state_query_service(
    connection: AsyncConnection,
) -> AsyncIterator[BeliefStateQueryService]:
    """The one caller-facing way to get a `BeliefStateQueryService` backed
    by real PostgreSQL — all three repositories share `connection`, so a
    `get_current_belief_state()` call reads the Atom/Conflict/Unknown
    stores within one transaction boundary. The caller still owns
    `connection`'s lifecycle (open/commit/close); this only wires the three
    repositories onto it."""

    yield BeliefStateQueryService(
        world_state_repository=PostgresWorldStateRepository(connection),
        conflict_repository=PostgresConflictRepository(connection),
        unknown_repository=PostgresUnknownRepository(connection),
    )


__all__ = ["build_belief_state_query_service"]
