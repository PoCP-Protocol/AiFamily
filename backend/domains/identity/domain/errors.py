"""Domain errors — same convention as `domains/membership/domain/errors.py`."""

from __future__ import annotations


class IdentityDomainError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class IdentityValidationError(IdentityDomainError):
    """-> HTTP 422/400. Malformed or missing required input."""


class IdentityUnauthenticatedError(IdentityDomainError):
    """-> HTTP 401.

    "No usable credential": missing bearer, malformed bearer, unknown token,
    or a token whose session has expired/been revoked. Deliberately distinct
    from :class:`IdentityForbiddenError` — see `resolve_actor`'s docstring in
    `backend/domains/assessment/api/dev_auth.py`, which this domain's API
    layer must preserve: collapsing 401 and 403 would tell a caller with a
    valid token for family A that family B does not exist.
    """


class IdentityForbiddenError(IdentityDomainError):
    """-> HTTP 403. Credential is valid but not scoped to the requested family."""


class IdentityNotFoundError(IdentityDomainError):
    """-> HTTP 404."""
