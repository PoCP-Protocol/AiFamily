"""Typed domain errors for family core.

Each carries a machine-readable `code` rather than prose, so the HTTP layer maps
status codes without string matching. The status mapping lives in
`api/routes.py::_ERROR_STATUS`; the four classes here exist so that mapping is a
dict lookup on a type rather than a chain of `if "not_found" in message`.

`FamilyConflictError` → 409 is load-bearing for the acceptance spec: M1-E2E-01
asserts that replaying an idempotency key with a *different* payload is a 409,
not a silent return of the first result.
"""

from __future__ import annotations


class FamilyDomainError(Exception):
    """Base for every error this domain raises. Never raised directly."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FamilyValidationError(FamilyDomainError):
    """Malformed input — the request could never be valid. → HTTP 400."""


class FamilyForbiddenError(FamilyDomainError):
    """The actor or the family scope forbids this operation. → HTTP 403."""


class FamilyNotFoundError(FamilyDomainError):
    """The referenced family or person does not exist in this scope. → HTTP 404."""


class FamilyConflictError(FamilyDomainError):
    """State conflict — idempotency key reused with a different payload, a
    duplicate relationship, a second active life stage for one child.
    → HTTP 409."""
