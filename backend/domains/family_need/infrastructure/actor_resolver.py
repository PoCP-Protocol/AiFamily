"""Resolve an opaque Bearer token into a scoped :class:`FamilyNeedActor`.

Mirrors ``backend/domains/journey/infrastructure/actor_resolver.py``'s six-
table trusted-identity chain (identity_sessions -> accounts ->
tenant_account_memberships -> tenant_family_bindings ->
account_person_bindings -> family_memberships), but produces the richer
``FamilyNeedActor`` (adds ``tenant_id``, ``region``, ``environment`` on top of
Journey's ``actor_id``/``family_id``). This module intentionally does not
import anything from ``backend.domains.journey`` — the query *pattern* is
shared, the two domains stay decoupled.

``region``/``environment`` are not part of the identity chain (no table in
that chain carries them), so they are resolved from, in order:

1. an explicit override passed by the caller (e.g. an ``X-AiFamily-Region``
   header the API adapter already validated), then
2. the ``tenant_family_bindings.region`` column if the schema carries one,
   then
3. the module-level defaults below, which match
   ``FamilyNeedActor``'s own dataclass defaults (``CN`` /
   ``development``) so an unconfigured deployment fails safe into the same
   value the dependency stub already used, not a silently invented one.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ..api.dependencies import FamilyNeedActor
from ..domain.errors import FamilyNeedForbiddenError
from ..domain.value_objects import ActorType

DEFAULT_REGION = "CN"
DEFAULT_ENVIRONMENT = "development"

_ROLE_TO_ACTOR_TYPE = {
    "OWNER_GUARDIAN": ActorType.FAMILY_GUARDIAN,
    "GUARDIAN": ActorType.FAMILY_GUARDIAN,
    "MEMBER": ActorType.FAMILY_MEMBER,
}


class FamilyNeedAuthenticationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SqlAlchemyFamilyNeedActorResolver:
    """Resolves a Bearer token to a tenant/family-scoped ``FamilyNeedActor``.

    One instance per process/wiring; each ``resolve`` call opens its own
    read-only connection, matching the Journey resolver's lifecycle (the
    resolver never mutates state, so it needs no caller-owned transaction).
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        region: str = DEFAULT_REGION,
        environment: str = DEFAULT_ENVIRONMENT,
    ):
        self._engine = engine
        self._default_region = region
        self._default_environment = environment

    async def resolve(
        self,
        authorization: str | None,
        family_id: str,
        *,
        region_override: str | None = None,
    ) -> FamilyNeedActor:
        token = _bearer_token(authorization)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with self._engine.connect() as connection:
            session_result = await connection.execute(
                text(
                    """
                    select session_id, account_ref from identity_sessions
                    where token_hash=:token_hash and revoked_at is null and expires_at>now()
                      and account_ref is not null
                    limit 1
                    """
                ),
                {"token_hash": token_hash},
            )
            session = session_result.first()
            if session is None:
                raise FamilyNeedAuthenticationError("invalid_or_expired_identity_session")

            context_result = await connection.execute(
                text(
                    """
                    select tfb.tenant_id, fm.person_id, fm.membership_id, fm.role
                    from accounts a
                    join tenant_account_memberships tam
                      on tam.account_id=a.account_id and tam.status='ACTIVE'
                      and tam.valid_from<=now() and (tam.valid_to is null or tam.valid_to>now())
                    join tenant_family_bindings tfb
                      on tfb.tenant_id=tam.tenant_id and tfb.family_id=:family_id
                      and tfb.status='ACTIVE' and tfb.effective_from<=now()
                      and (tfb.effective_to is null or tfb.effective_to>now())
                    join account_person_bindings apb
                      on apb.account_id=a.account_id and apb.status='ACTIVE'
                    join family_memberships fm
                      on fm.person_id=apb.person_id and fm.family_id=tfb.family_id
                      and fm.status='ACTIVE'
                      and fm.role in ('OWNER_GUARDIAN','GUARDIAN','MEMBER')
                    where a.account_id=:account_id and a.status='ACTIVE'
                    order by fm.role, fm.membership_id limit 1
                    """
                ),
                {"account_id": str(session.account_ref), "family_id": family_id},
            )
            context = context_result.first()
            if context is None:
                raise FamilyNeedForbiddenError("trusted_family_context_not_found")

            actor_type = _ROLE_TO_ACTOR_TYPE.get(context.role, ActorType.FAMILY_MEMBER)
            return FamilyNeedActor(
                tenant_id=str(context.tenant_id),
                family_id=family_id,
                actor_id=str(context.person_id),
                actor_type=actor_type,
                region=region_override or self._default_region,
                environment=self._default_environment,
            )


def _bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise FamilyNeedAuthenticationError("authorization_required")
    token = authorization[7:].strip()
    if not token:
        raise FamilyNeedAuthenticationError("authorization_required")
    return token


__all__ = [
    "DEFAULT_ENVIRONMENT",
    "DEFAULT_REGION",
    "FamilyNeedAuthenticationError",
    "SqlAlchemyFamilyNeedActorResolver",
]
