"""Resolve a verified account and family into one trusted tenant scope.

``ActorContext.tenant_id`` is not an authentication mechanism.  This module
closes the next boundary: after an authentication adapter has verified an
account, it proves that the account is active in a tenant and that the tenant
currently owns the requested family. A client-supplied tenant id is never an
input to this lookup.

The SQL adapter mirrors the baseline's trusted chain::

    Account -> TenantAccountMembership -> TenantFamilyBinding
             -> AccountPersonBinding -> FamilyMembership -> Family

An absent, inactive, expired, or ambiguous chain is indistinguishable to the
caller and resolves to ``None``. The resolver turns that into one stable
``TENANT_SCOPE_UNAVAILABLE`` error so the API cannot leak tenant existence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.platform.identity.context import (
    ActorContext,
    ActorType,
    TenantContext,
    TenantStatus,
)


class TenantMembershipStatus(StrEnum):
    """Account membership lifecycle in a tenant."""

    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class TenantBindingStatus(StrEnum):
    """Tenant-to-family binding lifecycle."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    MIGRATING = "MIGRATING"
    REVOKED = "REVOKED"


class TenantRole(StrEnum):
    """Roles granted inside a tenant, independent from family roles."""

    TENANT_OWNER = "TENANT_OWNER"
    TENANT_ADMIN = "TENANT_ADMIN"
    TENANT_OPERATOR = "TENANT_OPERATOR"
    TENANT_VIEWER = "TENANT_VIEWER"


class TenantScopeError(PermissionError):
    """Stable fail-closed error for an unavailable trusted scope."""


@dataclass(frozen=True, slots=True)
class TrustedTenantScope:
    """The server-resolved scope for one account acting on one family."""

    account_id: str
    tenant: TenantContext
    family_id: str
    region_id: str
    role: TenantRole
    membership_status: TenantMembershipStatus
    binding_status: TenantBindingStatus

    def __post_init__(self) -> None:
        for field_name in ("account_id", "family_id", "region_id"):
            if not getattr(self, field_name):
                raise ValueError(f"TrustedTenantScope.{field_name} must not be empty")

    @property
    def tenant_id(self) -> str:
        return self.tenant.tenant_id

    @property
    def is_active(self) -> bool:
        """Whether every link in the trusted chain is currently usable."""

        return (
            self.tenant.is_active
            and self.membership_status is TenantMembershipStatus.ACTIVE
            and self.binding_status is TenantBindingStatus.ACTIVE
        )

    def actor_context(
        self,
        *,
        actor_id: str,
        actor_type: ActorType,
        correlation_id: str,
    ) -> ActorContext:
        """Create an actor bound to this server-resolved tenant."""

        return ActorContext(
            actor_id=actor_id,
            actor_type=actor_type,
            tenant_id=self.tenant_id,
            correlation_id=correlation_id,
        )


class TrustedTenantScopeStore(ABC):
    """Port for resolving an account/family pair without client scope input."""

    @abstractmethod
    async def resolve(self, *, account_id: str, family_id: str) -> TrustedTenantScope | None:
        """Return one scope, or ``None`` for any unavailable/ambiguous chain."""
        ...


class InMemoryTrustedTenantScopeStore(TrustedTenantScopeStore):
    """Explicit test/dev store; it has no default tenant or family behavior."""

    def __init__(self, scopes: tuple[TrustedTenantScope, ...] = ()) -> None:
        self._scopes: dict[tuple[str, str], TrustedTenantScope] = {}
        for scope in scopes:
            self.register(scope)

    def register(self, scope: TrustedTenantScope) -> None:
        key = (scope.account_id, scope.family_id)
        if key in self._scopes:
            raise ValueError("duplicate trusted tenant scope")
        self._scopes[key] = scope

    async def resolve(self, *, account_id: str, family_id: str) -> TrustedTenantScope | None:
        return self._scopes.get((account_id, family_id))


class SqlAlchemyTrustedTenantScopeStore(TrustedTenantScopeStore):
    """Resolve the trusted chain from the canonical PostgreSQL baseline tables."""

    _RESOLVE_SQL = text(
        """
        SELECT
            a.account_id AS account_id,
            t.tenant_id AS tenant_id,
            t.status AS tenant_status,
            t.region_ref AS region_id,
            tm.role AS tenant_role,
            tm.status AS membership_status,
            tfb.family_id AS family_id,
            tfb.status AS binding_status
        FROM accounts AS a
        JOIN tenant_account_memberships AS tm
          ON tm.account_id = a.account_id
        JOIN tenants AS t
          ON t.tenant_id = tm.tenant_id
        JOIN tenant_family_bindings AS tfb
          ON tfb.tenant_id = t.tenant_id
         AND tfb.family_id = :family_id
        JOIN account_person_bindings AS apb
          ON apb.account_id = a.account_id
         AND apb.status = 'ACTIVE'
        JOIN family_memberships AS fm
          ON fm.family_id = tfb.family_id
         AND fm.person_id = apb.person_id
         AND fm.status = 'ACTIVE'
        WHERE a.account_id = :account_id
          AND a.status = 'ACTIVE'
          AND t.status = 'ACTIVE'
          AND tm.status = 'ACTIVE'
          AND tm.valid_from <= CURRENT_TIMESTAMP
          AND (tm.valid_to IS NULL OR tm.valid_to > CURRENT_TIMESTAMP)
          AND tfb.status = 'ACTIVE'
          AND tfb.effective_from <= CURRENT_TIMESTAMP
          AND (tfb.effective_to IS NULL OR tfb.effective_to > CURRENT_TIMESTAMP)
        """
    )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, *, account_id: str, family_id: str) -> TrustedTenantScope | None:
        result = await self._session.execute(
            self._RESOLVE_SQL,
            {"account_id": account_id, "family_id": family_id},
        )
        rows = result.mappings().all()
        if len(rows) != 1:
            return None
        try:
            return _scope_from_row(rows[0])
        except (KeyError, TypeError, ValueError):
            return None


class TrustedTenantScopeResolver:
    """Turn store misses and inactive links into one non-leaky API error."""

    def __init__(self, store: TrustedTenantScopeStore) -> None:
        self._store = store

    async def resolve(self, *, account_id: str, family_id: str) -> TrustedTenantScope:
        scope = await self._store.resolve(account_id=account_id, family_id=family_id)
        if scope is None or not scope.is_active:
            raise TenantScopeError("TENANT_SCOPE_UNAVAILABLE")
        return scope


def _scope_from_row(row: Mapping[str, object]) -> TrustedTenantScope:
    return TrustedTenantScope(
        account_id=_row_text(row, "account_id"),
        tenant=TenantContext(
            tenant_id=_row_text(row, "tenant_id"),
            status=TenantStatus(_row_text(row, "tenant_status").lower()),
        ),
        family_id=_row_text(row, "family_id"),
        region_id=_row_text(row, "region_id"),
        role=TenantRole(_row_text(row, "tenant_role").upper()),
        membership_status=TenantMembershipStatus(_row_text(row, "membership_status").upper()),
        binding_status=TenantBindingStatus(_row_text(row, "binding_status").upper()),
    )


def _row_text(row: Mapping[str, object], field_name: str) -> str:
    value = row[field_name]
    if value is None:
        raise ValueError(f"trusted tenant scope field {field_name} must not be null")
    value_as_text = str(value)
    if not value_as_text:
        raise ValueError(f"trusted tenant scope field {field_name} must not be empty")
    return value_as_text


__all__ = [
    "InMemoryTrustedTenantScopeStore",
    "SqlAlchemyTrustedTenantScopeStore",
    "TenantBindingStatus",
    "TenantMembershipStatus",
    "TenantRole",
    "TenantScopeError",
    "TrustedTenantScope",
    "TrustedTenantScopeResolver",
    "TrustedTenantScopeStore",
]
