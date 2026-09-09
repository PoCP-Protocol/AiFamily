"""Real-Postgres persistence tests for `SqlAlchemyIdentityRepository`.

Follows the opt-in gated pattern `tests/support/postgres.py` documents: every
test is skipped unless `AIFAMILY_TEST_DATABASE_URL` is set. These specifically
prove the property `dev_auth.py`'s own docstring named as missing — "Tokens
live in a process-local dict and vanish on restart" — by looking a session up
from a **second, independent** repository/session bound to a fresh connection
against the same schema, rather than reusing the object that created it. That
is the closest a single test process can get to proving "survives a process
restart" without literally killing and restarting a process; sharing no
Python object between the writer and the reader is what makes it a real
proof of persistence rather than of in-memory object identity.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.identity.application.service import IdentityApplicationService
from backend.domains.identity.domain.errors import IdentityUnauthenticatedError
from backend.domains.identity.infrastructure.sqlalchemy_models import Base
from backend.domains.identity.infrastructure.sqlalchemy_repository import (
    SqlAlchemyIdentityRepository,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_session_issued_by_one_connection_is_readable_from_a_fresh_one() -> None:
    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with session_factory() as writer_session:
            writer = IdentityApplicationService(SqlAlchemyIdentityRepository(writer_session))
            issued = await writer.create_account_session(
                external_ref="account-a:family-a", idempotency_key="pg-1"
            )

        # A brand new session/repository/service — no Python object is shared
        # with the writer above — proves this is real persistence, not an
        # in-memory dict the writer happens to still hold a reference to.
        async with session_factory() as reader_session:
            reader = IdentityApplicationService(SqlAlchemyIdentityRepository(reader_session))
            identity = await reader.resolve_actor(bearer_token=f"Bearer {issued.token}")
            assert identity.account_id == "account-a"
            assert identity.family_id == "family-a"


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_expiry_is_enforced_by_a_separate_connection_reading_the_same_row() -> None:
    from backend.domains.identity.domain.entities import IdentitySession

    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        now = datetime.now(UTC)

        # `identity_sessions.session_id` is a real `uuid` primary key (the
        # baseline schema this domain reuses, see
        # `sqlalchemy_models.py`'s module docstring) — the token must be a
        # valid UUID string, same as `IdentityApplicationService` itself
        # always mints via `uuid.uuid4()`.
        expired_token = str(uuid.uuid4())

        async with session_factory() as writer_session:
            repository = SqlAlchemyIdentityRepository(writer_session)
            # Constructed directly through the repository (bypassing the
            # service's validated `create_account_session`, which correctly
            # refuses to mint an already-expired session) so the row's
            # `expires_at` is in the past the instant it lands — this proves
            # expiry is read back from the stored column, not recomputed from
            # a live Python object the writer still holds.
            already_expired = IdentitySession(
                session_id=expired_token,
                account_id="account-b",
                family_id="family-b",
                issued_at=now - timedelta(hours=2),
                expires_at=now - timedelta(hours=1),
            )
            await repository.save_session(already_expired)
            await repository.commit()

        async with session_factory() as reader_session:
            reader = IdentityApplicationService(SqlAlchemyIdentityRepository(reader_session))
            with pytest.raises(IdentityUnauthenticatedError, match="UNKNOWN_OR_EXPIRED_SESSION"):
                await reader.resolve_actor(bearer_token=f"Bearer {expired_token}")


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_revocation_by_one_connection_is_visible_to_a_fresh_one() -> None:
    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with session_factory() as first_session:
            first = IdentityApplicationService(SqlAlchemyIdentityRepository(first_session))
            issued = await first.create_account_session(
                external_ref="account-c:family-c", idempotency_key="pg-3"
            )
            revoked = await first.revoke_session(
                bearer_token=f"Bearer {issued.token}", idempotency_key="pg-revoke-3"
            )
            assert revoked is True

        async with session_factory() as second_session:
            second = IdentityApplicationService(SqlAlchemyIdentityRepository(second_session))
            with pytest.raises(IdentityUnauthenticatedError, match="UNKNOWN_OR_EXPIRED_SESSION"):
                await second.resolve_actor(bearer_token=f"Bearer {issued.token}")


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_repository_round_trips_account_and_session_rows_directly() -> None:
    """Below the application service: proves the ORM mapping itself agrees
    with the migration's schema (column names/types), same purpose
    `test_save_and_get_signal_round_trips_through_real_postgres` serves for
    `family_need`."""

    from backend.domains.identity.domain.entities import Account, IdentitySession

    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        token = str(uuid.uuid4())
        async with session_factory() as session:
            repository = SqlAlchemyIdentityRepository(session)
            now = datetime.now(UTC)
            account = Account(account_id="acct-1", external_ref="acct-1:fam-1", created_at=now)
            await repository.save_account(account)
            session_row = IdentitySession(
                session_id=token,
                account_id="acct-1",
                family_id="fam-1",
                issued_at=now,
                expires_at=now + timedelta(hours=1),
            )
            await repository.save_session(session_row)
            await repository.commit()

            loaded_account = await repository.find_account_by_external_ref("acct-1:fam-1")
            assert loaded_account == account

            loaded_session = await repository.find_session(token)
            assert loaded_session == session_row
