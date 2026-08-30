from dataclasses import replace

import pytest

from backend.domains.service.domain.errors import ServiceForbiddenError
from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.domains.service.fgcn.entry import (
    DEFAULT_CASE_ENTRY_DEPENDENCIES,
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
    assert stub.calls == 1


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
