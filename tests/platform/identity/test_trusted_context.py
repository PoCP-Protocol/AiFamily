"""Trusted Account -> Tenant -> Family context resolution tests."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from backend.platform.identity.context import ActorType, TenantContext, TenantStatus
from backend.platform.identity.trusted_context import (
    InMemoryTrustedTenantScopeStore,
    SqlAlchemyTrustedTenantScopeStore,
    TenantBindingStatus,
    TenantMembershipStatus,
    TenantRole,
    TenantScopeError,
    TrustedTenantScope,
    TrustedTenantScopeResolver,
)


def _scope(
    *,
    tenant_status: TenantStatus = TenantStatus.ACTIVE,
    membership_status: TenantMembershipStatus = TenantMembershipStatus.ACTIVE,
    binding_status: TenantBindingStatus = TenantBindingStatus.ACTIVE,
    account_id: str = "account-1",
    family_id: str = "family-1",
) -> TrustedTenantScope:
    return TrustedTenantScope(
        account_id=account_id,
        tenant=TenantContext(tenant_id="tenant-1", status=tenant_status),
        family_id=family_id,
        region_id="CN",
        role=TenantRole.TENANT_VIEWER,
        membership_status=membership_status,
        binding_status=binding_status,
    )


@pytest.mark.parametrize(
    ("tenant_status", "membership_status", "binding_status"),
    [
        (TenantStatus.SUSPENDED, TenantMembershipStatus.ACTIVE, TenantBindingStatus.ACTIVE),
        (TenantStatus.ACTIVE, TenantMembershipStatus.SUSPENDED, TenantBindingStatus.ACTIVE),
        (TenantStatus.ACTIVE, TenantMembershipStatus.ACTIVE, TenantBindingStatus.MIGRATING),
        (TenantStatus.ACTIVE, TenantMembershipStatus.ACTIVE, TenantBindingStatus.REVOKED),
    ],
)
async def test_resolver_rejects_any_inactive_link(
    tenant_status: TenantStatus,
    membership_status: TenantMembershipStatus,
    binding_status: TenantBindingStatus,
) -> None:
    resolver = TrustedTenantScopeResolver(
        InMemoryTrustedTenantScopeStore(
            (
                _scope(
                    tenant_status=tenant_status,
                    membership_status=membership_status,
                    binding_status=binding_status,
                ),
            )
        )
    )

    with pytest.raises(TenantScopeError, match="TENANT_SCOPE_UNAVAILABLE"):
        await resolver.resolve(account_id="account-1", family_id="family-1")


async def test_resolver_returns_active_scope_and_actor_uses_server_tenant() -> None:
    scope = _scope()
    resolver = TrustedTenantScopeResolver(InMemoryTrustedTenantScopeStore((scope,)))

    resolved = await resolver.resolve(account_id="account-1", family_id="family-1")
    actor = resolved.actor_context(
        actor_id="person-1", actor_type=ActorType.HUMAN, correlation_id="corr-1"
    )

    assert resolved is scope
    assert resolved.tenant_id == "tenant-1"
    assert actor.tenant_id == resolved.tenant_id
    assert actor.actor_id == "person-1"


@pytest.mark.parametrize(
    ("account_id", "family_id"),
    [("unknown-account", "family-1"), ("account-1", "unknown-family")],
)
async def test_unknown_account_or_family_has_the_same_fail_closed_error(
    account_id: str, family_id: str
) -> None:
    resolver = TrustedTenantScopeResolver(InMemoryTrustedTenantScopeStore())

    with pytest.raises(TenantScopeError, match="TENANT_SCOPE_UNAVAILABLE") as error:
        await resolver.resolve(account_id=account_id, family_id=family_id)

    assert str(error.value) == "TENANT_SCOPE_UNAVAILABLE"


def test_in_memory_store_rejects_ambiguous_scope_registration() -> None:
    with pytest.raises(ValueError, match="duplicate trusted tenant scope"):
        InMemoryTrustedTenantScopeStore((_scope(), _scope()))


class _MappingResult:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> _MappingResult:
        return self

    def all(self) -> list[Mapping[str, object]]:
        return self._rows


class _Session:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def execute(self, statement: object, params: dict[str, str]) -> _MappingResult:
        self.calls.append((str(statement), params))
        return _MappingResult(self.rows)


def _sql_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "account_id": "account-1",
        "tenant_id": "tenant-1",
        "tenant_status": "ACTIVE",
        "region_id": "CN",
        "tenant_role": "TENANT_VIEWER",
        "membership_status": "ACTIVE",
        "family_id": "family-1",
        "binding_status": "ACTIVE",
    }
    row.update(overrides)
    return row


async def test_sql_store_maps_one_complete_trusted_chain() -> None:
    session = _Session([_sql_row()])
    store = SqlAlchemyTrustedTenantScopeStore(session)  # type: ignore[arg-type]

    resolved = await store.resolve(account_id="account-1", family_id="family-1")

    assert resolved is not None
    assert resolved.account_id == "account-1"
    assert resolved.tenant_id == "tenant-1"
    assert resolved.family_id == "family-1"
    assert resolved.region_id == "CN"
    assert resolved.role is TenantRole.TENANT_VIEWER
    assert session.calls[0][1] == {"account_id": "account-1", "family_id": "family-1"}
    query = session.calls[0][0]
    assert "t.status = 'ACTIVE'" in query
    assert "tm.status = 'ACTIVE'" in query
    assert "tfb.status = 'ACTIVE'" in query


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_sql_row(), _sql_row(tenant_id="tenant-2")],
        [_sql_row(tenant_role="UNKNOWN_ROLE")],
        [_sql_row(region_id=None)],
    ],
)
async def test_sql_store_rejects_missing_ambiguous_or_invalid_chain(
    rows: list[Mapping[str, object]],
) -> None:
    store = SqlAlchemyTrustedTenantScopeStore(_Session(rows))  # type: ignore[arg-type]

    assert await store.resolve(account_id="account-1", family_id="family-1") is None


async def test_sql_store_maps_database_enum_values_case_insensitively() -> None:
    store = SqlAlchemyTrustedTenantScopeStore(
        _Session(
            [
                _sql_row(
                    tenant_status="active",
                    tenant_role="tenant_admin",
                    membership_status="active",
                    binding_status="active",
                )
            ]
        )
    )  # type: ignore[arg-type]

    resolved = await store.resolve(account_id="account-1", family_id="family-1")

    assert resolved is not None
    assert resolved.tenant.status is TenantStatus.ACTIVE
    assert resolved.role is TenantRole.TENANT_ADMIN


def test_scope_requires_non_empty_identity_fields() -> None:
    with pytest.raises(ValueError):
        _scope(account_id="")
