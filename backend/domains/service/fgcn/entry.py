"""Entry dependency query contracts for opening an FGCN service case.

FGCN does not own GrowthIntent, Consent, or tenant-family binding facts.  A
case can only be opened after a read-only dependency query proves all three
relations for the exact scope and intent.  Missing, malformed, stale, or
failed dependency queries are refusals rather than implicit allows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.domains.service.domain.errors import ServiceForbiddenError, ServiceValidationError

from .contracts import GateServiceScope

_CONFIRMED_GROWTH_INTENT_STATUS = "CONFIRMED"
_ACTIVE_CONSENT_STATUS = "ACTIVE"
_ACTIVE_BINDING_STATUS = "ACTIVE"


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceValidationError(f"fgcn_case_entry_{field_name}_required")
    return value.strip()


def _status(value: object, field_name: str) -> str:
    return _required_text(value, field_name).upper()


@dataclass(frozen=True, slots=True)
class CaseEntryDependencySnapshot:
    """Read-only evidence required before a new ``ServiceCase`` is written."""

    intent_ref: str
    growth_intent_status: str
    consent_subject_person_id: str
    consent_purpose: str
    consent_version: str
    consent_status: str
    binding_tenant_id: str
    binding_family_id: str
    binding_status: str
    family_initiated_request: bool = False
    family_request_ref: str = ""
    self_help_failed_attempts: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_ref", _required_text(self.intent_ref, "intent_ref"))
        object.__setattr__(
            self,
            "growth_intent_status",
            _status(self.growth_intent_status, "growth_intent_status"),
        )
        object.__setattr__(
            self,
            "consent_subject_person_id",
            _required_text(self.consent_subject_person_id, "consent_subject_person_id"),
        )
        object.__setattr__(
            self,
            "consent_purpose",
            _required_text(self.consent_purpose, "consent_purpose"),
        )
        object.__setattr__(
            self,
            "consent_version",
            _required_text(self.consent_version, "consent_version"),
        )
        object.__setattr__(self, "consent_status", _status(self.consent_status, "consent_status"))
        object.__setattr__(
            self,
            "binding_tenant_id",
            _required_text(self.binding_tenant_id, "binding_tenant_id"),
        )
        object.__setattr__(
            self,
            "binding_family_id",
            _required_text(self.binding_family_id, "binding_family_id"),
        )
        object.__setattr__(self, "binding_status", _status(self.binding_status, "binding_status"))
        if type(self.family_initiated_request) is not bool:
            raise ServiceValidationError("fgcn_case_entry_family_request_invalid")
        object.__setattr__(
            self,
            "family_request_ref",
            _required_text(self.family_request_ref, "family_request_ref"),
        )
        if type(self.self_help_failed_attempts) is not int or self.self_help_failed_attempts < 0:
            raise ServiceValidationError("fgcn_case_entry_self_help_failures_invalid")


class CaseEntryDependencyQuery(Protocol):
    """Synchronous query port used by the in-memory FGCN engine."""

    def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> CaseEntryDependencySnapshot | None: ...


class AsyncCaseEntryDependencyQuery(Protocol):
    """Async query port used by the durable FGCN opening command."""

    async def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> CaseEntryDependencySnapshot | None: ...


class RejectingCaseEntryDependencyQuery:
    """Safe default when GrowthIntent/Consent/binding stores are not wired."""

    def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> None:
        return None


class AsyncRejectingCaseEntryDependencyQuery:
    """Safe durable default when the dependency boundary is not wired."""

    async def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> None:
        return None


DEFAULT_CASE_ENTRY_DEPENDENCIES = RejectingCaseEntryDependencyQuery()
DEFAULT_ASYNC_CASE_ENTRY_DEPENDENCIES = AsyncRejectingCaseEntryDependencyQuery()


def assert_case_entry_dependencies(
    snapshot: CaseEntryDependencySnapshot | None,
    *,
    scope: GateServiceScope,
    intent_ref: str,
) -> CaseEntryDependencySnapshot:
    """Enforce the exact GrowthIntent/Consent/binding relation for a case."""

    if not isinstance(snapshot, CaseEntryDependencySnapshot):
        raise ServiceForbiddenError("fgcn_case_entry_dependencies_unavailable")
    if snapshot.intent_ref != intent_ref:
        raise ServiceForbiddenError("fgcn_growth_intent_identity_mismatch")
    if snapshot.growth_intent_status != _CONFIRMED_GROWTH_INTENT_STATUS:
        raise ServiceForbiddenError("fgcn_growth_intent_not_confirmed")
    if not snapshot.family_initiated_request:
        raise ServiceForbiddenError("fgcn_family_request_required")
    if snapshot.self_help_failed_attempts < 2:
        raise ServiceForbiddenError("fgcn_repeated_self_help_failure_required")
    if snapshot.consent_status != _ACTIVE_CONSENT_STATUS:
        raise ServiceForbiddenError("fgcn_consent_not_active")
    if (
        snapshot.consent_subject_person_id != scope.subject_person_id
        or snapshot.consent_purpose != scope.purpose
        or snapshot.consent_version != scope.consent_version
    ):
        raise ServiceForbiddenError("fgcn_consent_scope_mismatch")
    if (
        snapshot.binding_status != _ACTIVE_BINDING_STATUS
        or snapshot.binding_tenant_id != scope.tenant_id
        or snapshot.binding_family_id != scope.family_id
    ):
        raise ServiceForbiddenError("fgcn_tenant_family_binding_invalid")
    return snapshot


def require_case_entry_dependencies(
    query: CaseEntryDependencyQuery,
    *,
    scope: GateServiceScope,
    intent_ref: str,
) -> CaseEntryDependencySnapshot:
    """Resolve and validate entry evidence for the synchronous engine."""

    try:
        snapshot = query.resolve(scope=scope, intent_ref=intent_ref)
    except ServiceForbiddenError:
        raise
    except Exception as exc:
        raise ServiceForbiddenError("fgcn_case_entry_dependencies_unavailable") from exc
    return assert_case_entry_dependencies(snapshot, scope=scope, intent_ref=intent_ref)


async def require_case_entry_dependencies_async(
    query: AsyncCaseEntryDependencyQuery,
    *,
    scope: GateServiceScope,
    intent_ref: str,
) -> CaseEntryDependencySnapshot:
    """Resolve and validate entry evidence for the durable command."""

    try:
        snapshot = await query.resolve(scope=scope, intent_ref=intent_ref)
    except ServiceForbiddenError:
        raise
    except Exception as exc:
        raise ServiceForbiddenError("fgcn_case_entry_dependencies_unavailable") from exc
    return assert_case_entry_dependencies(snapshot, scope=scope, intent_ref=intent_ref)


__all__ = [
    "AsyncCaseEntryDependencyQuery",
    "AsyncRejectingCaseEntryDependencyQuery",
    "CaseEntryDependencyQuery",
    "CaseEntryDependencySnapshot",
    "DEFAULT_ASYNC_CASE_ENTRY_DEPENDENCIES",
    "DEFAULT_CASE_ENTRY_DEPENDENCIES",
    "RejectingCaseEntryDependencyQuery",
    "assert_case_entry_dependencies",
    "require_case_entry_dependencies",
    "require_case_entry_dependencies_async",
]
