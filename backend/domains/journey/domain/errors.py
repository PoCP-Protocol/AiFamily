"""Errors owned by the Journey domain.

The API adapter maps these stable codes to HTTP responses.  Keeping the
domain independent of FastAPI means the same state machine can later be used
by the workflow worker or a PostgreSQL application service.
"""

from __future__ import annotations


class JourneyDomainError(Exception):
    """Base error with an API-stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class JourneyValidationError(JourneyDomainError):
    """The command is structurally invalid."""


class JourneyForbiddenError(JourneyDomainError):
    """The trusted actor cannot operate on this family."""


class JourneyNotFoundError(JourneyDomainError):
    """A scoped aggregate or prerequisite is absent."""


class JourneyConflictError(JourneyDomainError):
    """The command conflicts with current state or idempotency history."""
