"""HTTP control plane for the FGCN Human Gate -> Named Action bridge.

This router exposes the smallest deployable platform seam for the reference
FGCN chain:

* an authenticated AI actor submits an assignment *proposal*;
* a trusted human reviewer decides it;
* an authenticated internal workflow worker consumes only an accepted request.

The first two operations persist only AI review state.  The third delegates to
``consume_accepted_human_task``; it never writes ``TaskAssignment`` directly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from backend.domains.service.domain.errors import ServiceDomainError
from backend.intelligence.human_gate import (
    ActionProposal,
    GateScope,
    HumanTask,
    SqlAlchemyHumanGate,
)
from backend.intelligence.human_gate import ActorType as GateActorType
from backend.intelligence.model_gateway.contracts import ModelDraft
from backend.intelligence.model_gateway.provenance import StoredModelDraft
from backend.platform.audit import AuditRecorder
from backend.platform.identity.context import ActorContext, ActorType

from ..admission import AsyncProviderAdmissionQuery
from ..application import FGCNAssignmentRepository
from ..workflow_worker import consume_accepted_human_task
from . import dependencies as deps
from .requests import AssignmentProposalRequest, HumanDecisionRequest

router = APIRouter(prefix="/families/{family_id}/fgcn", tags=["fgcn"])

_HUMAN_GATE_ERROR_STATUS = {
    "TASK_NOT_FOUND": 404,
    "TASK_EXPIRED": 409,
    "TASK_ALREADY_DECIDED": 409,
    "PROPOSAL_REPLAY_MISMATCH": 409,
    "TASK_ID_COLLISION": 409,
    "PERSISTED_SHAPE_INVALID": 409,
    "INVALID_CONTRACT": 400,
    "INVALID_NAMED_ACTION": 400,
    "INVALID_DECISION": 400,
    "DECISION_REASON_REQUIRED": 400,
    "REVIEWER_NOT_ALLOWED": 403,
    "HUMAN_REVIEWER_REQUIRED": 403,
}

_SERVICE_ERROR_STATUS = {
    "ServiceValidationError": 400,
    "ServiceForbiddenError": 403,
    "ServiceNotFoundError": 404,
    "ServiceConflictError": 409,
}


def register_exception_handlers(app: FastAPI) -> None:
    """Install stable HTTP mappings for gate and FGCN domain errors."""

    from backend.intelligence.human_gate.errors import HumanGateError

    @app.exception_handler(HumanGateError)
    async def _handle_human_gate_error(request, error: HumanGateError) -> JSONResponse:
        return JSONResponse(
            status_code=_HUMAN_GATE_ERROR_STATUS.get(error.code, 400),
            content={"detail": error.code},
        )

    @app.exception_handler(ServiceDomainError)
    async def _handle_service_error(request, error: ServiceDomainError) -> JSONResponse:
        return JSONResponse(
            status_code=_SERVICE_ERROR_STATUS.get(type(error).__name__, 400),
            content={"detail": error.code},
        )


def _assert_family_path(family_id: str, context: deps.ActionContext) -> None:
    if family_id != context.family_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")


def _require_idempotency_key(context: deps.ActionContext) -> None:
    if not context.idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency-key header is required")


def _require_ai_actor(actor: ActorContext, context: deps.ActionContext) -> None:
    if not actor.is_ai or actor.tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail="fgcn_draft_requires_scoped_ai_actor")


def _require_worker_actor(actor: ActorContext, context: deps.ActionContext) -> None:
    if actor.actor_type is not ActorType.SYSTEM or actor.tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail="fgcn_consume_requires_scoped_worker")


async def _load_scoped_task(
    service_task_id: str,
    context: deps.ActionContext,
    repository: FGCNAssignmentRepository,
):
    task = await repository.load_task(service_task_id)
    case = await repository.load_case(task.case_id)
    if case.scope.tenant_id != context.tenant_id or case.scope.family_id != context.family_id:
        raise HTTPException(status_code=403, detail="fgcn_case_scope_violation")
    return task, case


def _gate_scope(case) -> GateScope:
    return GateScope(
        tenant_id=case.scope.tenant_id,
        family_id=case.scope.family_id,
        subject_ids=(case.scope.subject_person_id,),
        purpose=case.scope.purpose,
        consent_version=case.scope.consent_version,
        correlation_id=case.scope.correlation_id,
    )


def _serialize_gate_scope(scope: GateScope) -> dict[str, Any]:
    return {
        "tenant_id": scope.tenant_id,
        "family_id": scope.family_id,
        "subject_ids": list(scope.subject_ids),
        "purpose": scope.purpose,
        "consent_version": scope.consent_version,
        "correlation_id": scope.correlation_id,
    }


def _serialize_task(task: HumanTask) -> dict[str, Any]:
    proposal = task.proposal
    decision = task.decision
    request = task.action_request
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "created_at": task.created_at.isoformat(),
        "proposal": {
            "proposal_id": proposal.proposal_id,
            "draft_id": proposal.draft_id,
            "draft_status": proposal.draft_status,
            "action_name": proposal.action_name,
            "action_arguments": dict(proposal.action_arguments),
            "scope": _serialize_gate_scope(proposal.scope),
            "allowed_actor_types": [item.value for item in proposal.allowed_actor_types],
            "risk_level": proposal.risk_level,
            "provenance_ref": proposal.provenance_ref,
            "created_at": proposal.created_at.isoformat(),
            "expires_at": proposal.expires_at.isoformat(),
        },
        "decision": None
        if decision is None
        else {
            "decision_id": decision.decision_id,
            "task_id": decision.task_id,
            "actor_id": decision.actor_id,
            "actor_type": decision.actor_type.value,
            "outcome": decision.outcome.value,
            "reason": decision.reason,
            "decided_at": decision.decided_at.isoformat(),
        },
        "action_request": None
        if request is None
        else {
            "request_id": request.request_id,
            "action_name": request.action_name,
            "action_arguments": dict(request.action_arguments),
            "task_id": request.task_id,
            "proposal_id": request.proposal_id,
            "decision_id": request.decision_id,
            "actor_id": request.actor_id,
            "actor_type": request.actor_type.value,
            "scope": _serialize_gate_scope(request.scope),
            "provenance_ref": request.provenance_ref,
            "idempotency_key": request.idempotency_key,
        },
    }


async def _resolve_provenance_draft(
    resolver: deps.DraftProvenanceResolver,
    body: AssignmentProposalRequest,
    case,
) -> ModelDraft:
    """Resolve the draft and, when available, verify its server-owned id."""

    resolve_stored = getattr(resolver, "resolve_stored", None)
    if callable(resolve_stored):
        stored = await resolve_stored(
            body.provenance_ref,
            tenant_id=case.scope.tenant_id,
            family_id=case.scope.family_id,
            subject_person_id=case.scope.subject_person_id,
            purpose=case.scope.purpose,
            correlation_id=case.scope.correlation_id,
        )
        if not isinstance(stored, StoredModelDraft):
            raise HTTPException(status_code=422, detail="fgcn_provenance_record_invalid")
        if stored.draft_id != body.draft_id:
            raise HTTPException(status_code=422, detail="fgcn_draft_identity_mismatch")
        return stored.draft
    return await resolver.resolve(
        body.provenance_ref,
        tenant_id=case.scope.tenant_id,
        family_id=case.scope.family_id,
        subject_person_id=case.scope.subject_person_id,
        purpose=case.scope.purpose,
        correlation_id=case.scope.correlation_id,
    )


@router.post("/tasks/{service_task_id}/assignment-proposals", status_code=201)
async def submit_assignment_proposal(
    family_id: str,
    service_task_id: str,
    body: AssignmentProposalRequest,
    context: deps.ActionContext = Depends(deps.get_action_context),
    actor: ActorContext = Depends(deps.get_actor_context),
    repository: FGCNAssignmentRepository = Depends(deps.get_fgcn_repository),
    provenance_resolver: deps.DraftProvenanceResolver = Depends(deps.get_draft_provenance_resolver),
    gate: SqlAlchemyHumanGate = Depends(deps.get_human_gate),
    recorder: AuditRecorder = Depends(deps.get_audit_recorder),
) -> dict[str, Any]:
    """Persist a DRAFT proposal after deriving scope from the FGCN case."""

    _assert_family_path(family_id, context)
    _require_idempotency_key(context)
    _require_ai_actor(actor, context)
    task, case = await _load_scoped_task(service_task_id, context, repository)
    try:
        draft = await _resolve_provenance_draft(provenance_resolver, body, case)
    except deps.DraftProvenanceNotFound as exc:
        raise HTTPException(status_code=422, detail="fgcn_provenance_not_found") from exc
    if not isinstance(draft, ModelDraft):
        raise HTTPException(status_code=422, detail="fgcn_provenance_not_a_model_draft")
    if draft.status != "DRAFT" or draft.may_mutate_business_state is not False:
        raise HTTPException(status_code=422, detail="fgcn_model_draft_not_reviewable")
    proposal = ActionProposal(
        proposal_id=body.proposal_id,
        draft_id=body.draft_id,
        draft_status="DRAFT",
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments={
            "service_task_id": task.task_id,
            "provider_id": body.provider_id,
            "assignee_kind": body.assignee_kind,
            "assignment_id": str(body.assignment_id or uuid4()),
        },
        scope=_gate_scope(case),
        allowed_actor_types=(GateActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref=body.provenance_ref,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(seconds=body.expires_in_seconds),
    )
    task_state = await gate.submit(proposal, recorder=recorder)
    await gate.flush_audit(recorder)
    await gate.commit()
    return _serialize_task(task_state)


@router.get("/human-tasks/{task_id}")
async def get_human_task(
    family_id: str,
    task_id: str,
    context: deps.ActionContext = Depends(deps.get_action_context),
    reviewer: deps.HumanReviewerContext = Depends(deps.get_human_reviewer_context),
    gate: SqlAlchemyHumanGate = Depends(deps.get_human_gate),
) -> dict[str, Any]:
    """Return a review task only to a trusted reviewer in the same tenant."""

    _assert_family_path(family_id, context)
    if reviewer.tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail="reviewer_tenant_scope_violation")
    task = await gate.get(task_id)
    if (
        task.proposal.scope.tenant_id != context.tenant_id
        or task.proposal.scope.family_id != family_id
    ):
        raise HTTPException(status_code=403, detail="human_task_scope_violation")
    if reviewer.actor_type not in task.proposal.allowed_actor_types:
        raise HTTPException(status_code=403, detail="reviewer_not_allowed_for_task")
    return _serialize_task(task)


@router.post("/human-tasks/{task_id}/decisions")
async def decide_human_task(
    family_id: str,
    task_id: str,
    body: HumanDecisionRequest,
    context: deps.ActionContext = Depends(deps.get_action_context),
    reviewer: deps.HumanReviewerContext = Depends(deps.get_human_reviewer_context),
    gate: SqlAlchemyHumanGate = Depends(deps.get_human_gate),
    recorder: AuditRecorder = Depends(deps.get_audit_recorder),
) -> dict[str, Any]:
    """Record a trusted human decision; ACCEPT returns only a Named Action."""

    _assert_family_path(family_id, context)
    _require_idempotency_key(context)
    if reviewer.tenant_id != context.tenant_id:
        raise HTTPException(status_code=403, detail="reviewer_tenant_scope_violation")
    task = await gate.get(task_id)
    if (
        task.proposal.scope.tenant_id != context.tenant_id
        or task.proposal.scope.family_id != family_id
    ):
        raise HTTPException(status_code=403, detail="human_task_scope_violation")
    decided, _ = await gate.decide(
        task_id,
        actor_id=reviewer.actor_id,
        actor_type=reviewer.actor_type,
        outcome=body.outcome,
        reason=body.reason,
        recorder=recorder,
    )
    await gate.flush_audit(recorder)
    await gate.commit()
    return _serialize_task(decided)


@router.post("/human-tasks/{task_id}/consume")
async def consume_human_task(
    family_id: str,
    task_id: str,
    context: deps.ActionContext = Depends(deps.get_action_context),
    worker: ActorContext = Depends(deps.get_workflow_worker_context),
    repository: FGCNAssignmentRepository = Depends(deps.get_fgcn_repository),
    provider_admission: AsyncProviderAdmissionQuery = Depends(deps.get_provider_admission),
    gate: SqlAlchemyHumanGate = Depends(deps.get_human_gate),
    recorder: AuditRecorder = Depends(deps.get_audit_recorder),
) -> dict[str, Any]:
    """Invoke the one-shot worker handler using only a system worker identity."""

    _assert_family_path(family_id, context)
    _require_idempotency_key(context)
    _require_worker_actor(worker, context)
    task = await gate.get(task_id)
    if (
        task.proposal.scope.tenant_id != context.tenant_id
        or task.proposal.scope.family_id != family_id
    ):
        raise HTTPException(status_code=403, detail="human_task_scope_violation")
    assignment = await consume_accepted_human_task(
        gate,
        repository,
        task_id,
        recorder=recorder,
        claim_owner=worker.actor_id,
        provider_admission=provider_admission,
    )
    return {
        "assignment_id": assignment.assignment_id,
        "case_id": assignment.case_id,
        "task_id": assignment.task_id,
        "assignee_ref": assignment.assignee_ref,
        "assignee_kind": assignment.assignee_kind,
        "status": assignment.status.value,
        "accepted_by_actor_id": assignment.accepted_by_actor_id,
        "source_request_id": assignment.source_request_id,
        "accepted_at": assignment.accepted_at.isoformat(),
    }


__all__ = ["register_exception_handlers", "router"]
