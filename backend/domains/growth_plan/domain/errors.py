"""Domain errors — the `application`/`api` layers map these to HTTP status
codes (400/403/404/409), mirroring the NestJS exception types used in
`journey-plan.service.ts` (NotFoundException/ForbiddenException/
ConflictException). Keeping the same error-code strings
(`journey_plan_*`, `active_growth_priority_not_found`, ...) preserves
API-observable behavior across the port.
"""
from __future__ import annotations


class GrowthPlanDomainError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class GrowthPlanValidationError(GrowthPlanDomainError):
    """-> HTTP 400."""


class GrowthPlanForbiddenError(GrowthPlanDomainError):
    """-> HTTP 403, port of NestJS ForbiddenException sites
    (missing_required_consent, normal_safety_route_not_verified)."""


class GrowthPlanNotFoundError(GrowthPlanDomainError):
    """-> HTTP 404, port of NestJS NotFoundException sites
    (active_growth_priority_not_found, journey_plan_not_found,
    active_growth_onboarding_not_found and the GrowthSubjectResolver
    404s)."""


class GrowthPlanConflictError(GrowthPlanDomainError):
    """-> HTTP 409, port of NestJS ConflictException sites
    (journey_plan_not_draft, journey_plan_not_active,
    journey_phase_review_not_due, growth_subject_unresolved/ambiguous/
    is_not_child/guardian_unresolved/guardian_mismatch)."""
