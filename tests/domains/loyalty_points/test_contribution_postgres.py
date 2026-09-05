"""Opt-in PostgreSQL adapter evidence.

This is intentionally separate from the SQLite contract matrix.  It creates a
disposable schema from the isolated contribution metadata because P2.1 has no
governed Alembic migration in this ownership slice; therefore this test proves
the SQL adapter and restart read-back, not production migration readiness.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.loyalty_points.application.contribution_commands import (
    reverse_released_contribution,
)
from backend.domains.loyalty_points.infrastructure.contribution_sqlalchemy import (
    ContributionBase,
    SqlAlchemyContributionRepository,
)
from tests.domains.loyalty_points.test_contribution_ledger import _ctx, _released
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_postgres_contribution_adapter_restarts_with_same_contract() -> None:
    async with postgres_schema_engine(ContributionBase.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            repo = SqlAlchemyContributionRepository(session)
            released = await _released(repo, prefix="postgres")
            reversed_record = await reverse_released_contribution(
                repo,
                _ctx(key="postgres-refund"),
                released.contribution_id,
                refund_ref="refund:postgres",
            )

        async with session_factory() as restarted_session:
            restarted_repo = SqlAlchemyContributionRepository(restarted_session)
            loaded = await restarted_repo.get_record(
                "tenant-contribution", released.contribution_id
            )
            points = await restarted_repo.list_platform_points(
                "tenant-contribution", "family-contributor"
            )
            audits = await restarted_repo.list_audits(
                "tenant-contribution", released.contribution_id
            )
            outbox = await restarted_repo.list_outbox(
                "tenant-contribution", released.contribution_id
            )

    assert reversed_record.status.value == "REVERSED"
    assert loaded.status.value == "REVERSED"
    assert [(point.points_delta, point.reward_basis) for point in points] == [
        (20, "VERIFIED_ADULT_CONTRIBUTION"),
        (-20, "REFUND_REVERSAL"),
    ]
    assert len(audits) == len(outbox) == 7
