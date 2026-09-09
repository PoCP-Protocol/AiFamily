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
    VerticalFamilyGrowthRuntime,
    VerticalRuntimeError,
)
from backend.intelligence.experience.run_http import (
    InteractionType,
    RunHttpError,
    RunReplaySnapshot,
    RunScope,
)
from backend.intelligence.experience.sql_run_ledger import AsyncExperienceRunLedger
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft


class DurableVerticalLedgerPort(Protocol):
    async def create_draft(self, **kwargs: Any) -> RunReplaySnapshot: ...

    async def append_interaction(self, **kwargs: Any) -> Any: ...

    async def replay(self, **kwargs: Any) -> RunReplaySnapshot: ...

    async def feedback_refs(self, **kwargs: Any) -> tuple[str, ...]: ...


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
            "guardian_calibration": entry.guardian_calibration,
            "capability_refs": entry.capability_refs,
            "knowledge_ref": entry.knowledge_ref,
            "knowledge_version": entry.knowledge_version,
            "lineage_ref": entry.lineage_ref,
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
        # Scope isolation alone is not enough: a caller may have a valid
        # family scope but accidentally attach a decision for another need or
        # path to this run.  Resolve the durable draft before writing so the
        # correlation is checked against the server-owned payload.  This is a
        # fail-closed guard at the persistence boundary, not just a runtime
        # convenience check.
        snapshot = await self.replay(run_id=decision.run_id, scope=scope)
        payload = snapshot.draft_payload or {}
        if (
            payload.get("family_need_id") != decision.family_need_id
            or payload.get("path_id") != decision.path_id
        ):
            raise ValueError("GUARDIAN_DECISION_CORRELATION_MISMATCH")
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

    async def feedback_refs(self, *, scope: RunScope, family_need_id: str) -> tuple[str, ...]:
        return tuple(
            await self._call(
                self._ledger.feedback_refs,
                scope=scope,
                family_need_id=family_need_id,
            )
        )

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


class DurableVerticalGrowthRuntime:
    """Production facade that makes durable replay the HTTP source of truth.

    The generation pipeline remains the existing runtime, while every created
    draft is immediately copied to the shared experience ledger.  Reads and
    deletes never consult that process-local pipeline ledger.
    """

    def __init__(
        self,
        runtime: VerticalFamilyGrowthRuntime,
        ledger: DurableVerticalLedgerAdapter,
        scope_factory: Any,
        context_snapshot_factory: Any | None = None,
    ):
        self._runtime = runtime
        self._ledger = ledger
        self._scope_factory = scope_factory
        self._context_snapshot_factory = context_snapshot_factory

    async def _scope(self, family_id: str) -> RunScope:
        scope = self._scope_factory(family_id)
        if inspect.isawaitable(scope):
            scope = await scope
        if not isinstance(scope, RunScope) or scope.family_id != family_id:
            raise ValueError("durable vertical scope mismatch")
        return scope

    async def run(self, **kwargs: Any) -> EvaluationLedgerEntry:
        family_id = kwargs["family_id"]
        run_id = kwargs["run_id"]
        decision = kwargs.get("guardian_decision")
        # Idempotent HTTP retries must replay the durable run before creating
        # another ContextSnapshot or invoking the model a second time.
        try:
            existing = await self.replay(run_id=run_id, family_id=family_id)
        except RunHttpError as error:
            if error.code != "RUN_NOT_FOUND":
                raise
            existing = None
        except VerticalRuntimeError as error:
            if str(error) != "EVALUATION_ENTRY_NOT_FOUND":
                raise
            existing = None
        if existing is not None:
            if decision is not None:
                return await self.decide(
                    run_id=run_id,
                    family_id=family_id,
                    decision=decision,
                )
            return existing
        # A production composition may create a fresh scoped ContextSnapshot
        # before invoking the generator. Preserve that server-owned reference
        # instead of deriving one from the client run id.
        if self._context_snapshot_factory is not None:
            snapshot_ref = self._context_snapshot_factory(
                family_id=kwargs["family_id"], run_id=kwargs["run_id"]
            )
            if inspect.isawaitable(snapshot_ref):
                snapshot_ref = await snapshot_ref
            if not isinstance(snapshot_ref, str) or not snapshot_ref.strip():
                raise VerticalRuntimeError("CONTEXT_SNAPSHOT_REF_INVALID")
            kwargs = {**kwargs, "context_snapshot_ref": snapshot_ref}
        entry = await self._runtime.run(**kwargs)
        scope = await self._scope(family_id)
        await self._ledger.save_entry(entry, scope=scope)
        if decision is not None:
            await self._ledger.record_guardian_decision(decision, scope=scope)
        # The durable ledger is the source of truth for production responses.
        # Reconstructing after the write proves that serialization, provenance,
        # and guardian calibration survive the persistence boundary instead of
        # returning the process-local generator object.
        return await self.replay(run_id=entry.run_id, family_id=family_id)

    async def replay(self, *, run_id: str, family_id: str) -> EvaluationLedgerEntry:
        snapshot = await self._ledger.replay(run_id=run_id, scope=await self._scope(family_id))
        payload = snapshot.draft_payload
        if not payload:
            raise VerticalRuntimeError("EVALUATION_ENTRY_NOT_FOUND")
        feedback_refs = list(payload.get("feedback_refs", ()))
        guardian_calibration = payload.get("guardian_calibration")
        for interaction in reversed(snapshot.interactions):
            if interaction.interaction_type is not InteractionType.DECISION:
                continue
            decision_payload = dict(interaction.payload)
            decision_ref = decision_payload.get("decision_ref")
            if isinstance(decision_ref, str) and decision_ref not in feedback_refs:
                feedback_refs.append(decision_ref)
            guardian_calibration = {
                "decision_ref": decision_ref,
                "state": decision_payload.get("state"),
                "edits": dict(decision_payload.get("edits", {})),
            }
            break
        provenance_payload = dict(payload["provenance"])
        provenance = AiProvenance(
            **{
                name: provenance_payload[name]
                for name, field in AiProvenance.__dataclass_fields__.items()
                if field.init and name in provenance_payload and name != "REQUIRED_IDENTITY_FIELDS"
            }
        )
        return EvaluationLedgerEntry(
            family_need_id=payload["family_need_id"],
            path_id=payload["path_id"],
            run_id=snapshot.run_id,
            context_snapshot_ref=payload["context_snapshot_ref"],
            draft=ModelDraft(output=dict(payload["output"]), provenance=provenance),
            feedback_refs=tuple(feedback_refs),
            guardian_calibration=guardian_calibration,
            capability_refs=tuple(payload.get("capability_refs", ())),
            knowledge_ref=payload.get("knowledge_ref", ""),
            knowledge_version=payload.get("knowledge_version", ""),
            lineage_ref=payload.get("lineage_ref", ""),
        )

    async def delete(self, *, run_id: str, family_id: str) -> RunReplaySnapshot:
        return await self._ledger.delete(run_id=run_id, scope=await self._scope(family_id))

    async def decide(
        self, *, run_id: str, family_id: str, decision: GuardianDecision
    ) -> EvaluationLedgerEntry:
        scope = await self._scope(family_id)
        snapshot = await self._ledger.replay(run_id=run_id, scope=scope)
        payload = snapshot.draft_payload or {}
        if (
            payload.get("family_need_id") != decision.family_need_id
            or payload.get("path_id") != decision.path_id
        ):
            raise VerticalRuntimeError("GUARDIAN_DECISION_CORRELATION_MISMATCH")
        await self._ledger.record_guardian_decision(decision, scope=scope)
        return await self.replay(run_id=run_id, family_id=family_id)


__all__ = ["DurableVerticalGrowthRuntime", "DurableVerticalLedgerAdapter", "DurableVerticalRun"]
