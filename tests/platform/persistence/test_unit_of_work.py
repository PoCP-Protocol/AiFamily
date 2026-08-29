"""UnitOfWork commit/rollback semantics against an in-memory SQLite engine.

Two toy repositories share one UnitOfWork's session. We assert that either
both writes land (explicit commit) or neither does (no commit / an
exception before commit) — the core guarantee a UnitOfWork exists to give.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.platform.persistence.session import get_engine
from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork

metadata = MetaData()

widgets = Table(
    "widgets",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
)

gadgets = Table(
    "gadgets",
    metadata,
    Column("id", String, primary_key=True),
    Column("label", String, nullable=False),
)


@pytest.fixture
async def sessionmaker_for_test() -> async_sessionmaker[AsyncSession]:
    """A fresh in-memory SQLite engine + schema, isolated per test."""
    database_url = f"sqlite+aiosqlite:///:memory:?test_id={uuid.uuid4().hex}"
    # Each unique query string still maps through StaticPool caching by URL,
    # so use the shared cached engine helper to get pool semantics right,
    # then create the schema once against it.
    engine = get_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


class WidgetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, widget_id: str, name: str) -> None:
        await self._session.execute(widgets.insert().values(id=widget_id, name=name))

    async def all_ids(self) -> list[str]:
        result = await self._session.execute(select(widgets.c.id))
        return [row[0] for row in result.all()]


class GadgetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, gadget_id: str, label: str) -> None:
        await self._session.execute(gadgets.insert().values(id=gadget_id, label=label))

    async def all_ids(self) -> list[str]:
        result = await self._session.execute(select(gadgets.c.id))
        return [row[0] for row in result.all()]


async def test_commit_persists_writes_from_both_repositories(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        widget_repo = WidgetRepository(uow.session)
        gadget_repo = GadgetRepository(uow.session)

        await widget_repo.add("w1", "Widget One")
        await gadget_repo.add("g1", "Gadget One")

        await uow.commit()

    async with sessionmaker_for_test() as verify_session:
        widget_repo = WidgetRepository(verify_session)
        gadget_repo = GadgetRepository(verify_session)
        assert await widget_repo.all_ids() == ["w1"]
        assert await gadget_repo.all_ids() == ["g1"]


async def test_no_commit_rolls_back_both_repositories(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        widget_repo = WidgetRepository(uow.session)
        gadget_repo = GadgetRepository(uow.session)

        await widget_repo.add("w2", "Widget Two")
        await gadget_repo.add("g2", "Gadget Two")
        # deliberately no uow.commit() — __aexit__ must roll back

    async with sessionmaker_for_test() as verify_session:
        widget_repo = WidgetRepository(verify_session)
        gadget_repo = GadgetRepository(verify_session)
        assert await widget_repo.all_ids() == []
        assert await gadget_repo.all_ids() == []


async def test_exception_before_commit_rolls_back_both_repositories(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(RuntimeError):
        async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
            widget_repo = WidgetRepository(uow.session)
            gadget_repo = GadgetRepository(uow.session)

            await widget_repo.add("w3", "Widget Three")
            await gadget_repo.add("g3", "Gadget Three")
            raise RuntimeError("simulated failure mid-transaction")

    async with sessionmaker_for_test() as verify_session:
        widget_repo = WidgetRepository(verify_session)
        gadget_repo = GadgetRepository(verify_session)
        assert await widget_repo.all_ids() == []
        assert await gadget_repo.all_ids() == []


async def test_ping_returns_true_against_reachable_database(
    sessionmaker_for_test: async_sessionmaker[AsyncSession],
) -> None:
    async with SqlAlchemyUnitOfWork(sessionmaker_for_test) as uow:
        assert await uow.ping() is True
