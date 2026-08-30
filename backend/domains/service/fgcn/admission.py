"""Provider-admission query contracts for the FGCN assignment boundary.

FGCN does not own provider qualification or admission facts.  It consumes a
small, read-only snapshot from the provider/service capability boundary and
uses it as a final gate before creating a ``TaskAssignment``.  A missing,
malformed, stale, or non-matching snapshot is a refusal, never an implicit
allow.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from backend.domains.service.domain.errors import (
    ServiceConflictError,
    ServiceForbiddenError,
    ServiceValidationError,
)

from .contracts import GateServiceScope


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceValidationError(f"fgcn_provider_admission_{field_name}_required")
    return value.strip()


def _text_tuple(values: object, field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ServiceValidationError(f"fgcn_provider_admission_{field_name}_invalid")
    normalized = tuple(_required_text(value, field_name) for value in values)
    if len(normalized) != len(set(normalized)):
        raise ServiceValidationError(f"fgcn_provider_admission_{field_name}_duplicate")
    return normalized


def _required_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ServiceValidationError(f"fgcn_provider_admission_{field_name}_invalid")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ProviderAdmissionSnapshot:
    """Read-only provider capability/admission data supplied by another port."""

    provider_ref: str
    assignee_kind: str
    admission_status: str
    tenant_id: str
    family_id: str
    credential_ref: str
    credential_valid_from: datetime
    credential_valid_until: datetime
    slot_ref: str
    slot_start_at: datetime
    slot_end_at: datetime
    capability_keys: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    capacity_available: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_ref", _required_text(self.provider_ref, "provider_ref"))
        object.__setattr__(
            self,
            "assignee_kind",
            _required_text(self.assignee_kind, "assignee_kind"),
        )
        object.__setattr__(
            self,
            "admission_status",
            _required_text(self.admission_status, "admission_status").upper(),
        )
        for field_name in ("tenant_id", "family_id", "credential_ref", "slot_ref"):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )
        credential_valid_from = _required_utc(self.credential_valid_from, "credential_valid_from")
        credential_valid_until = _required_utc(
            self.credential_valid_until, "credential_valid_until"
        )
        if credential_valid_until <= credential_valid_from:
            raise ServiceValidationError("fgcn_provider_admission_credential_window_invalid")
        slot_start_at = _required_utc(self.slot_start_at, "slot_start_at")
        slot_end_at = _required_utc(self.slot_end_at, "slot_end_at")
        if slot_end_at <= slot_start_at:
            raise ServiceValidationError("fgcn_provider_admission_slot_window_invalid")
        object.__setattr__(self, "credential_valid_from", credential_valid_from)
        object.__setattr__(self, "credential_valid_until", credential_valid_until)
        object.__setattr__(self, "slot_start_at", slot_start_at)
        object.__setattr__(self, "slot_end_at", slot_end_at)
        object.__setattr__(
            self,
            "capability_keys",
            _text_tuple(self.capability_keys, "capability_key"),
        )
        object.__setattr__(
            self,
            "allowed_purposes",
            _text_tuple(self.allowed_purposes, "allowed_purpose"),
        )
        if type(self.capacity_available) is not int or self.capacity_available < 0:
            raise ServiceValidationError("fgcn_provider_admission_capacity_invalid")


class ProviderAdmissionQuery(Protocol):
    """Synchronous query port used by the in-memory FGCN contract seam."""

    def resolve(
        self,
        *,
        provider_ref: str,
        assignee_kind: str,
        required_capability_keys: tuple[str, ...],
        scope: GateServiceScope,
    ) -> ProviderAdmissionSnapshot | None: ...


class AsyncProviderAdmissionQuery(Protocol):
    """Async query port used by the durable application command."""

    async def resolve(
        self,
        *,
        provider_ref: str,
        assignee_kind: str,
        required_capability_keys: tuple[str, ...],
        scope: GateServiceScope,
    ) -> ProviderAdmissionSnapshot | None: ...


class RejectingProviderAdmissionQuery:
    """Safe default for the synchronous seam when no provider registry is wired."""

    def resolve(
        self,
        *,
        provider_ref: str,
        assignee_kind: str,
        required_capability_keys: tuple[str, ...],
        scope: GateServiceScope,
    ) -> None:
        return None


class AsyncRejectingProviderAdmissionQuery:
    """Safe default for the durable seam when no provider registry is wired."""

    async def resolve(
        self,
        *,
        provider_ref: str,
        assignee_kind: str,
        required_capability_keys: tuple[str, ...],
        scope: GateServiceScope,
    ) -> None:
        return None


DEFAULT_PROVIDER_ADMISSION = RejectingProviderAdmissionQuery()
DEFAULT_ASYNC_PROVIDER_ADMISSION = AsyncRejectingProviderAdmissionQuery()


def assert_provider_admitted(
    snapshot: ProviderAdmissionSnapshot | None,
    *,
    provider_ref: str,
    assignee_kind: str,
    required_capability_keys: tuple[str, ...],
    scope: GateServiceScope,
    effective_at: datetime | None = None,
) -> ProviderAdmissionSnapshot:
    """Enforce the final provider admission relation before a state write."""

    if assignee_kind == "AI":
        raise ServiceForbiddenError("fgcn_service_provider_must_be_human")
    if not isinstance(snapshot, ProviderAdmissionSnapshot):
        raise ServiceForbiddenError("fgcn_provider_not_admitted")
    if snapshot.provider_ref != provider_ref or snapshot.assignee_kind != assignee_kind:
        raise ServiceForbiddenError("fgcn_provider_admission_identity_mismatch")
    if snapshot.tenant_id != scope.tenant_id:
        raise ServiceForbiddenError("fgcn_provider_tenant_scope_violation")
    if snapshot.family_id != scope.family_id:
        raise ServiceForbiddenError("fgcn_provider_family_scope_violation")
    if snapshot.admission_status != "ACTIVE":
        raise ServiceForbiddenError("fgcn_provider_not_admitted")
    if effective_at is None:
        effective_at = datetime.now(UTC)
    effective_at = _required_utc(effective_at, "effective_at")
    if effective_at < snapshot.credential_valid_from:
        raise ServiceForbiddenError("fgcn_provider_credential_not_yet_valid")
    if effective_at > snapshot.credential_valid_until:
        raise ServiceForbiddenError("fgcn_provider_credential_expired")
    if effective_at > snapshot.slot_end_at:
        raise ServiceConflictError("fgcn_provider_slot_unavailable")
    if snapshot.capacity_available == 0:
        raise ServiceConflictError("RESOURCE_GAP")
    if type(snapshot.capacity_available) is not int or snapshot.capacity_available < 0:
        raise ServiceForbiddenError("fgcn_provider_admission_capacity_invalid")
    if scope.purpose not in snapshot.allowed_purposes:
        raise ServiceForbiddenError("fgcn_provider_purpose_not_admitted")
    missing = set(required_capability_keys).difference(snapshot.capability_keys)
    if missing:
        raise ServiceForbiddenError("fgcn_provider_capability_mismatch")
    return snapshot


def require_provider_admitted(
    query: ProviderAdmissionQuery,
    *,
    provider_ref: str,
    assignee_kind: str,
    required_capability_keys: tuple[str, ...],
    scope: GateServiceScope,
    effective_at: datetime | None = None,
) -> ProviderAdmissionSnapshot:
    """Resolve and validate a provider snapshot for the sync engine."""

    try:
        snapshot = query.resolve(
            provider_ref=provider_ref,
            assignee_kind=assignee_kind,
            required_capability_keys=required_capability_keys,
            scope=scope,
        )
    except ServiceForbiddenError:
        raise
    except Exception as exc:
        raise ServiceForbiddenError("fgcn_provider_admission_unavailable") from exc
    return assert_provider_admitted(
        snapshot,
        provider_ref=provider_ref,
        assignee_kind=assignee_kind,
        required_capability_keys=required_capability_keys,
        scope=scope,
        effective_at=effective_at,
    )


async def require_provider_admitted_async(
    query: AsyncProviderAdmissionQuery,
    *,
    provider_ref: str,
    assignee_kind: str,
    required_capability_keys: tuple[str, ...],
    scope: GateServiceScope,
    effective_at: datetime | None = None,
) -> ProviderAdmissionSnapshot:
    """Resolve and validate a provider snapshot for the durable command."""

    try:
        snapshot = await query.resolve(
            provider_ref=provider_ref,
            assignee_kind=assignee_kind,
            required_capability_keys=required_capability_keys,
            scope=scope,
        )
    except ServiceForbiddenError:
        raise
    except Exception as exc:
        raise ServiceForbiddenError("fgcn_provider_admission_unavailable") from exc
    return assert_provider_admitted(
        snapshot,
        provider_ref=provider_ref,
        assignee_kind=assignee_kind,
        required_capability_keys=required_capability_keys,
        scope=scope,
        effective_at=effective_at,
    )


__all__ = [
    "AsyncProviderAdmissionQuery",
    "DEFAULT_ASYNC_PROVIDER_ADMISSION",
    "DEFAULT_PROVIDER_ADMISSION",
    "ProviderAdmissionQuery",
    "ProviderAdmissionSnapshot",
    "RejectingProviderAdmissionQuery",
    "assert_provider_admitted",
    "require_provider_admitted",
    "require_provider_admitted_async",
]
