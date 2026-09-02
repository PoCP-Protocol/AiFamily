"""HTTP facade for the adult-only live commerce contract sandbox."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from poc.standalone_live_commerce_sandbox.contract import (
    ActorRole,
    CommerceActor,
    CommerceConflict,
    CommerceRejected,
    InMemoryCanonicalCommerceFixture,
    LiveCommerceService,
    SupportIntent,
    SupportKind,
)
from poc.standalone_live_commerce_sandbox.ledger_sandbox import (
    LedgerActor,
    LedgerRejected,
    Purchase,
    ThreeLedgerSandbox,
    Track,
)
from poc.standalone_live_moderation_sandbox.question_api import (
    SyntheticActor,
    actor_headers,
    require_role,
)


class SupportRequest(BaseModel):
    intent_ref: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=120)
    kind: SupportKind
    amount: int = Field(gt=0, le=100_000)
    currency: str


class RefundRequest(BaseModel):
    refund_ref: str = Field(min_length=3, max_length=120)
    support_intent_ref: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=2, max_length=240)


class PurchaseRequest(BaseModel):
    purchase_ref: str = Field(min_length=3, max_length=120)
    track: Track
    subject_ref: str = Field(min_length=3, max_length=120)
    amount: int = Field(gt=0, le=10_000_000)
    currency: str = Field(min_length=3, max_length=20)
    idempotency_key: str = Field(min_length=3, max_length=120)


class ReversalRequest(BaseModel):
    reversal_ref: str = Field(min_length=3, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=120)
    reason: str = Field(min_length=2, max_length=240)


def create_app(database_path: Path | None = None) -> FastAPI:
    port = InMemoryCanonicalCommerceFixture()
    service = LiveCommerceService(port)
    if database_path is None:
        database_path = Path(tempfile.mkdtemp(prefix="xiaojudeng-commerce-")) / "ledger.sqlite3"
    ledger = ThreeLedgerSandbox(database_path)
    app = FastAPI(title="Xiao Ju Deng adult commerce sandbox")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://127\.0\.0\.1:\d+$",
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "source": "SANDBOX_SYNTHETIC", "fixture_only": True}

    @app.get("/sandbox/live-commerce/membership")
    def membership(
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"ADULT_VIEWER"})
        member = service.membership(actor=commerce_actor(actor))
        return {
            "membership": member,
            "source": "SANDBOX_SYNTHETIC",
            "fixture_only": True,
        }

    @app.post("/sandbox/live-commerce/sessions/{session_ref}/support")
    def support(
        session_ref: str,
        request: SupportRequest,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"ADULT_VIEWER"})
        try:
            receipt = service.support_expert(
                actor=commerce_actor(actor),
                intent=SupportIntent(
                    intent_ref=request.intent_ref,
                    session_ref=session_ref,
                    expert_ref="expert.synthetic.1",
                    tenant_id="tenant.synthetic.alpha",
                    family_id="family.synthetic.alpha",
                    kind=request.kind,
                    amount=request.amount,
                    currency=request.currency,
                    idempotency_key=request.idempotency_key,
                ),
            )
        except CommerceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CommerceRejected as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {
            "intent_ref": receipt.intent_ref,
            "status": receipt.status,
            "gross_amount": receipt.gross_amount,
            "allocations": [
                {"beneficiary_ref": item.beneficiary_ref, "amount": item.amount}
                for item in receipt.allocations
            ],
            "external_effect": False,
            "source": receipt.source,
            "fixture_only": receipt.fixture_only,
        }

    @app.post("/sandbox/live-commerce/refunds")
    def refund(
        request: RefundRequest,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"ADULT_VIEWER"})
        try:
            receipt = service.refund_support(
                actor=commerce_actor(actor),
                support_intent_ref=request.support_intent_ref,
                refund_ref=request.refund_ref,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
            )
        except CommerceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CommerceRejected as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return {
            "refund_ref": receipt.refund_ref,
            "support_intent_ref": receipt.support_intent_ref,
            "status": receipt.status,
            "reversed_allocations": [
                {"beneficiary_ref": item.beneficiary_ref, "amount": item.amount}
                for item in receipt.reversed_allocations
            ],
            "reason": receipt.reason,
            "external_effect": False,
            "source": receipt.source,
            "fixture_only": receipt.fixture_only,
        }

    @app.post("/sandbox/live-commerce/purchases")
    def purchase(
        request: PurchaseRequest,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"ADULT_VIEWER"})
        try:
            result = ledger.purchase(
                actor=ledger_actor(actor),
                command=Purchase(
                    purchase_ref=request.purchase_ref,
                    track=request.track,
                    subject_ref=request.subject_ref,
                    amount=request.amount,
                    currency=request.currency,
                    idempotency_key=request.idempotency_key,
                ),
            )
        except LedgerRejected as exc:
            status_code = 409 if "idempotency conflict" in str(exc) else 403
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return sandbox_result(result)

    @app.post("/sandbox/live-commerce/purchases/{purchase_ref}/reversals")
    def reverse_purchase(
        purchase_ref: str,
        request: ReversalRequest,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"ADULT_VIEWER"})
        try:
            result = ledger.reverse(
                actor=ledger_actor(actor),
                purchase_ref=purchase_ref,
                reversal_ref=request.reversal_ref,
                idempotency_key=request.idempotency_key,
                reason=request.reason,
            )
        except LedgerRejected as exc:
            status_code = 409 if "idempotency conflict" in str(exc) else 404
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return sandbox_result(result)

    @app.get("/sandbox/live-commerce/purchases/{purchase_ref}/balances")
    def balances(
        purchase_ref: str,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"ADULT_VIEWER"})
        try:
            result = ledger.balances(actor=ledger_actor(actor), purchase_ref=purchase_ref)
        except LedgerRejected as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return sandbox_result(result)

    @app.get("/sandbox/live-commerce/purchases/{purchase_ref}/settlements")
    def settlements(
        purchase_ref: str,
        actor: Annotated[SyntheticActor, Depends(actor_headers())],
    ) -> dict[str, object]:
        require_role(actor, {"ADULT_VIEWER"})
        try:
            result = ledger.settlements(actor=ledger_actor(actor), purchase_ref=purchase_ref)
        except LedgerRejected as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return sandbox_result(result)

    return app


def commerce_actor(actor: SyntheticActor) -> CommerceActor:
    return CommerceActor(
        tenant_id=actor.tenant_id,
        family_id=actor.family_id,
        actor_id=actor.actor_id,
        role=ActorRole.ADULT_GUARDIAN,
    )


def ledger_actor(actor: SyntheticActor) -> LedgerActor:
    return LedgerActor(
        tenant_id=actor.tenant_id,
        family_id=actor.family_id,
        actor_id=actor.actor_id,
    )


def sandbox_result(result: dict[str, object]) -> dict[str, object]:
    return {
        **result,
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    if not args.serve:
        raise SystemExit("use --serve")
    uvicorn.run(create_app(args.database), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
