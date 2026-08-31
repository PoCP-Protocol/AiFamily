"""Trusted source-resolution boundary for ProductPackage review submissions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from .context import ActorContext
from .product_package_submission import ProductPackageSubmissionInput


class ProductPackageSourceResolutionError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ProductPackageSourceNotFoundError(ProductPackageSourceResolutionError):
    pass


class ProductPackageSourceUnavailableError(ProductPackageSourceResolutionError):
    pass


@dataclass(frozen=True, slots=True)
class ProductPackageDesignIntent:
    """Browser-safe intent; it deliberately contains no governance decisions."""

    source_draft_locator: str
    concept_id: str
    zone_assessment_id: str
    product_kind: str
    duration_days: int
    primary_contradiction: str
    demand_ref: str
    market_insight_refs: tuple[str, ...]
    competitor_evidence_refs: tuple[str, ...]
    component_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]
    success_metric_ids: tuple[str, ...]
    guardrail_ids: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    pause_policy: str
    human_gate_policy: str
    evidence_locators: tuple[str, ...]
    assumptions: tuple[str, ...]
    unknowns: tuple[str, ...]
    next_validation: str
    requested_ttl_hours: int


@dataclass(frozen=True, slots=True)
class ResolvedProductPackageSource:
    source_draft_locator: str
    submission: ProductPackageSubmissionInput


class ProductPackageSourceResolver(Protocol):
    async def resolve(
        self,
        *,
        context: ActorContext,
        intent: ProductPackageDesignIntent,
        now: datetime,
    ) -> ResolvedProductPackageSource: ...


_INTENT_FIELDS = (
    "concept_id",
    "zone_assessment_id",
    "product_kind",
    "duration_days",
    "primary_contradiction",
    "demand_ref",
    "market_insight_refs",
    "competitor_evidence_refs",
    "component_ids",
    "skill_ids",
    "success_metric_ids",
    "guardrail_ids",
    "stop_conditions",
    "pause_policy",
    "human_gate_policy",
    "assumptions",
    "unknowns",
    "next_validation",
)


async def resolve_product_package_source(
    resolver: ProductPackageSourceResolver,
    context: ActorContext,
    intent: ProductPackageDesignIntent,
    *,
    now: datetime,
) -> ProductPackageSubmissionInput:
    """Resolve server facts and reject a mismatched or overlong-lived resolution."""

    resolved = await resolver.resolve(context=context, intent=intent, now=now)
    if resolved.source_draft_locator != intent.source_draft_locator:
        raise ProductPackageSourceResolutionError("PRODUCT_PACKAGE_SOURCE_LOCATOR_MISMATCH")
    source = resolved.submission
    if any(getattr(source, field) != getattr(intent, field) for field in _INTENT_FIELDS):
        raise ProductPackageSourceResolutionError("PRODUCT_PACKAGE_SOURCE_INTENT_MISMATCH")
    if tuple(source.evidence_refs) != tuple(intent.evidence_locators):
        raise ProductPackageSourceResolutionError("PRODUCT_PACKAGE_EVIDENCE_LOCATOR_MISMATCH")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ProductPackageSourceResolutionError("PRODUCT_PACKAGE_RESOLUTION_NOW_MUST_BE_AWARE")
    if source.expires_at.tzinfo is None or source.expires_at.utcoffset() is None:
        raise ProductPackageSourceResolutionError("PRODUCT_PACKAGE_SOURCE_EXPIRY_MUST_BE_AWARE")
    maximum_expiry = now + timedelta(hours=intent.requested_ttl_hours)
    if source.expires_at > maximum_expiry:
        raise ProductPackageSourceResolutionError("PRODUCT_PACKAGE_SOURCE_TTL_EXCEEDED")
    return source


__all__ = [
    "ProductPackageDesignIntent",
    "ProductPackageSourceNotFoundError",
    "ProductPackageSourceResolutionError",
    "ProductPackageSourceResolver",
    "ProductPackageSourceUnavailableError",
    "ResolvedProductPackageSource",
    "resolve_product_package_source",
]
