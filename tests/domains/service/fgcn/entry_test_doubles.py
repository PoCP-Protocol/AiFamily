"""Test-only entry dependency adapters for FGCN case-opening tests."""

from __future__ import annotations

from dataclasses import dataclass

from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.domains.service.fgcn.entry import CaseEntryDependencySnapshot


@dataclass
class SyncCaseEntryDependencyStub:
    snapshot: CaseEntryDependencySnapshot | None
    error: Exception | None = None
    calls: int = 0

    def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> CaseEntryDependencySnapshot | None:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.snapshot


@dataclass
class AsyncCaseEntryDependencyStub:
    snapshot: CaseEntryDependencySnapshot | None
    error: Exception | None = None
    calls: int = 0

    async def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> CaseEntryDependencySnapshot | None:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.snapshot


def valid_entry_snapshot(
    scope: GateServiceScope,
    *,
    intent_ref: str,
    growth_intent_status: str = "CONFIRMED",
    consent_subject_person_id: str | None = None,
    consent_purpose: str | None = None,
    consent_version: str | None = None,
    consent_status: str = "ACTIVE",
    binding_tenant_id: str | None = None,
    binding_family_id: str | None = None,
    binding_status: str = "ACTIVE",
) -> CaseEntryDependencySnapshot:
    return CaseEntryDependencySnapshot(
        intent_ref=intent_ref,
        growth_intent_status=growth_intent_status,
        consent_subject_person_id=consent_subject_person_id or scope.subject_person_id,
        consent_purpose=consent_purpose or scope.purpose,
        consent_version=consent_version or scope.consent_version,
        consent_status=consent_status,
        binding_tenant_id=binding_tenant_id or scope.tenant_id,
        binding_family_id=binding_family_id or scope.family_id,
        binding_status=binding_status,
    )


__all__ = [
    "AsyncCaseEntryDependencyStub",
    "SyncCaseEntryDependencyStub",
    "valid_entry_snapshot",
]
