import pytest

from backend.workflow_worker.family_scope_config import resolve_family_worker_scope


def test_scope_requires_explicit_deployment_values():
    with pytest.raises(RuntimeError, match="scope configuration"):
        resolve_family_worker_scope(environ={})


def test_scope_reads_tenant_and_family_without_defaults():
    scope = resolve_family_worker_scope(
        environ={"AIFAMILY_WORKER_TENANT_ID": " t ", "AIFAMILY_WORKER_FAMILY_ID": " f "}
    )
    assert scope.tenant_id == "t"
    assert scope.family_id == "f"
