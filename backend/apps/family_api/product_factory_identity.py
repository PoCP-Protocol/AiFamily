"""Trusted identity bridge for the Product Factory HTTP boundary.

The Product Intelligence domain deliberately knows nothing about bearer
tokens or the platform identity service.  This adapter is owned by the app
composition layer: it validates an opaque bearer through ``IdentitySessionPort``
and delegates tenant binding to an explicitly injected resolver.  No request
body or unverified header can choose the resulting ``ActorContext``.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Request

from backend.domains.product_intelligence.application.context import ActorContext
from backend.platform.identity.session_port import IdentitySessionPort, VerifiedIdentitySession


class ProductFactoryIdentityError(PermissionError):
    """Stable fail-closed error for an unusable Product Factory identity."""


TenantScopeResolver = Callable[[VerifiedIdentitySession, Request], str | Awaitable[str]]
PermissionResolver = Callable[
    [VerifiedIdentitySession, str, Request],
    frozenset[str] | Awaitable[frozenset[str]],
]


def _bearer_token(authorization: str | None) -> str:
    if not isinstance(authorization, str):
        raise ProductFactoryIdentityError("BEARER_REQUIRED")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise ProductFactoryIdentityError("BEARER_REQUIRED")
    if " " in token.strip():
        raise ProductFactoryIdentityError("BEARER_INVALID")
    return token.strip()


@dataclass(frozen=True, slots=True)
class ProductFactoryBearerActorResolver:
    """Resolve a human Product Factory actor from verified identity metadata."""

    session_port: IdentitySessionPort
    tenant_scope_resolver: TenantScopeResolver
    permission_resolver: PermissionResolver | None = None

    def __post_init__(self) -> None:
        if not callable(getattr(self.session_port, "introspect", None)):
            raise TypeError("session_port must implement introspect()")
        if not callable(self.tenant_scope_resolver):
            raise TypeError("tenant_scope_resolver must be callable")
        if self.permission_resolver is not None and not callable(self.permission_resolver):
            raise TypeError("permission_resolver must be callable")

    async def __call__(self, request: Request) -> ActorContext:
        token = _bearer_token(request.headers.get("authorization"))
        try:
            session = await self.session_port.introspect(access_token=token)
        except Exception as exc:  # noqa: BLE001 - identity boundary is fail-closed
            raise ProductFactoryIdentityError("IDENTITY_SESSION_UNAVAILABLE") from exc
        if not isinstance(session, VerifiedIdentitySession):
            raise ProductFactoryIdentityError("IDENTITY_SESSION_UNAVAILABLE")
        if session.expires_at.astimezone(UTC) <= datetime.now(UTC):
            raise ProductFactoryIdentityError("IDENTITY_SESSION_EXPIRED")
        try:
            tenant_scope = self.tenant_scope_resolver(session, request)
            if inspect.isawaitable(tenant_scope):
                tenant_scope = await tenant_scope
        except Exception as exc:  # noqa: BLE001 - tenant binding is fail-closed
            raise ProductFactoryIdentityError("TENANT_SCOPE_UNAVAILABLE") from exc
        if not isinstance(tenant_scope, str) or not tenant_scope.strip():
            raise ProductFactoryIdentityError("TENANT_SCOPE_UNAVAILABLE")
        tenant_scope = tenant_scope.strip()
        permissions = frozenset[str]()
        if self.permission_resolver is not None:
            try:
                resolved = self.permission_resolver(session, tenant_scope, request)
                if inspect.isawaitable(resolved):
                    resolved = await resolved
            except Exception as exc:  # noqa: BLE001 - authorization boundary is fail-closed
                raise ProductFactoryIdentityError("AUTHORIZATION_SCOPE_UNAVAILABLE") from exc
            if not isinstance(resolved, frozenset) or any(
                not isinstance(permission, str) or not permission.strip() for permission in resolved
            ):
                raise ProductFactoryIdentityError("AUTHORIZATION_SCOPE_UNAVAILABLE")
            permissions = frozenset(permission.strip() for permission in resolved)
        return ActorContext(
            actor_id=f"account:{session.account_id}",
            actor_type="HUMAN",
            tenant_scope=tenant_scope,
            permissions=permissions,
            trace_id=f"identity-session:{session.session_id}",
        )


__all__ = [
    "ProductFactoryBearerActorResolver",
    "ProductFactoryIdentityError",
    "PermissionResolver",
    "TenantScopeResolver",
]
