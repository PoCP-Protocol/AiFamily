"""Read-only DEV/TEST product catalogue route for UI-13/UI-14."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.domains.service.api.dependencies import get_action_context
from backend.domains.service.application.context import ActionContext

from ..application import commands, queries
from ..application.ports import CommerceRepositoryPort
from ..domain.errors import CommerceDomainError
from .dependencies import get_repository

router = APIRouter(
    prefix="/families/{family_id}/orchestration/test-loop/commerce", tags=["commerce"]
)


class SubmitCommerceIntentRequest(BaseModel):
    page_id: str = "UI-14"
    product_ref: str
    product_version: int = Field(gt=0)
    attributes: dict[str, object] = Field(default_factory=dict)


def _raise_http(exc: CommerceDomainError) -> None:
    status_by_type = {
        "CommerceNotFoundError": 404,
        "CommerceConflictError": 409,
    }
    status = status_by_type.get(type(exc).__name__, 400)
    raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/products")
async def get_product_catalogue(
    family_id: str,
    repo: CommerceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
) -> Any:
    if family_id != ctx.family_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")
    if ctx.environment not in {"DEV", "TEST"}:
        raise HTTPException(status_code=403, detail="commerce_fixture_boundary")
    return await queries.list_product_catalogue(repo, tenant_id=ctx.tenant_id)


@router.post("/order-intents")
async def submit_commerce_intent(
    family_id: str,
    body: SubmitCommerceIntentRequest,
    repo: CommerceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
) -> Any:
    if family_id != ctx.family_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")
    if ctx.environment not in {"DEV", "TEST"}:
        raise HTTPException(status_code=403, detail="commerce_fixture_boundary")
    try:
        intent, entitlement = await commands.submit_order_intent(
            repo,
            tenant_id=ctx.tenant_id,
            family_id=ctx.family_id,
            actor_person_id=ctx.actor_person_id,
            product_ref=body.product_ref,
            product_version=body.product_version,
            page_id=body.page_id,
            idempotency_key=ctx.idempotency_key,
            correlation_id=ctx.correlation_id,
            attributes=body.attributes,
        )
    except CommerceDomainError as exc:
        _raise_http(exc)
    return {
        "intent": {
            "order_intent_id": intent.order_intent_id,
            "intent_ref": intent.intent_ref,
            "status": intent.status,
            "product_ref": intent.product_ref,
            "product_version": intent.product_version,
            "row_version": 1,
            "external_effect": False,
            "environment": intent.environment,
            "text_equivalent": "购买意向已保存，不会扣款或自动开通权益。",
        },
        "entitlement": {
            "entitlement_id": entitlement.entitlement_id,
            "entitlement_ref": entitlement.entitlement_ref,
            "status": entitlement.status,
            "source_order_intent_id": entitlement.source_order_intent_id,
            "external_effect": False,
            "text_equivalent": "当前为待处理意向，不代表已购买或已开通权益。",
        },
    }


@router.get("/customer-projection")
async def get_commerce_customer_projection(
    family_id: str,
    repo: CommerceRepositoryPort = Depends(get_repository),
    ctx: ActionContext = Depends(get_action_context),
) -> Any:
    if family_id != ctx.family_id:
        raise HTTPException(status_code=403, detail="family_scope_violation")
    if ctx.environment not in {"DEV", "TEST"}:
        raise HTTPException(status_code=403, detail="commerce_fixture_boundary")
    return await queries.get_customer_projection(
        repo, tenant_id=ctx.tenant_id, family_id=ctx.family_id
    )
