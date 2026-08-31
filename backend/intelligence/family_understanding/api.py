"""Unmounted FastAPI router contract for generative family understanding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from backend.intelligence.family_understanding.application import (
    FamilyUnderstandingApplication,
    GenerateUnderstandingCommand,
    UnderstandingDraftView,
)
from backend.intelligence.family_understanding.contracts import KnowledgeRef
from backend.intelligence.family_understanding.eval import FamilyUnderstandingRejected
from backend.intelligence.model_gateway.errors import ModelGatewayError


class KnowledgeRefBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1)
    source: str = Field(min_length=1)
    version: str = Field(min_length=1)
    chunk_ref: str = Field(min_length=1)
    content_digest: str = Field(min_length=1)
    applicability: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)


class GenerateUnderstandingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    guardian_input_ref: str = Field(min_length=1)
    guardian_text: str = Field(min_length=1)
    revision: int = Field(ge=1)
    prior_draft_artifact_hash: str | None = None
    reviewed_knowledge_refs: list[KnowledgeRefBody] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class AuthorizedFamilyContext:
    tenant_id: str
    family_id: str
    subject_ref: str
    consent_ref: str
    context_snapshot_ref: str
    context_expires_at: datetime


class AuthorizedContextResolver(Protocol):
    async def resolve(
        self, *, tenant_id: str, family_id: str
    ) -> AuthorizedFamilyContext | None: ...


class UnderstandingDraftResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    artifact_hash: str
    request_hash: str
    version: int
    prior_draft_artifact_hash: str | None
    status: str
    summary: str
    hypotheses: list[dict[str, object]]
    unknowns: list[dict[str, str]]
    follow_up_questions: list[str]
    strengths: list[dict[str, object]]
    desired_change: dict[str, object]
    source_refs: list[str]
    knowledge_references: list[str]
    provider_id: str
    model: str
    model_version: str
    prompt_version: str
    schema_version: str
    context_snapshot_ref: str
    provenance: dict[str, object]
    requires_guardian_confirmation: bool
    may_mutate_business_state: bool


def create_family_understanding_router(
    application: FamilyUnderstandingApplication,
    authorized_contexts: AuthorizedContextResolver,
) -> APIRouter:
    router = APIRouter(tags=["family-understanding"])

    @router.post(
        "/v1/families/{family_id}/understanding-drafts",
        response_model=UnderstandingDraftResponse,
        status_code=status.HTTP_200_OK,
    )
    async def generate_understanding(
        family_id: str,
        body: GenerateUnderstandingBody,
    ) -> UnderstandingDraftResponse:
        authorized = await authorized_contexts.resolve(
            tenant_id=body.tenant_id,
            family_id=family_id,
        )
        if (
            authorized is None
            or authorized.tenant_id != body.tenant_id
            or authorized.family_id != family_id
        ):
            raise _http_error(status.HTTP_403_FORBIDDEN, "FAMILY_SCOPE_MISMATCH")
        try:
            view = await application.generate(
                GenerateUnderstandingCommand(
                    run_id=body.run_id,
                    tenant_id=body.tenant_id,
                    family_id=family_id,
                    subject_ref=authorized.subject_ref,
                    consent_ref=authorized.consent_ref,
                    context_snapshot_ref=authorized.context_snapshot_ref,
                    context_expires_at=authorized.context_expires_at,
                    guardian_input_ref=body.guardian_input_ref,
                    guardian_text=body.guardian_text,
                    revision=body.revision,
                    prior_draft_artifact_hash=body.prior_draft_artifact_hash,
                    reviewed_knowledge_refs=tuple(
                        KnowledgeRef(
                            ref=item.ref,
                            source=item.source,
                            version=item.version,
                            chunk_ref=item.chunk_ref,
                            content_digest=item.content_digest,
                            applicability=item.applicability,
                            limitations=tuple(item.limitations),
                        )
                        for item in body.reviewed_knowledge_refs
                    ),
                )
            )
        except FamilyUnderstandingRejected as exc:
            if exc.reason == "SCOPE_MISMATCH":
                raise _http_error(status.HTTP_403_FORBIDDEN, "FAMILY_SCOPE_MISMATCH") from exc
            if exc.reason in {"PROMPT_INJECTION_DETECTED", "DIRECT_IDENTIFIER_DETECTED"}:
                raise _http_error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.reason) from exc
            if exc.reason == "REPLAY_INPUT_MISMATCH":
                raise _http_error(status.HTTP_409_CONFLICT, exc.reason) from exc
            raise _unavailable() from exc
        except ModelGatewayError as exc:
            raise _unavailable() from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise _http_error(status.HTTP_422_UNPROCESSABLE_ENTITY, "REQUEST_INVALID") from exc
        return _response(view)

    return router


def _response(view: UnderstandingDraftView) -> UnderstandingDraftResponse:
    return UnderstandingDraftResponse(
        run_id=view.run_id,
        artifact_hash=view.artifact_hash,
        request_hash=view.request_hash,
        version=view.version,
        prior_draft_artifact_hash=view.prior_draft_artifact_hash,
        status=view.status,
        summary=view.summary,
        hypotheses=list(view.hypotheses),
        unknowns=list(view.unknowns),
        follow_up_questions=list(view.follow_up_questions),
        strengths=list(view.strengths),
        desired_change=view.desired_change,
        source_refs=list(view.source_refs),
        knowledge_references=list(view.knowledge_references),
        provider_id=view.provider_id,
        model=view.model,
        model_version=view.model_version,
        prompt_version=view.prompt_version,
        schema_version=view.schema_version,
        context_snapshot_ref=view.context_snapshot_ref,
        provenance=view.provenance,
        requires_guardian_confirmation=view.requires_guardian_confirmation,
        may_mutate_business_state=view.may_mutate_business_state,
    )


def _http_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code})


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "UNDERSTANDING_TEMPORARILY_UNAVAILABLE",
            "message": "这次理解暂时没有完成，请保留输入后重试。",
        },
    )
