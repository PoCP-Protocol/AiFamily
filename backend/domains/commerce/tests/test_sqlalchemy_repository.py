from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.domains.commerce.domain.entities import ProductOffering
from backend.domains.commerce.domain.facts import Entitlement, OrderIntent
from backend.domains.commerce.infrastructure.sqlalchemy_models import Base
from backend.domains.commerce.infrastructure.sqlalchemy_repository import (
    SqlAlchemyCommerceRepository,
)


async def test_sqlalchemy_repository_round_trips_platform_and_tenant_scope():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        repository = SqlAlchemyCommerceRepository(session)
        now = datetime.now(UTC).replace(tzinfo=None)
        await repository.save_product(
            ProductOffering(
                product_id="platform-product",
                product_ref="PLATFORM_PRODUCT",
                title="平台方案",
                source_ref="test",
                effective_from=now,
            )
        )
        await repository.save_product(
            ProductOffering(
                product_id="tenant-product",
                scope_type="TENANT",
                tenant_id="tenant-a",
                product_ref="TENANT_PRODUCT",
                title="租户方案",
                source_ref="test",
                effective_from=now,
            )
        )
        await repository.commit()

        tenant_a = await repository.list_products(tenant_id="tenant-a")
        tenant_b = await repository.list_products(tenant_id="tenant-b")
        assert {product.product_ref for product in tenant_a} == {
            "PLATFORM_PRODUCT",
            "TENANT_PRODUCT",
        }
        assert {product.product_ref for product in tenant_b} == {"PLATFORM_PRODUCT"}

    await engine.dispose()


async def test_sqlalchemy_repository_round_trips_private_intent_and_entitlement():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        repository = SqlAlchemyCommerceRepository(session)
        now = datetime.now(UTC).replace(tzinfo=None)
        intent = OrderIntent(
            order_intent_id="intent-1",
            tenant_id="tenant-a",
            family_id="family-a",
            actor_person_id="parent-a",
            intent_ref="INTENT_PRODUCT_V1",
            product_id="product-1",
            product_ref="PRODUCT_PRODUCT",
            product_version=1,
            source_page_id="UI-14",
            idempotency_key="intent-key-1",
            correlation_id="corr-1",
            created_at=now,
            updated_at=now,
        )
        entitlement = Entitlement(
            entitlement_id="entitlement-1",
            tenant_id="tenant-a",
            family_id="family-a",
            source_order_intent_id="intent-1",
            entitlement_ref="ENTITLEMENT_PRODUCT_V1",
            created_at=now,
            updated_at=now,
        )
        await repository.save_order_intent(intent)
        await repository.save_entitlement(entitlement)
        await repository.commit()

        found = await repository.find_order_intent_by_idempotency(
            tenant_id="tenant-a", family_id="family-a", idempotency_key="intent-key-1"
        )
        assert found is not None
        assert found.product_ref == "PRODUCT_PRODUCT"
        entitlements = await repository.list_entitlements(
            tenant_id="tenant-a", family_id="family-a"
        )
        assert entitlements[0].entitlement_id == "entitlement-1"

    await engine.dispose()
