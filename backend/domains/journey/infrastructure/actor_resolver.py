"""Resolve an opaque Bearer token through the trusted account/tenant/family chain."""

from __future__ import annotations

import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ..application.service import JourneyActor
from ..domain.errors import JourneyForbiddenError


class JourneyAuthenticationError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SqlAlchemyJourneyActorResolver:
    def __init__(self, engine: AsyncEngine):
        self._engine = engine

    async def resolve(self, authorization: str | None, family_id: str) -> JourneyActor:
        token = _bearer_token(authorization)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with self._engine.connect() as connection:
            session_result = await connection.execute(
                text(
                    """
                    select session_id,account_ref from identity_sessions
                    where token_hash=:token_hash and revoked_at is null and expires_at>now()
                      and account_ref is not null
                    limit 1
                    """
                ),
                {"token_hash": token_hash},
            )
            session = session_result.first()
            if session is None:
                raise JourneyAuthenticationError("invalid_or_expired_identity_session")

            context_result = await connection.execute(
                text(
                    """
                    select tfb.tenant_id,fm.person_id,fm.membership_id,fm.role
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
                      and fm.role in ('OWNER_GUARDIAN','GUARDIAN')
                    where a.account_id=:account_id and a.status='ACTIVE'
                    order by fm.role,fm.membership_id limit 1
                    """
                ),
                {"account_id": str(session.account_ref), "family_id": family_id},
            )
            context = context_result.first()
            if context is None:
                raise JourneyForbiddenError("trusted_family_context_not_found")
            return JourneyActor(actor_id=str(context.person_id), family_id=family_id)


def _bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise JourneyAuthenticationError("authorization_required")
    token = authorization[7:].strip()
    if not token:
        raise JourneyAuthenticationError("authorization_required")
    return token
