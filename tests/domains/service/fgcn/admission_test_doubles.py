"""Test-only provider admission adapters for the FGCN contract tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.domains.service.fgcn.admission import ProviderAdmissionSnapshot
from backend.domains.service.fgcn.contracts import GateServiceScope

_VALID_FROM = datetime(2026, 1, 1, tzinfo=UTC)
_VALID_UNTIL = datetime(2099, 1, 1, tzinfo=UTC)
_SLOT_START = datetime(2026, 1, 1, tzinfo=UTC)
_SLOT_END = datetime(2099, 1, 1, tzinfo=UTC)


@dataclass
class SyncProviderAdmissionStub:
    snapshot: ProviderAdmissionSnapshot | None

    def resolve(
        self,
        *,
        provider_ref: str,
        assignee_kind: str,
        required_capability_keys: tuple[str, ...],
        scope: GateServiceScope,
    ) -> ProviderAdmissionSnapshot | None:
        return self.snapshot


@dataclass
class AsyncProviderAdmissionStub:
    snapshot: ProviderAdmissionSnapshot | None

    async def resolve(
        self,
        *,
        provider_ref: str,
        assignee_kind: str,
        required_capability_keys: tuple[str, ...],
        scope: GateServiceScope,
    ) -> ProviderAdmissionSnapshot | None:
        return self.snapshot


def admitted_snapshot(
    *,
    provider_ref: str = "expert-1",
    assignee_kind: str = "EXPERT",
    admission_status: str = "ACTIVE",
    tenant_id: str = "tenant-1",
    family_id: str = "family-1",
    credential_ref: str = "credential:expert-1:v1",
    credential_valid_from: datetime = _VALID_FROM,
    credential_valid_until: datetime = _VALID_UNTIL,
    slot_ref: str = "slot:expert-1:default",
    slot_start_at: datetime = _SLOT_START,
    slot_end_at: datetime = _SLOT_END,
    capability_keys: tuple[str, ...] = (),
    allowed_purposes: tuple[str, ...] = ("service_collaboration",),
    capacity_available: int = 1,
) -> ProviderAdmissionSnapshot:
    return ProviderAdmissionSnapshot(
        provider_ref=provider_ref,
        assignee_kind=assignee_kind,
        admission_status=admission_status,
        tenant_id=tenant_id,
        family_id=family_id,
        credential_ref=credential_ref,
        credential_valid_from=credential_valid_from,
        credential_valid_until=credential_valid_until,
        slot_ref=slot_ref,
        slot_start_at=slot_start_at,
        slot_end_at=slot_end_at,
        capability_keys=capability_keys,
        allowed_purposes=allowed_purposes,
        capacity_available=capacity_available,
    )
