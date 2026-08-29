"""Domain errors — same four-way split as the membership domain, so the HTTP
layer can map them identically without either domain importing the other."""

from __future__ import annotations


class LoyaltyPointsDomainError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class LoyaltyPointsValidationError(LoyaltyPointsDomainError):
    """-> HTTP 400. Bad input."""


class LoyaltyPointsForbiddenError(LoyaltyPointsDomainError):
    """-> HTTP 403.

    Refusals of principle, not bad input: an `ai:` actor adjusting a balance,
    a forbidden earn source (测评分/家庭分/排名), a reward kind that would let
    points buy a membership tier, anything outside the fixture-only boundary.
    """


class LoyaltyPointsNotFoundError(LoyaltyPointsDomainError):
    """-> HTTP 404."""


class LoyaltyPointsConflictError(LoyaltyPointsDomainError):
    """-> HTTP 409.

    Append-only / arithmetic violations: spending more than the balance,
    exceeding a rule's daily or total cap, redeeming an already-cancelled
    redemption.
    """
