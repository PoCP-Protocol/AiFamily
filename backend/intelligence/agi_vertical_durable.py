"""Adapter from the vertical AGI prototype to the existing durable run ledger.

The adapter deliberately owns no SQL tables.  It maps experiment drafts and
Guardian decisions onto ``AsyncExperienceRunLedger`` so PostgreSQL/restart/
deletion semantics remain the platform's existing responsibility.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Protocol

from backend.intelligence.agi_growth_path_projection import (
    GrowthPathProjection,
    project_next_growth_path,
)
from backend.intelligence.agi_vertical_runtime import (
    EvaluationLedgerEntry,
    GuardianDecision,
)
from backend.intelligence.experience.run_http import InteractionType, RunReplaySnapshot, RunScope
from backend.intelligence.experience.sql_run_ledger import AsyncExperienceRunLedger


class DurableVerticalLedgerPort(Protocol):
    async def create_draft(self, **kwargs: Any) -> RunReplaySnapshot: ...

    async def append_interaction(self, **kwargs: Any) -> Any: ...

    async def replay(self, **kwargs: Any) -> RunReplaySnapshot: ...


@dataclass(frozen=True, slots=True)
class DurableVerticalRun:
    family_need_id: str
    path_id: str
    run_id: str
    scope: RunScope
    snapshot: RunReplaySnapshot


class DurableVerticalLedgerAdapter:
    """Persist vertical drafts through the existing experience ledger port."""

    def __init__(self, ledger: DurableVerticalLedgerPort | AsyncExperienceRunLedger):
        self._ledger = ledger

    async def _call(self, method: Any, **kwargs: Any) -> Any:
        result = method(**kwargs)
        return await result if inspect.isawaitable(result) else result

    async def save_entry(
        self, entry: EvaluationLedgerEntry, *, scope: RunScope
    ) -> DurableVerticalRun:
        payload = {
            "family_need_id": entry.family_need_id,
            "path_id": entry.path_id,
            "run_id": entry.run_id,
            "status": entry.draft.status,
            "output": entry.draft.output,
            "provenance": entry.draft.provenance.__dict__
            if hasattr(entry.draft.provenance, "__dict__")
            else {
                name: getattr(entry.draft.provenance, name)
                for name in entry.draft.provenance.__dataclass_fields__
            },
            "feedback_refs": entry.feedback_refs,
            "context_snapshot_ref": entry.context_snapshot_ref,
        }
        snapshot = await self._call(
            self._ledger.create_draft,
            scope=scope,
            run_id=entry.run_id,
            request_ref=f"agi:{entry.family_need_id}:{entry.path_id}",
            draft_payload=payload,
            idempotency_key=f"agi-create:{entry.run_id}",
        )
        return DurableVerticalRun(
            entry.family_need_id, entry.path_id, entry.run_id, scope, snapshot
        )

    async def record_guardian_decision(
        self, decision: GuardianDecision, *, scope: RunScope
    ) -> None:
        await self._call(
            self._ledger.append_interaction,
            scope=scope,
            run_id=decision.run_id,
            interaction_type=InteractionType.DECISION,
            payload={
                "decision": {
                    "ACCEPT": "accepted",
                    "EDIT": "rewrite",
                    "REJECT": "rejected",
                    "DEFER": "pending_human_confirmation",
                }[decision.state],
                "decision_ref": decision.decision_ref,
                "family_need_id": decision.family_need_id,
                "path_id": decision.path_id,
                "run_id": decision.run_id,
                "state": decision.state,
                "edits": decision.edits,
            },
            idempotency_key=f"agi-decision:{decision.decision_ref}",
        )

    async def replay(self, *, run_id: str, scope: RunScope) -> RunReplaySnapshot:
        return await self._call(self._ledger.replay, scope=scope, run_id=run_id)

    async def project_growth_path(self, *, run_id: str, scope: RunScope) -> GrowthPathProjection:
        """Read the durable run and project the next growth direction."""

        snapshot = await self.replay(run_id=run_id, scope=scope)
        return project_next_growth_path(snapshot)

    async def delete(self, *, run_id: str, scope: RunScope) -> RunReplaySnapshot:
        await self._call(
            self._ledger.append_interaction,
            scope=scope,
            run_id=run_id,
            interaction_type=InteractionType.DELETE,
            payload={"status": "deleted"},
            idempotency_key=f"agi-delete:{run_id}",
        )
        return await self.replay(run_id=run_id, scope=scope)


__all__ = ["DurableVerticalLedgerAdapter", "DurableVerticalRun"]
