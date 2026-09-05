from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.domains.service.domain.errors import ServiceForbiddenError
from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.domains.service.fgcn.entry import (
    DEFAULT_CASE_ENTRY_DEPENDENCIES,
    FamilyRequestRef,
    require_case_entry_dependencies,
    require_case_entry_dependencies_async,
)
from tests.domains.service.fgcn.entry_test_doubles import (
    AsyncCaseEntryDependencyStub,
    SyncCaseEntryDependencyStub,
    valid_entry_snapshot,
)


def _scope() -> GateServiceScope:
    return GateServiceScope(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_person_id="child-1",
        purpose="service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr-entry-1",
    )


@pytest.mark.parametrize(
    ("change", "error_code"),
    (
        ({"growth_intent_status": "DRAFT"}, "fgcn_growth_intent_not_confirmed"),
        ({"consent_status": "REVOKED"}, "fgcn_consent_not_active"),
        ({"consent_purpose": "unrelated-purpose"}, "fgcn_consent_scope_mismatch"),
        ({"consent_version": "consent.v2"}, "fgcn_consent_scope_mismatch"),
        ({"consent_subject_person_id": "another-child"}, "fgcn_consent_scope_mismatch"),
        ({"binding_tenant_id": "foreign-tenant"}, "fgcn_tenant_family_binding_invalid"),
        ({"binding_family_id": "foreign-family"}, "fgcn_tenant_family_binding_invalid"),
        ({"binding_status": "REVOKED"}, "fgcn_tenant_family_binding_invalid"),
    ),
)
def test_entry_gate_rejects_each_invalid_dependency(change, error_code):
    scope = _scope()
    snapshot = valid_entry_snapshot(scope, intent_ref="intent-1")
    snapshot = replace(snapshot, **change)

    with pytest.raises(ServiceForbiddenError, match=error_code):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(snapshot),
            scope=scope,
            intent_ref="intent-1",
        )


def test_entry_gate_rejects_intent_identity_mismatch_and_missing_query():
    scope = _scope()
    snapshot = valid_entry_snapshot(scope, intent_ref="other-intent")

    with pytest.raises(ServiceForbiddenError, match="fgcn_growth_intent_identity_mismatch"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(snapshot),
            scope=scope,
            intent_ref="intent-1",
        )
    with pytest.raises(ServiceForbiddenError, match="fgcn_case_entry_dependencies_unavailable"):
        require_case_entry_dependencies(
            DEFAULT_CASE_ENTRY_DEPENDENCIES,
            scope=scope,
            intent_ref="intent-1",
        )


def test_entry_gate_accepts_exact_intent_consent_and_binding_snapshot():
    scope = _scope()
    stub = SyncCaseEntryDependencyStub(valid_entry_snapshot(scope, intent_ref="intent-1"))

    result = require_case_entry_dependencies(stub, scope=scope, intent_ref="intent-1")

    assert result.growth_intent_status == "CONFIRMED"
    assert result.consent_status == "ACTIVE"
    assert result.binding_tenant_id == scope.tenant_id
    assert result.family_request.initiated_by == "FAMILY"
    assert len(result.self_help_actions) == 2
    assert len(result.self_help_observations) == 2
    assert stub.calls == 1


def test_entry_gate_rejects_withdrawn_deleted_and_expired_canonical_request_refs():
    scope = _scope()
    snapshot = valid_entry_snapshot(scope, intent_ref="intent-1")

    with pytest.raises(ServiceForbiddenError, match="fgcn_family_request_withdrawn"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(
                replace(
                    snapshot, family_request=replace(snapshot.family_request, status="WITHDRAWN")
                )
            ),
            scope=scope,
            intent_ref="intent-1",
        )
    with pytest.raises(ServiceForbiddenError, match="fgcn_family_request_expired_or_deleted"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(
                replace(snapshot, family_request=replace(snapshot.family_request, status="DELETED"))
            ),
            scope=scope,
            intent_ref="intent-1",
        )
    with pytest.raises(ServiceForbiddenError, match="fgcn_family_request_expired_or_deleted"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(
                replace(
                    snapshot,
                    family_request=replace(
                        snapshot.family_request,
                        expires_at=datetime.now(UTC) - timedelta(minutes=1),
                    ),
                )
            ),
            scope=scope,
            intent_ref="intent-1",
        )


def test_entry_gate_rejects_forged_cross_scope_and_untraceable_action_refs():
    scope = _scope()
    snapshot = valid_entry_snapshot(scope, intent_ref="intent-1")
    forged_request = replace(snapshot.family_request, ref="family-request:forged")
    with pytest.raises(ServiceForbiddenError, match="fgcn_self_help_action_reference_invalid"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(replace(snapshot, family_request=forged_request)),
            scope=scope,
            intent_ref="intent-1",
        )

    foreign_request = replace(snapshot.family_request, tenant_id="tenant-foreign")
    with pytest.raises(ServiceForbiddenError, match="fgcn_family_request_scope_mismatch"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(replace(snapshot, family_request=foreign_request)),
            scope=scope,
            intent_ref="intent-1",
        )

    with pytest.raises(ServiceForbiddenError, match="fgcn_repeated_self_help_evidence_required"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(
                replace(
                    snapshot,
                    self_help_actions=(snapshot.self_help_actions[0],),
                    self_help_observations=(snapshot.self_help_observations[0],),
                )
            ),
            scope=scope,
            intent_ref="intent-1",
        )


def test_entry_gate_rejects_cross_scope_or_deleted_observation_reference():
    scope = _scope()
    snapshot = valid_entry_snapshot(scope, intent_ref="intent-1")
    foreign = replace(snapshot.self_help_observations[1], tenant_id="tenant-foreign")
    with pytest.raises(ServiceForbiddenError, match="fgcn_self_help_observation_reference_invalid"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(
                replace(
                    snapshot, self_help_observations=(snapshot.self_help_observations[0], foreign)
                )
            ),
            scope=scope,
            intent_ref="intent-1",
        )
    deleted = replace(snapshot.self_help_observations[1], status="DELETED")
    with pytest.raises(
        ServiceForbiddenError, match="fgcn_self_help_observation_expired_or_deleted"
    ):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(
                replace(
                    snapshot, self_help_observations=(snapshot.self_help_observations[0], deleted)
                )
            ),
            scope=scope,
            intent_ref="intent-1",
        )


def test_entry_gate_rejects_expired_action_and_mismatched_version_or_locale():
    scope = _scope()
    snapshot = valid_entry_snapshot(scope, intent_ref="intent-1")
    expired = replace(
        snapshot.self_help_actions[1],
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    with pytest.raises(ServiceForbiddenError, match="fgcn_self_help_action_expired_or_deleted"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(
                replace(
                    snapshot,
                    self_help_actions=(snapshot.self_help_actions[0], expired),
                )
            ),
            scope=scope,
            intent_ref="intent-1",
        )
    wrong_version = replace(snapshot.self_help_actions[1], version=2)
    with pytest.raises(ServiceForbiddenError, match="fgcn_self_help_action_reference_invalid"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(
                replace(
                    snapshot,
                    self_help_actions=(snapshot.self_help_actions[0], wrong_version),
                )
            ),
            scope=scope,
            intent_ref="intent-1",
        )
    with pytest.raises(ServiceForbiddenError, match="fgcn_case_entry_locale_mismatch"):
        require_case_entry_dependencies(
            SyncCaseEntryDependencyStub(replace(snapshot, locale="zh")),
            scope=scope,
            intent_ref="intent-1",
        )


def test_family_request_ref_must_be_family_initiated():
    with pytest.raises(ServiceForbiddenError, match="fgcn_family_request_must_be_family_initiated"):
        FamilyRequestRef(
            ref="family-request:not-family",
            tenant_id="tenant-1",
            family_id="family-1",
            intent_ref="intent-1",
            status="ACTIVE",
            version=1,
            locale="en",
            initiated_by="PROVIDER",
        )


@pytest.mark.asyncio
async def test_async_entry_gate_fail_closes_when_dependency_query_fails():
    scope = _scope()
    query = AsyncCaseEntryDependencyStub(None, error=RuntimeError("dependency store down"))

    with pytest.raises(ServiceForbiddenError, match="fgcn_case_entry_dependencies_unavailable"):
        await require_case_entry_dependencies_async(query, scope=scope, intent_ref="intent-1")

    assert query.calls == 1


@pytest.mark.asyncio
async def test_async_entry_gate_accepts_exact_snapshot():
    scope = _scope()
    query = AsyncCaseEntryDependencyStub(valid_entry_snapshot(scope, intent_ref="intent-1"))

    result = await require_case_entry_dependencies_async(query, scope=scope, intent_ref="intent-1")

    assert result.intent_ref == "intent-1"
    assert query.calls == 1
