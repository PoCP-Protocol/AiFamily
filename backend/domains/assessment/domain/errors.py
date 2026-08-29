"""Domain errors — the `application`/`api` layers map these to HTTP status
codes (400/403/404/409), mirroring the Nest exception types used in
`assessment.service.ts` / `growth-hypothesis.service.ts`
(BadRequestException/ForbiddenException/NotFoundException/ConflictException).
Keeping the same error-code strings (`assessment_*`, `growth_hypothesis_*`)
preserves API-observable behavior across the port.
"""
from __future__ import annotations


class AssessmentDomainError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class AssessmentValidationError(AssessmentDomainError):
    """-> HTTP 400, port of NestJS BadRequestException sites."""


class AssessmentForbiddenError(AssessmentDomainError):
    """-> HTTP 403, port of NestJS ForbiddenException sites."""


class AssessmentNotFoundError(AssessmentDomainError):
    """-> HTTP 404, port of NestJS NotFoundException sites."""


class AssessmentConflictError(AssessmentDomainError):
    """-> HTTP 409, port of NestJS ConflictException sites."""
