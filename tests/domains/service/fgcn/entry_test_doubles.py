"""Test-only entry dependency adapters for FGCN case-opening tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.domains.service.fgcn.entry import (
    ActionRecordRef,
    CaseEntryDependencySnapshot,
    FamilyRequestRef,
    ObservationRef,
)


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
    request = FamilyRequestRef(
        ref="family-request:s01",
        tenant_id=binding_tenant_id or scope.tenant_id,
        family_id=binding_family_id or scope.family_id,
        intent_ref=intent_ref,
        status="ACTIVE",
        version=1,
        locale="en",
    )
    action_one = ActionRecordRef(
        ref="action-record:self-help-1",
        family_request_ref=request.ref,
        tenant_id=request.tenant_id,
        family_id=request.family_id,
        intent_ref=intent_ref,
        action_type="SELF_HELP",
        outcome="FAILED",
        status="COMPLETED",
        version=request.version,
        locale=request.locale,
        observation_refs=("observation:self-help-1",),
        occurred_at=datetime(2026, 8, 29, 9, tzinfo=UTC),
    )
    action_two = ActionRecordRef(
        ref="action-record:self-help-2",
        family_request_ref=request.ref,
        tenant_id=request.tenant_id,
        family_id=request.family_id,
        intent_ref=intent_ref,
        action_type="SELF_HELP",
        outcome="FAILED",
        status="COMPLETED",
        version=request.version,
        locale=request.locale,
        observation_refs=("observation:self-help-2",),
        occurred_at=datetime(2026, 8, 30, 9, tzinfo=UTC),
    )
    observations = (
        ObservationRef(
            ref="observation:self-help-1",
            action_ref=action_one.ref,
            family_request_ref=request.ref,
            tenant_id=request.tenant_id,
            family_id=request.family_id,
            intent_ref=intent_ref,
            kind="SELF_HELP_OUTCOME",
            value="FAILED",
            status="RECORDED",
            version=request.version,
            locale=request.locale,
            observed_at=action_one.occurred_at,
        ),
        ObservationRef(
            ref="observation:self-help-2",
            action_ref=action_two.ref,
            family_request_ref=request.ref,
            tenant_id=request.tenant_id,
            family_id=request.family_id,
            intent_ref=intent_ref,
            kind="SELF_HELP_OUTCOME",
            value="FAILED",
            status="RECORDED",
            version=request.version,
            locale=request.locale,
            observed_at=action_two.occurred_at,
        ),
    )
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
        family_request=request,
        self_help_actions=(action_one, action_two),
        self_help_observations=observations,
        locale=request.locale,
    )


__all__ = [
    "AsyncCaseEntryDependencyStub",
    "SyncCaseEntryDependencyStub",
    "valid_entry_snapshot",
]
