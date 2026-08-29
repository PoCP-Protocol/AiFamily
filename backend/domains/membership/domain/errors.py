"""Domain errors — same convention as
`domains/product_intelligence/domain/errors.py`."""

from __future__ import annotations


class MembershipDomainError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class MembershipValidationError(MembershipDomainError):
    """-> HTTP 400."""


class MembershipForbiddenError(MembershipDomainError):
    """-> HTTP 403.

    Raised when an actor or an activation source is structurally not allowed
    to do the thing — an `ai:` actor granting a tier (baseline invariant 3),
    a points redemption used as an activation source (invariant 4), a client
    asking for a production/external effect outside the fixture-only
    boundary. These are refusals of principle, not bad input.
    """


class MembershipNotFoundError(MembershipDomainError):
    """-> HTTP 404."""


class MembershipConflictError(MembershipDomainError):
    """-> HTTP 409.

    Raised on append-only / immutability violations: rewriting a closed
    `MembershipPeriod` (invariant 8), reusing a `period_ref`, consuming more
    units than a grant holds.
    """
