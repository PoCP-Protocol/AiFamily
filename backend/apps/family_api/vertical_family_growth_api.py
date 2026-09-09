"""HTTP contract for the vertical family-growth AGI draft pipeline.

The endpoint exposes a *draft* generation only.  It deliberately does not
accept tenant or subject scope from the body: the composed runtime resolves
that context server-side and the model gateway is constrained to ``DRAFT``
outputs (R8/R9).  A missing runtime is a 503 rather than a synthetic fallback.
"""

from __future__ import annotations

import inspect
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field

from backend.intelligence.agi_vertical_runtime import (
    GuardianDecision,
    VerticalFamilyGrowthRuntime,
    VerticalRuntimeError,
)
from backend.intelligence.context_engine.contracts import ContextContractError
from backend.intelligence.experience.run_http import RunHttpError


class GuardianDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_ref: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    path_id: str = Field(min_length=1, max_length=200)
    state: str = Field(pattern="^(ACCEPT|REJECT|EDIT|DEFER)$")
    edits: dict[str, object] = Field(default_factory=dict)


class VerticalGrowthDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_need_id: str = Field(min_length=1, max_length=200)
    path_id: str = Field(min_length=1, max_length=200)
    run_id: str = Field(min_length=1, max_length=200)
    knowledge_ref: str = Field(min_length=1, max_length=300)
    provider_id: str | None = Field(default=None, min_length=1, max_length=100)
    guardian_decision: GuardianDecisionInput | None = None


class VerticalGrowthDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_need_id: str
    path_id: str
    run_id: str
    context_snapshot_ref: str
    status: str
    output: dict[str, object]
    feedback_refs: tuple[str, ...]
    capability_refs: tuple[str, ...]
    knowledge_ref: str
    knowledge_version: str
    lineage_ref: str
    provenance: dict[str, object]


class VerticalGrowthDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_ref: str = Field(min_length=1, max_length=200)
    family_need_id: str = Field(min_length=1, max_length=200)
    path_id: str = Field(min_length=1, max_length=200)
    state: str = Field(pattern="^(ACCEPT|REJECT|EDIT|DEFER)$")
    edits: dict[str, object] = Field(default_factory=dict)
    next_run_id: str | None = Field(default=None, min_length=1, max_length=200)


def get_vertical_family_growth_runtime(
    request: Request,
) -> VerticalFamilyGrowthRuntime:
    runtime = getattr(request.app.state, "vertical_family_growth_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="vertical_family_growth_runtime_not_configured",
        )
    return runtime


def _map_runtime_error(
    error: VerticalRuntimeError | RunHttpError | ContextContractError,
) -> HTTPException:
    """Translate both in-process and durable runtime errors to stable HTTP.

    The PostgreSQL-backed runtime delegates replay/delete to the shared
    experience ledger, whose provider-neutral contract raises ``RunHttpError``
    rather than ``VerticalRuntimeError``.  Keeping this mapping at the HTTP
    boundary prevents those expected isolation/idempotency failures from
    becoming unhandled 500 responses.
    """

    detail = getattr(error, "code", str(error))
    if detail in {
        "KNOWLEDGE_NOT_PUBLISHED",
        "CONTEXT_SCOPE_MISMATCH",
        "CROSS_TENANT_CONTEXT_SNAPSHOT",
        "CROSS_FAMILY_CONTEXT_SNAPSHOT",
        "CONTEXT_SNAPSHOT_NOT_FOUND",
        "CONTEXT_SNAPSHOT_EXPIRED",
        "CONTEXT_DELETION_IN_PROGRESS",
        "RUN_SCOPE_MISMATCH",
        "RUN_NOT_FOUND",
    }:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if detail in {
        "RUN_ID_REPLAY_COLLISION",
        "GUARDIAN_DECISION_SCOPE_MISMATCH",
        "RUN_ALREADY_EXISTS",
        "DRAFT_CREATE_IN_PROGRESS",
        "IDEMPOTENCY_REPLAY_MISMATCH",
        "RUN_CREATE_CONFLICT",
        "INTERACTION_APPEND_CONFLICT",
        "REVISION_RUN_ID_INVALID",
        "REVISION_NO_CHANGE",
    }:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if detail in {"CONSENT_NOT_ACTIVE", "CONSENT_REVOKED"}:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="vertical_family_growth_runtime_unavailable",
    )


def _entry_response(entry: object) -> VerticalGrowthDraftResponse:
    """Project a runtime entry without exposing mutable business state."""
    return VerticalGrowthDraftResponse(
        family_need_id=entry.family_need_id,
        path_id=entry.path_id,
        run_id=entry.run_id,
        context_snapshot_ref=entry.context_snapshot_ref,
        status=entry.draft.status,
        output=entry.draft.output,
        feedback_refs=entry.feedback_refs,
        capability_refs=entry.capability_refs,
        knowledge_ref=entry.knowledge_ref,
        knowledge_version=entry.knowledge_version,
        lineage_ref=entry.lineage_ref,
        provenance={
            name: getattr(entry.draft.provenance, name)
            for name in entry.draft.provenance.__dataclass_fields__
        },
    )


async def _await_if_needed(value: Any) -> Any:
    """Resolve both legacy in-process and async durable runtime methods.

    The development runtime is intentionally synchronous for replay/delete,
    while PostgreSQL-backed adapters expose awaitable methods.  Keeping this
    bridge at the HTTP boundary avoids forcing either implementation to mimic
    the other's execution model and prevents an accidental coroutine object
    from leaking into response serialization.
    """

    return await value if inspect.isawaitable(value) else value


router = APIRouter(prefix="/families/{family_id}/growth", tags=["family-growth-ai"])


@router.post("/ai-drafts", response_model=VerticalGrowthDraftResponse)
async def create_vertical_growth_draft(
    payload: VerticalGrowthDraftRequest,
    family_id: Annotated[str, Path(min_length=1, max_length=200)],
    runtime: VerticalFamilyGrowthRuntime = Depends(get_vertical_family_growth_runtime),
) -> VerticalGrowthDraftResponse:
    decision = None
    if payload.guardian_decision is not None:
        value = payload.guardian_decision
        decision = GuardianDecision(
            decision_ref=value.decision_ref,
            family_need_id=payload.family_need_id,
            run_id=value.run_id,
            path_id=value.path_id,
            state=value.state,
            edits=dict(value.edits),
        )
    try:
        entry = await runtime.run(
            family_need_id=payload.family_need_id,
            path_id=payload.path_id,
            run_id=payload.run_id,
            family_id=family_id,
            knowledge_ref=payload.knowledge_ref,
            provider_id=payload.provider_id,
            guardian_decision=decision,
        )
    except (VerticalRuntimeError, RunHttpError, ContextContractError) as error:
        raise _map_runtime_error(error) from error
    return _entry_response(entry)


@router.get("/ai-drafts/{run_id}", response_model=VerticalGrowthDraftResponse)
async def replay_vertical_growth_draft(
    run_id: Annotated[str, Path(min_length=1, max_length=200)],
    family_id: Annotated[str, Path(min_length=1, max_length=200)],
    runtime: VerticalFamilyGrowthRuntime = Depends(get_vertical_family_growth_runtime),
) -> VerticalGrowthDraftResponse:
    try:
        entry = await _await_if_needed(runtime.replay(run_id=run_id, family_id=family_id))
    except (VerticalRuntimeError, RunHttpError, ContextContractError) as error:
        raise _map_runtime_error(error) from error
    return _entry_response(entry)


@router.post("/ai-drafts/{run_id}/decisions", response_model=VerticalGrowthDraftResponse)
async def decide_vertical_growth_draft(
    payload: VerticalGrowthDecisionRequest,
    run_id: Annotated[str, Path(min_length=1, max_length=200)],
    family_id: Annotated[str, Path(min_length=1, max_length=200)],
    runtime: VerticalFamilyGrowthRuntime = Depends(get_vertical_family_growth_runtime),
) -> VerticalGrowthDraftResponse:
    decision = GuardianDecision(
        decision_ref=payload.decision_ref,
        family_need_id=payload.family_need_id,
        run_id=run_id,
        path_id=payload.path_id,
        state=payload.state,
        edits=dict(payload.edits),
    )
    try:
        if payload.next_run_id is not None:
            revise = getattr(runtime, "revise", None)
            if not callable(revise):
                raise VerticalRuntimeError("vertical_family_growth_revision_unavailable")
            entry = await _await_if_needed(
                revise(
                    run_id=run_id,
                    next_run_id=payload.next_run_id,
                    family_id=family_id,
                    decision=decision,
                )
            )
        else:
            decide = getattr(runtime, "decide", None)
            if not callable(decide):
                raise VerticalRuntimeError("vertical_family_growth_decision_unavailable")
            entry = await _await_if_needed(
                decide(run_id=run_id, family_id=family_id, decision=decision)
            )
    except (VerticalRuntimeError, RunHttpError, ContextContractError, ValueError) as error:
        raise _map_runtime_error(error) from error
    return _entry_response(entry)


@router.delete("/ai-drafts/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vertical_growth_draft(
    run_id: Annotated[str, Path(min_length=1, max_length=200)],
    family_id: Annotated[str, Path(min_length=1, max_length=200)],
    runtime: VerticalFamilyGrowthRuntime = Depends(get_vertical_family_growth_runtime),
) -> None:
    try:
        await _await_if_needed(runtime.delete(run_id=run_id, family_id=family_id))
    except (VerticalRuntimeError, RunHttpError, ContextContractError) as error:
        raise _map_runtime_error(error) from error


__all__ = [
    "GuardianDecisionInput",
    "VerticalGrowthDraftRequest",
    "VerticalGrowthDraftResponse",
    "VerticalGrowthDecisionRequest",
    "get_vertical_family_growth_runtime",
    "router",
]
