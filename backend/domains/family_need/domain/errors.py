"""Stable, API-agnostic errors raised by Family Need domain policies."""

from __future__ import annotations


class FamilyNeedDomainError(Exception):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


class FamilyNeedValidationError(FamilyNeedDomainError):
    """Input violates a domain invariant (HTTP 400 at an adapter)."""


class FamilyNeedForbiddenError(FamilyNeedDomainError):
    """Actor, tenant, subject or purpose is not allowed (HTTP 403)."""


class FamilyNeedNotFoundError(FamilyNeedDomainError):
    """A referenced aggregate or supply object is not visible (HTTP 404)."""


class FamilyNeedConflictError(FamilyNeedDomainError):
    """State transition, idempotency or version conflict (HTTP 409)."""


class FamilyNeedResourceGapError(FamilyNeedDomainError):
    """The requested need is valid, but no qualified supply is available."""

    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__("resource_gap", detail or reason)
        self.reason = reason
