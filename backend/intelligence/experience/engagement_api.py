"""HTTP boundary for evidence-bound Engagement Draft generation.

The route accepts only event identifiers and model context.  A runtime resolver
must supply the authenticated ``ExperienceScope``, actor, consent reference,
server-side event reader and Model Gateway.  Without that resolver the route is
visible but fail-closed with 503, preserving production/test contract parity.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Mapping
from typing import Any, Literal, Protocol

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.intelligence.experience.contracts import ExperienceScope
from backend.intelligence.experience.engagement import EngagementDraft
from backend.intelligence.experience.engagement_review import (
    EngagementDraftReviewError,
    EngagementDraftReviewNotFound,
    engagement_draft_id,
)
from backend.intelligence.human_gate.contracts import HumanTask
from backend.intelligence.human_gate.errors import HumanGateError
from backend.intelligence.model_gateway.errors import ModelGatewayError

_FORBIDDEN_CLIENT_KEYS = frozenset(
    {
        "tenant_id",
        "family_id",
        "subject_id",
        "subject_ids",
        "purpose",
        "consent",
        "consent_granted",
        "consent_version",
        "actor_id",
        "authorization_ref",
        "context_snapshot_ref",
        "environment",
        "provider",
        "provider_id",
        "api_key",
        "access_token",
        "secret",
    }
)


def _reject_forbidden_keys(value: object, *, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_CLIENT_KEYS:
                raise ValueError(f"{path}.{key} is controlled by the server")
            _reject_forbidden_keys(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_forbidden_keys(item, path=f"{path}[{index}]")


class EngagementDraftRuntime(Protocol):
    scope: ExperienceScope

    async def generate_draft(
        self,
        *,
        request_id: str,
        event_ids: tuple[str, ...],
        payload: Mapping[str, Any] | None = None,
    ) -> EngagementDraft: ...

    async def submit_achievement_candidate(
        self,
        *,
        draft_id: str,
        candidate_id: str,
        idempotency_key: str,
    ) -> HumanTask: ...

    async def decide_achievement_task(
        self,
        *,
        task_id: str,
        outcome: str,
        reason: str | None,
        idempotency_key: str,
    ) -> HumanTask: ...


class EngagementDraftRuntimeResolver(Protocol):
    def resolve(
        self, family_id: str
    ) -> EngagementDraftRuntime | Awaitable[EngagementDraftRuntime]: ...


class EngagementDraftRequest(BaseModel):
    """Client-controlled generation intent; scope and events stay server-owned."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    event_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_ids")
    @classmethod
    def validate_event_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not event_id.strip() for event_id in value):
            raise ValueError("event_ids must contain non-empty ids")
        if len(set(value)) != len(value):
            raise ValueError("event_ids must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_payload(self) -> EngagementDraftRequest:
        _reject_forbidden_keys(self.payload)
        return self


class EngagementCandidateSubmissionRequest(BaseModel):
    """The server owns every proposal field; the client submits an empty object."""

    model_config = ConfigDict(extra="forbid")


class EngagementHumanDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["ACCEPT", "REJECT", "ESCALATE"]
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_reason_for_non_acceptance(self) -> EngagementHumanDecisionRequest:
        if self.outcome != "ACCEPT" and not (self.reason and self.reason.strip()):
            raise ValueError("reason is required for rejection or escalation")
        return self


class EngagementScopeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    region_id: str
    family_id: str
    subject_ids: tuple[str, ...]
    purpose: str
    consent_version: str
    consent_granted: Literal[True]
    data_class: str
    locale: str


class EngagementProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    model: str
    model_version: str
    prompt_version: str
    schema_version: str
    context_snapshot_ref: str
    use_case: str
    latency_ms: int
    confidence: float | None = None


class EngagementDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    draft_id: str
    status: Literal["DRAFT"]
    evidence_event_ids: tuple[str, ...]
    output: dict[str, Any]
    requires_human_confirmation: Literal[True]
    scope: EngagementScopeResponse
    provenance: EngagementProvenanceResponse


class EngagementReviewTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: str
    draft_id: str
    candidate_id: str
    title: str
    message: str
    evidence_refs: tuple[str, ...]
    risk_level: str
    expires_at: str
    decision_outcome: str | None = None
    decided_at: str | None = None


router = APIRouter(prefix="/families", tags=["experience"])


async def get_engagement_draft_runtime_resolver() -> EngagementDraftRuntimeResolver:
    """Default dependency; the composition root must install a resolver."""

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="engagement_runtime_not_configured",
    )


async def _resolve_runtime(
    family_id: str,
    resolver: EngagementDraftRuntimeResolver,
) -> EngagementDraftRuntime:
    try:
        resolved = resolver.resolve(family_id)
        runtime = await resolved if inspect.isawaitable(resolved) else resolved
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="engagement_scope_denied",
        ) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="engagement_scope_invalid",
        ) from error
    if not hasattr(runtime, "scope") or not callable(getattr(runtime, "generate_draft", None)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engagement_runtime_invalid",
        )
    scope = runtime.scope
    if not isinstance(scope, ExperienceScope) or scope.family_id != family_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="engagement_scope_denied",
        )
    return runtime


def _to_response(draft: EngagementDraft) -> EngagementDraftResponse:
    provenance = draft.draft.provenance
    scope = draft.scope
    if scope is None:  # pragma: no cover - contract guard
        raise ValueError("engagement draft scope is required")
    return EngagementDraftResponse(
        request_id=draft.request_id,
        draft_id=draft.draft_id
        or engagement_draft_id(
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            request_id=draft.request_id,
        ),
        status=draft.draft.status,
        evidence_event_ids=draft.evidence_event_ids,
        output=dict(draft.output),
        requires_human_confirmation=True,
        scope=EngagementScopeResponse(
            tenant_id=scope.tenant_id,
            region_id=scope.region_id,
            family_id=scope.family_id,
            subject_ids=scope.subject_ids,
            purpose=scope.purpose,
            consent_version=scope.consent_version,
            consent_granted=True,
            data_class=str(scope.data_class),
            locale=scope.locale,
        ),
        provenance=EngagementProvenanceResponse(
            provider_id=provenance.provider_id,
            model=provenance.model,
            model_version=provenance.model_version,
            prompt_version=provenance.prompt_version,
            schema_version=provenance.schema_version,
            context_snapshot_ref=provenance.context_snapshot_ref,
            use_case=provenance.use_case,
            latency_ms=provenance.latency_ms,
            confidence=provenance.confidence,
        ),
    )


@router.post(
    "/{family_id}/experience/engagement/drafts",
    response_model=EngagementDraftResponse,
    status_code=status.HTTP_200_OK,
)
async def create_engagement_draft(
    family_id: str,
    body: EngagementDraftRequest,
    resolver: EngagementDraftRuntimeResolver = Depends(
        get_engagement_draft_runtime_resolver
    ),
) -> EngagementDraftResponse:
    runtime = await _resolve_runtime(family_id, resolver)
    try:
        draft = await runtime.generate_draft(
            request_id=body.request_id,
            event_ids=body.event_ids,
            payload=dict(body.payload),
        )
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="engagement_scope_denied",
        ) from error
    except ModelGatewayError as error:
        error_status = (
            status.HTTP_504_GATEWAY_TIMEOUT
            if error.kind == "TIMEOUT"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        raise HTTPException(status_code=error_status, detail=error.kind) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ENGAGEMENT_DRAFT_INVALID",
        ) from error
    try:
        return _to_response(draft)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ENGAGEMENT_DRAFT_RESPONSE_INVALID",
        ) from error


@router.post(
    "/{family_id}/experience/engagement/drafts/{draft_id}/achievement-candidates/"
    "{candidate_id}/human-task",
    response_model=EngagementReviewTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_engagement_achievement_candidate(
    family_id: str,
    draft_id: str,
    candidate_id: str,
    body: EngagementCandidateSubmissionRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    resolver: EngagementDraftRuntimeResolver = Depends(
        get_engagement_draft_runtime_resolver
    ),
) -> EngagementReviewTaskResponse:
    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="idempotency_key_required",
        )
    runtime = await _resolve_runtime(family_id, resolver)
    submit = getattr(runtime, "submit_achievement_candidate", None)
    if not callable(submit):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engagement_review_runtime_not_configured",
        )
    try:
        task = await submit(
            draft_id=draft_id,
            candidate_id=candidate_id,
            idempotency_key=idempotency_key,
        )
    except EngagementDraftReviewNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="engagement_draft_not_found",
        ) from error
    except EngagementDraftReviewError as error:
        error_status = (
            status.HTTP_409_CONFLICT
            if "EXPIRED" in str(error) or "REPLAY" in str(error) or "STALE" in str(error)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=error_status, detail=str(error)) from error
    except HumanGateError as error:
        error_status = (
            status.HTTP_409_CONFLICT
            if error.code in {"PROPOSAL_REPLAY_MISMATCH", "TASK_ID_COLLISION"}
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=error_status, detail=error.code) from error
    return _review_task_response(task)


@router.post(
    "/{family_id}/experience/engagement/human-tasks/{task_id}/decisions",
    response_model=EngagementReviewTaskResponse,
    status_code=status.HTTP_200_OK,
)
async def decide_engagement_achievement_task(
    family_id: str,
    task_id: str,
    body: EngagementHumanDecisionRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    resolver: EngagementDraftRuntimeResolver = Depends(
        get_engagement_draft_runtime_resolver
    ),
) -> EngagementReviewTaskResponse:
    if idempotency_key is None or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="idempotency_key_required",
        )
    runtime = await _resolve_runtime(family_id, resolver)
    decide = getattr(runtime, "decide_achievement_task", None)
    if not callable(decide):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engagement_reviewer_runtime_not_configured",
        )
    try:
        task = await decide(
            task_id=task_id,
            outcome=body.outcome,
            reason=body.reason,
            idempotency_key=idempotency_key,
        )
    except PermissionError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="engagement_reviewer_denied",
        ) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engagement_reviewer_runtime_not_configured",
        ) from error
    except HumanGateError as error:
        error_status = {
            "TASK_NOT_FOUND": status.HTTP_404_NOT_FOUND,
            "TASK_EXPIRED": status.HTTP_409_CONFLICT,
            "TASK_ALREADY_DECIDED": status.HTTP_409_CONFLICT,
            "REVIEWER_NOT_ALLOWED": status.HTTP_403_FORBIDDEN,
            "HUMAN_REVIEWER_REQUIRED": status.HTTP_403_FORBIDDEN,
        }.get(error.code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        raise HTTPException(status_code=error_status, detail=error.code) from error
    return _review_task_response(task)


def _review_task_response(task: HumanTask) -> EngagementReviewTaskResponse:
    arguments = task.proposal.action_arguments
    evidence_refs = arguments.get("evidence_refs")
    if not isinstance(evidence_refs, (list, tuple)):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="engagement_review_task_invalid",
        )
    return EngagementReviewTaskResponse(
        task_id=task.task_id,
        status=task.status.value,
        draft_id=task.proposal.draft_id,
        candidate_id=str(arguments.get("candidate_id", "")),
        title=str(arguments.get("title", "")),
        message=str(arguments.get("message", "")),
        evidence_refs=tuple(str(item) for item in evidence_refs),
        risk_level=task.proposal.risk_level,
        expires_at=task.proposal.expires_at.isoformat(),
        decision_outcome=(
            None if task.decision is None else task.decision.outcome.value
        ),
        decided_at=(
            None if task.decision is None else task.decision.decided_at.isoformat()
        ),
    )


__all__ = [
    "EngagementCandidateSubmissionRequest",
    "EngagementDraftRequest",
    "EngagementDraftResponse",
    "EngagementHumanDecisionRequest",
    "EngagementReviewTaskResponse",
    "EngagementDraftRuntime",
    "EngagementDraftRuntimeResolver",
    "get_engagement_draft_runtime_resolver",
    "decide_engagement_achievement_task",
    "router",
    "submit_engagement_achievement_candidate",
]
