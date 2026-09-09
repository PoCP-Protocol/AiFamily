"""Durable application service for the vertical family-growth pipeline.

The generator remains responsible for producing a governed Draft.  This
facade is the explicit boundary that persists that Draft through the existing
durable experience ledger and serves replay/delete from PostgreSQL-aware
adapters; it does not promote AI output to a business fact.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.intelligence.agi_vertical_durable import (
    DurableVerticalLedgerAdapter,
    DurableVerticalRun,
)
from backend.intelligence.agi_vertical_runtime import VerticalFamilyGrowthRuntime
from backend.intelligence.experience.run_http import RunReplaySnapshot, RunScope


@dataclass(frozen=True, slots=True)
class DurableVerticalFamilyGrowthService:
    runtime: VerticalFamilyGrowthRuntime
    durable_ledger: DurableVerticalLedgerAdapter

    async def run(self, *, scope: RunScope, **kwargs: object) -> DurableVerticalRun:
        entry = await self.runtime.run(**kwargs)  # type: ignore[arg-type]
        return await self.durable_ledger.save_entry(entry, scope=scope)

    async def replay(self, *, run_id: str, scope: RunScope) -> RunReplaySnapshot:
        return await self.durable_ledger.replay(run_id=run_id, scope=scope)

    async def delete(self, *, run_id: str, scope: RunScope) -> RunReplaySnapshot:
        return await self.durable_ledger.delete(run_id=run_id, scope=scope)


__all__ = ["DurableVerticalFamilyGrowthService"]
