"""Domain errors — same convention as `domains/assessment/domain/errors.py`
and `domains/product_strategy/domain/errors.py`."""
from __future__ import annotations


class ProductIntelligenceDomainError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ProductIntelligenceValidationError(ProductIntelligenceDomainError):
    """-> HTTP 400."""


class ProductIntelligenceNotFoundError(ProductIntelligenceDomainError):
    """-> HTTP 404."""


class ProductIntelligenceForbiddenError(ProductIntelligenceDomainError):
    """-> HTTP 403. Raised when a non-human actor attempts to validate a
    hypothesis or approve a contradiction/strategy — see
    `domain/entities.py` `GrowthHypothesis.mark_validated`.
    """
