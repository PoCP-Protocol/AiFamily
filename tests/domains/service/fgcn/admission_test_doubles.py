"""Test-only provider admission adapters for the FGCN contract tests."""

from __future__ import annotations

from dataclasses import dataclass

from backend.domains.service.fgcn.admission import ProviderAdmissionSnapshot
from backend.domains.service.fgcn.contracts import GateServiceScope


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
    capability_keys: tuple[str, ...] = (),
    allowed_purposes: tuple[str, ...] = ("service_collaboration",),
    capacity_available: int = 1,
) -> ProviderAdmissionSnapshot:
    return ProviderAdmissionSnapshot(
        provider_ref=provider_ref,
        assignee_kind=assignee_kind,
        admission_status=admission_status,
        capability_keys=capability_keys,
        allowed_purposes=allowed_purposes,
        capacity_available=capacity_available,
    )
