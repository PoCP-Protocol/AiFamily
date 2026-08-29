"""FastAPI routes for the local Assessment vertical slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from backend.domains.assessment.service import AssessmentService
from backend.platform.audit import AuditEvent


class AccountSessionRequest(BaseModel):
    external_ref: str


class AssessmentStartRequest(BaseModel):
    subject_person_id: str
    tool_ref: str | None = None


class AssessmentResponseRequest(BaseModel):
    item_ref: str
    response_type: str
    response_value: str | bool


class HypothesisDecisionRequest(BaseModel):
    assessment_session_id: str
    hypothesis_ref: str
    decision_type: str


@dataclass
class AssessmentApiState:
    service: AssessmentService = field(default_factory=AssessmentService)
    tokens: dict[str, dict[str, str]] = field(default_factory=dict)
    idempotent_receipts: dict[str, Any] = field(default_factory=dict)


def build_router(state: AssessmentApiState | None = None) -> APIRouter:
    state = state or AssessmentApiState()
    router = APIRouter()

    def mutation_key(key: str | None) -> str:
        if not key:
            raise HTTPException(status_code=400, detail="idempotency-key header is required")
        return key

    def actor(authorization: str | None, family_id: str | None = None) -> dict[str, str]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="authorization required")
        identity = state.tokens.get(authorization[7:])
        if not identity or (family_id and identity["family_id"] != family_id):
            raise HTTPException(status_code=403, detail="family access denied")
        return identity

    def replay_or(key: str, operation: Any) -> Any:
        if key in state.idempotent_receipts:
            return state.idempotent_receipts[key]
        receipt = operation()
        state.idempotent_receipts[key] = receipt
        return receipt

    @router.post("/auth/account-session")
    def account_session(
        body: AccountSessionRequest,
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, str]:
        key = mutation_key(idempotency_key)

        def create() -> dict[str, str]:
            # The dev external_ref convention is "<account>:<family>" — the same
            # shape the mobile client sends via EXPO_PUBLIC_FAMILY_DEV_EXTERNAL_REF.
            # The family is the segment *after* the colon; reading [0] instead
            # bound the session to the account segment, so every
            # /families/{family_id}/... request failed its family check with 403.
            # A ref with no colon is treated as both account and family.
            account_part, _, family_part = body.external_ref.partition(":")
            account_id = account_part or body.external_ref
            family_id = family_part or account_id
            token = str(uuid4())
            state.tokens[token] = {"account_id": account_id, "family_id": family_id}
            result = {
                "token": token,
                "expires_at": "2099-01-01T00:00:00+00:00",
                "account_id": account_id,
                "family_id": family_id,
            }
            state.service.audit.record(
                AuditEvent(
                    actor_id=account_id,
                    tenant_id=family_id,
                    action="auth.session_created",
                    resource_type="IdentitySession",
                    resource_id=token,
                    reason="dev account session",
                    correlation_id=str(uuid4()),
                    after={"account_id": account_id},
                )
            )
            return result

        return replay_or(f"auth:{key}", create)

    @router.get("/auth/me")
    def me(authorization: str | None = Header(default=None)) -> dict[str, str]:
        identity = actor(authorization)
        return {"account_id": identity["account_id"], "session_id": identity["account_id"]}

    @router.get("/auth/contexts")
    def contexts(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        identity = actor(authorization)
        return {
            "account_id": identity["account_id"],
            "contexts": [
                {
                    "type": "FAMILY",
                    "tenant_id": identity["family_id"],
                    "family_id": identity["family_id"],
                    "person_id": identity["account_id"],
                    "membership_id": "dev-membership",
                    "role": "GUARDIAN",
                }
            ],
        }

    @router.post("/auth/session/revoke")
    def revoke(
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> dict[str, bool]:
        identity = actor(authorization)
        key = mutation_key(idempotency_key)

        def revoke_once() -> dict[str, bool]:
            state.service.audit.record(
                AuditEvent(
                    actor_id=identity["account_id"],
                    tenant_id=identity["family_id"],
                    action="auth.session_revoked",
                    resource_type="IdentitySession",
                    resource_id=identity["account_id"],
                    reason="dev session revoke",
                    correlation_id=str(uuid4()),
                    after={"revoked": True},
                )
            )
            return {"revoked": True}

        return replay_or(f"revoke:{identity['account_id']}:{key}", revoke_once)

    @router.get("/families/{family_id}/ui/02/assessment")
    def assessment_projection(
        family_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        actor(authorization, family_id)
        return {"family_id": family_id, "ui_id": "UI-02", "status": "READY", "items": []}

    @router.post("/families/{family_id}/assessments/sessions")
    def start(
        family_id: str,
        body: AssessmentStartRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> Any:
        identity = actor(authorization, family_id)
        key = mutation_key(idempotency_key)
        return replay_or(
            f"start:{family_id}:{key}",
            lambda: state.service.start(
                identity["account_id"], family_id, body.subject_person_id, body.tool_ref
            ),
        )

    @router.post("/families/{family_id}/assessments/sessions/{session_id}/responses")
    def response(
        family_id: str,
        session_id: str,
        body: AssessmentResponseRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> Any:
        identity = actor(authorization, family_id)
        key = mutation_key(idempotency_key)
        try:
            return replay_or(
                f"response:{family_id}:{session_id}:{key}",
                lambda: state.service.response(
                    identity["account_id"],
                    family_id,
                    session_id,
                    body.item_ref,
                    body.response_type,
                    body.response_value,
                ),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/families/{family_id}/assessments/sessions/{session_id}/submit")
    def submit(
        family_id: str,
        session_id: str,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> Any:
        identity = actor(authorization, family_id)
        key = mutation_key(idempotency_key)
        try:
            return replay_or(
                f"submit:{family_id}:{session_id}:{key}",
                lambda: state.service.submit(identity["account_id"], family_id, session_id),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/families/{family_id}/ui/03/growth-hypothesis")
    def hypothesis_projection(
        family_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        actor(authorization, family_id)
        return {
            "family_id": family_id,
            "ui_id": "UI-03",
            "hypotheses": [
                h
                for h in state.service.repository.hypotheses.values()
                if h["family_id"] == family_id
            ],
        }

    @router.post("/families/{family_id}/assessments/{session_id}/growth-hypothesis")
    def generate(
        family_id: str,
        session_id: str,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> Any:
        identity = actor(authorization, family_id)
        key = mutation_key(idempotency_key)
        try:
            return replay_or(
                f"generate:{family_id}:{session_id}:{key}",
                lambda: state.service.generate_hypothesis(
                    identity["account_id"], family_id, session_id
                ),
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/families/{family_id}/growth-hypotheses/decisions")
    def decide(
        family_id: str,
        body: HypothesisDecisionRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None),
    ) -> Any:
        identity = actor(authorization, family_id)
        key = mutation_key(idempotency_key)
        if body.decision_type not in {"CONFIRM", "DISMISS"}:
            raise HTTPException(status_code=422, detail="unsupported decision_type")
        try:
            return replay_or(
                f"decide:{family_id}:{key}",
                lambda: state.service.decide(
                    identity["account_id"],
                    family_id,
                    body.assessment_session_id,
                    body.hypothesis_ref,
                    body.decision_type,
                ),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router


def install_state(app: Any) -> AssessmentApiState:
    state = AssessmentApiState()
    app.include_router(build_router(state))
    app.state.assessment = state
    return state