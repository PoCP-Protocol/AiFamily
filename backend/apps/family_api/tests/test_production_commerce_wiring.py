import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.apps.family_api.production_commerce_wiring import provide_commerce_repository
from backend.domains.commerce.infrastructure.sqlalchemy_repository import (
    SqlAlchemyCommerceRepository,
)


@pytest.mark.asyncio
async def test_repository_dependency_is_request_scoped_and_closes_session() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    dependency = provide_commerce_repository(factory)
    repository = await dependency.__anext__()
    assert isinstance(repository, SqlAlchemyCommerceRepository)
    await dependency.aclose()
    await engine.dispose()
