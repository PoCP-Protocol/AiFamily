"""Typed domain errors for the service booking chain.

Each error carries a machine-readable `code` rather than a prose message, so
the HTTP layer can map it to a status without string matching and the mobile
client sees the same `detail` codes the source repository's contract documents
(`contracts/frontend/UI-06_SERVICE_JOURNEY_PRIVATE_CHECKIN_API_CONTRACT_001.md`
§6, and the `family-service-booking.service.ts` exception codes).
"""

from __future__ import annotations


class ServiceDomainError(Exception):
    """Base for every error this domain raises. Never raised directly."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ServiceValidationError(ServiceDomainError):
    """Malformed input — the request could never be valid. → HTTP 400."""


class ServiceForbiddenError(ServiceDomainError):
    """The actor/family/consent state forbids this operation. → HTTP 403.

    Includes the consent failures: a booking without an active `SERVICE`
    consent grant is not a validation problem, it is a refusal.
    """


class ServiceNotFoundError(ServiceDomainError):
    """The referenced supply/booking does not exist in this scope. → HTTP 404."""


class ServiceConflictError(ServiceDomainError):
    """State conflict — slot taken, idempotency key reused with a different
    payload, record already produced. → HTTP 409."""
