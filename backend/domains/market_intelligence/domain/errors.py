"""Domain errors — same convention as `domains/product_strategy/domain/errors.py`."""
from __future__ import annotations


class MarketIntelligenceDomainError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class MarketIntelligenceValidationError(MarketIntelligenceDomainError):
    """-> HTTP 400."""


class MarketIntelligenceNotFoundError(MarketIntelligenceDomainError):
    """-> HTTP 404."""
