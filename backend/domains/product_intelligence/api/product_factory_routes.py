"""Draft-only HTTP surface for the Product Factory.

This router is intentionally separate from the legacy acceptance-chain router
until the owning app explicitly mounts it.  It reuses existing commands where
their aggregate exists and returns a clear ``501`` for competitor evidence
until a repository port can persist the richer evidence-card shape.
"""

from __future__ import annotations

from typing import NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from backend.intelligence.product_management.product_factory_inputs import (
    CompetitorEvidenceCard,
    DemandFrame,
    MarketInsightDraft,
    ProductFactoryInputError,
)

from ..application import commands
from ..application.context import ActorContext
from ..application.ports import ProductIntelligenceRepositoryPort
from ..domain.errors import ProductIntelligenceDomainError
from .dependencies import get_actor_context, get_repository
from .product_factory_requests import (
    CreateCompetitorEvidenceCardRequest,
    CreateDemandFrameRequest,
    CreateMarketInsightDraftRequest,
    CreateProductPackageDraftRequest,
)
from .product_factory_responses import (
    CompetitorEvidenceCardResponse,
    DemandFrameDraftResponse,
    MarketInsightDraftResponse,
    ProductPackageDraftResponse,
)

router = APIRouter(prefix="/product-intelligence/product-factory", tags=["product-factory"])


def _raise_domain_http(exc: ProductIntelligenceDomainError) -> NoReturn:
    status = {
        "ProductIntelligenceForbiddenError": 403,
        "ProductIntelligenceNotFoundError": 404,
        "ProductIntelligenceValidationError": 422,
    }.get(type(exc).__name__, 400)
    raise HTTPException(status_code=status, detail=exc.code) from exc


def _raise_contract_http(exc: ProductFactoryInputError) -> NoReturn:
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _require_ai_provenance(context: ActorContext, body: object) -> None:
    """AI-authored drafts need complete provenance before any command runs."""

    if context.actor_type != "AI":
        return
    missing = [
        field
        for field in ("model_ref", "prompt_use_case_version", "confidence", "provenance_ref")
        if getattr(body, field, None) is None
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail="ai_actor_requires_full_provenance:" + ",".join(missing),
        )


def _demand_response(frame: DemandFrame) -> DemandFrameDraftResponse:
    return DemandFrameDraftResponse(
        demand_id=frame.demand_id,
        statement=frame.statement,
        scenario=frame.scenario,
        source_refs=frame.source_refs,
        target_segment=frame.target_segment,
        locale=frame.locale,
        purpose=frame.purpose,
        version=frame.version,
        status="DRAFT",
        evidence_refs=frame.evidence_refs,
        assumptions=frame.assumptions,
        unknowns=frame.unknowns,
        next_validation=frame.next_validation,
        expires_at=frame.expires_at,
        provenance_ref=frame.provenance_ref,
    )


def _insight_response(insight: MarketInsightDraft) -> MarketInsightDraftResponse:
    return MarketInsightDraftResponse(
        insight_id=insight.insight_id,
        demand_ref=insight.demand_ref,
        statement=insight.statement,
        source_refs=insight.source_refs,
        competitor_evidence_refs=insight.competitor_evidence_refs,
        segment_ref=insight.segment_ref,
        version=insight.version,
        status="DRAFT",
        evidence_refs=insight.evidence_refs,
        assumptions=insight.assumptions,
        unknowns=insight.unknowns,
        next_validation=insight.next_validation,
        expires_at=insight.expires_at,
        provenance_ref=insight.provenance_ref,
    )


def _competitor_response(card: CompetitorEvidenceCard) -> CompetitorEvidenceCardResponse:
    return CompetitorEvidenceCardResponse(
        evidence_id=card.evidence_id,
        competitor_ref=card.competitor_ref,
        claim=card.claim,
        source_refs=card.source_refs,
        evidence_status=card.evidence_status,
        demand_ref=card.demand_ref,
        market_insight_ref=card.market_insight_ref,
        source_type=card.source_type,
        version=card.version,
        status="DRAFT",
        evidence_refs=card.evidence_refs,
        assumptions=card.assumptions,
        unknowns=card.unknowns,
        next_validation=card.next_validation,
        expires_at=card.expires_at,
        provenance_ref=card.provenance_ref,
    )


@router.post("/demand-frames", response_model=DemandFrameDraftResponse, status_code=201)
async def create_demand_frame(
    body: CreateDemandFrameRequest,
    repo: ProductIntelligenceRepositoryPort = Depends(get_repository),
    context: ActorContext = Depends(get_actor_context),
) -> DemandFrameDraftResponse:
    _require_ai_provenance(context, body)
    try:
        signal = await commands.create_market_signal(
            repo,
            context,
            raw_text=body.statement,
            source_ref=body.source_refs[0],
        )
        frame = DemandFrame(
            demand_id=signal.id,
            statement=body.statement,
            scenario=body.scenario,
            source_refs=tuple(body.source_refs),
            target_segment=body.target_segment,
            locale=body.locale,
            purpose=body.purpose,
            version="1.0.0",
            evidence_refs=tuple(body.evidence_refs),
            assumptions=tuple(body.assumptions),
            unknowns=tuple(body.unknowns),
            next_validation=body.next_validation,
            expires_at=body.expires_at,
            provenance_ref=body.provenance_ref,
        )
    except ProductIntelligenceDomainError as exc:
        _raise_domain_http(exc)
    except ProductFactoryInputError as exc:
        _raise_contract_http(exc)
    return _demand_response(frame)


@router.post("/market-insights", response_model=MarketInsightDraftResponse, status_code=201)
async def create_market_insight(
    body: CreateMarketInsightDraftRequest,
    repo: ProductIntelligenceRepositoryPort = Depends(get_repository),
    context: ActorContext = Depends(get_actor_context),
) -> MarketInsightDraftResponse:
    _require_ai_provenance(context, body)
    try:
        insight_entity = await commands.create_customer_insight(
            repo,
            context,
            signal_id=body.demand_ref,
            statement=body.statement,
            evidence_refs=body.evidence_refs,
            model_ref=body.model_ref,
            prompt_use_case_version=body.prompt_use_case_version,
            confidence=body.confidence,
        )
        insight = MarketInsightDraft(
            insight_id=insight_entity.id,
            demand_ref=body.demand_ref,
            statement=body.statement,
            source_refs=tuple(body.source_refs),
            competitor_evidence_refs=tuple(body.competitor_evidence_refs),
            segment_ref=body.segment_ref,
            version="1.0.0",
            evidence_refs=tuple(body.evidence_refs),
            assumptions=tuple(body.assumptions),
            unknowns=tuple(body.unknowns),
            next_validation=body.next_validation,
            expires_at=body.expires_at,
            provenance_ref=body.provenance_ref,
        )
    except ProductIntelligenceDomainError as exc:
        _raise_domain_http(exc)
    except ProductFactoryInputError as exc:
        _raise_contract_http(exc)
    return _insight_response(insight)


@router.post(
    "/competitor-evidence",
    response_model=CompetitorEvidenceCardResponse,
    status_code=201,
)
async def create_competitor_evidence(
    body: CreateCompetitorEvidenceCardRequest,
    repo: ProductIntelligenceRepositoryPort = Depends(get_repository),
    context: ActorContext = Depends(get_actor_context),
) -> CompetitorEvidenceCardResponse:
    _require_ai_provenance(context, body)
    try:
        card = CompetitorEvidenceCard(
            evidence_id=f"competitor-evidence:{uuid4().hex}",
            competitor_ref=body.competitor_ref,
            claim=body.claim,
            source_refs=tuple(body.source_refs),
            evidence_status=body.evidence_status,
            demand_ref=body.demand_ref,
            market_insight_ref=body.market_insight_ref,
            source_type=body.source_type,
            evidence_refs=tuple(body.evidence_refs),
            assumptions=tuple(body.assumptions),
            unknowns=tuple(body.unknowns),
            next_validation=body.next_validation,
            expires_at=body.expires_at,
            provenance_ref=body.provenance_ref,
        )
    except ProductFactoryInputError as exc:
        _raise_contract_http(exc)
    saver = getattr(repo, "save_competitor_evidence", None)
    if saver is None:
        raise HTTPException(
            status_code=503,
            detail="competitor_evidence_persistence_not_configured",
        )
    await saver(card, tenant_scope=context.tenant_scope, created_by=context.actor_id)
    return _competitor_response(card)


@router.post(
    "/product-packages",
    response_model=ProductPackageDraftResponse,
    status_code=201,
)
async def create_product_package(
    body: CreateProductPackageDraftRequest,
    repo: ProductIntelligenceRepositoryPort = Depends(get_repository),
    context: ActorContext = Depends(get_actor_context),
) -> ProductPackageDraftResponse:
    _require_ai_provenance(context, body)
    try:
        # Product Factory only proposes a package.  Loading the concept proves
        # the reference exists in the caller's tenant; the eventual named
        # action is responsible for persisting a ProductDefinition after human
        # review.  Calling ``create_education_product_definition`` here would
        # violate the DRAFT-only response contract by writing a domain fact.
        concept = await repo.load_product_concept(body.concept_id, context.tenant_scope)
    except ProductIntelligenceDomainError as exc:
        _raise_domain_http(exc)
    draft_id = f"draft:product-package:{uuid4().hex}"
    return ProductPackageDraftResponse(
        draft_id=draft_id,
        # Kept as a nullable compatibility field: no ProductDefinition exists
        # until a separate human-gated adoption command runs.
        product_definition_id=None,
        concept_id=concept.id,
        product_kind=body.product_kind,
        duration_days=body.duration_days,
        zone="UNIQUE_CANDIDATE" if body.zone == "EXCLUSIVE_CANDIDATE" else body.zone,
        demand_ref=body.demand_ref,
        market_insight_refs=tuple(body.market_insight_refs),
        competitor_evidence_refs=tuple(body.competitor_evidence_refs),
        component_ids=tuple(body.component_ids),
        skill_ids=tuple(body.skill_ids),
        version="1.0.0",
        status="DRAFT",
        evidence_refs=tuple(body.evidence_refs),
        assumptions=tuple(body.assumptions),
        unknowns=tuple(body.unknowns),
        next_validation=body.next_validation,
        expires_at=body.expires_at,
        provenance_ref=body.provenance_ref,
    )


__all__ = ["router"]
