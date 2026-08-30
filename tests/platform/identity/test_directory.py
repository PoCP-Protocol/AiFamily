"""TenantDirectory — the lookup that turns `TenantContext.is_active` into a gate.

`TenantContext.is_active` shipped with zero callers anywhere in the repository
(`docs/06_platform/IDENTITY.md` §3 gap 3), so "a suspended tenant must not
operate" was an unenforced sentence. These tests cover the lookup half; the
enforcement half — that `PolicyEngine` actually refuses a suspended or unknown
tenant — lives in `tests/platform/authorization/test_tenant_gate.py`.
"""

from __future__ import annotations

import pytest

from backend.platform.identity.context import TenantStatus
from backend.platform.identity.directory import (
    DenyAllTenantDirectory,
    InMemoryTenantDirectory,
)


def test_deny_all_directory_resolves_nothing() -> None:
    """The production default must not invent an ACTIVE tenant.

    There is no tenant store in this repository yet. A directory that answered
    "active" for anything it had never heard of would fail open for every tenant
    nobody remembered to register.
    """
    assert DenyAllTenantDirectory().resolve("tenant-1") is None


def test_unregistered_tenant_resolves_to_none_not_a_default_status() -> None:
    directory = InMemoryTenantDirectory({"tenant-1": TenantStatus.ACTIVE})
    assert directory.resolve("tenant-2") is None


def test_registered_tenant_resolves_with_its_status() -> None:
    directory = InMemoryTenantDirectory({"tenant-1": TenantStatus.SUSPENDED})

    resolved = directory.resolve("tenant-1")

    assert resolved is not None
    assert resolved.tenant_id == "tenant-1"
    assert resolved.status is TenantStatus.SUSPENDED
    assert resolved.is_active is False


@pytest.mark.parametrize(
    ("status", "expected_active"),
    [
        (TenantStatus.ACTIVE, True),
        (TenantStatus.SUSPENDED, False),
        (TenantStatus.ARCHIVED, False),
    ],
)
def test_is_active_is_true_only_for_active(status: TenantStatus, expected_active: bool) -> None:
    """ARCHIVED is as inert as SUSPENDED — neither may act."""
    directory = InMemoryTenantDirectory({"tenant-1": status})
    resolved = directory.resolve("tenant-1")

    assert resolved is not None
    assert resolved.is_active is expected_active


def test_register_rejects_empty_tenant_id() -> None:
    with pytest.raises(ValueError):
        InMemoryTenantDirectory().register("", TenantStatus.ACTIVE)


def test_directory_copies_the_mapping_it_is_given() -> None:
    """A caller mutating its own dict afterwards must not silently reactivate a tenant."""
    seed = {"tenant-1": TenantStatus.SUSPENDED}
    directory = InMemoryTenantDirectory(seed)
    seed["tenant-1"] = TenantStatus.ACTIVE

    resolved = directory.resolve("tenant-1")
    assert resolved is not None
    assert resolved.is_active is False
