"""Domain errors — same naming convention as
`domains/assessment/domain/errors.py` (`{Domain}DomainError` base +
`{Domain}ValidationError/ForbiddenError/NotFoundError/ConflictError`
mapping to HTTP 400/403/404/409). No NestJS predecessor to port from — this
is a new domain — the convention is reused for consistency, not traceability.
"""
from __future__ import annotations


class ProductStrategyDomainError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ProductStrategyValidationError(ProductStrategyDomainError):
    """-> HTTP 400. Raised by `Opportunity.promote_to_invest()` when the
    supplied provenance level cannot establish a claim (simulated/inferred/
    unverified/unknown) — see `packages/contracts/evidence.py`.
    """


class ProductStrategyForbiddenError(ProductStrategyDomainError):
    """-> HTTP 403."""


class ProductStrategyNotFoundError(ProductStrategyDomainError):
    """-> HTTP 404."""


class ProductStrategyConflictError(ProductStrategyDomainError):
    """-> HTTP 409."""
