from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.model_gateway.budget import (
    BudgetReservationStatus,
    InMemoryModelBudgetStore,
    ModelBudgetBase,
    ModelBudgetError,
    ModelBudgetPolicy,
    ModelBudgetRuntime,
    ModelRate,
    ModelRateCard,
    SqlAlchemyModelBudgetStore,
    build_budget_account,
)
from backend.intelligence.model_gateway.contracts import StructuredRequest, TokenUsage

NOW = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def _policy(*, request_limit: int = 500, period_limit: int = 1000) -> ModelBudgetPolicy:
    return ModelBudgetPolicy(
        version="family-budget.v1",
        rate_card_version="rate-card.v1",
        per_request_limit_microusd=request_limit,
        period_limit_microusd=period_limit,
        max_completion_tokens=10,
        prompt_overhead_tokens=10,
    )


def _rate_card(*, effective_at: datetime | None = None) -> ModelRateCard:
    return ModelRateCard(
        version="rate-card.v1",
        rates=(
            ModelRate(
                provider_id="provider-a",
                model="model-a",
                prompt_microusd_per_1k=1000,
                completion_microusd_per_1k=2000,
                media_item_microusd=5,
            ),
        ),
        effective_at=effective_at or NOW - timedelta(days=1),
        expires_at=(effective_at or NOW - timedelta(days=1)) + timedelta(days=30),
    )


def _request(request_id: str = "request-a", *, payload_size: int = 1) -> StructuredRequest:
    return StructuredRequest(
        use_case="family-image-summary",
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        data_class="SYNTHETIC",
        payload={"message": "x" * payload_size},
        output_schema={"type": "object"},
        context_snapshot_ref="context:a",
        request_id=request_id,
        tenant_id="tenant-a",
        family_id="family-a",
    )


async def _runtime(store, *, policy: ModelBudgetPolicy | None = None):
    active_policy = policy or _policy()
    await store.provision_account(
        build_budget_account(
            tenant_id="tenant-a",
            environment="test",
            policy=active_policy,
            now=NOW,
        )
    )
    return ModelBudgetRuntime(
        store=store,
        rate_card=_rate_card(),
        policy=active_policy,
        environment="test",
        clock=lambda: NOW,
    )


@pytest.fixture
async def sql_store() -> SqlAlchemyModelBudgetStore:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ModelBudgetBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield SqlAlchemyModelBudgetStore(factory)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reserve_then_settle_releases_hold_and_records_actual_cost() -> None:
    store = InMemoryModelBudgetStore()
    runtime = await _runtime(store)

    reservation = await runtime.reserve(
        _request(), provider_id="provider-a", model="model-a", route_sequence=0
    )
    settled = await runtime.settle(
        reservation,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        media_item_count=1,
    )
    account = await store.get_account("tenant-a", "test", NOW.date().isoformat())

    assert settled.status is BudgetReservationStatus.SETTLED
    assert settled.actual_microusd == 25
    assert account is not None
    assert account.reserved_microusd == 0
    assert account.spent_microusd == 25
    assert await runtime.settle(
        reservation,
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        media_item_count=1,
    ) == settled


@pytest.mark.asyncio
async def test_missing_usage_or_infrastructure_uncertainty_consumes_full_hold() -> None:
    store = InMemoryModelBudgetStore()
    runtime = await _runtime(store)
    missing_usage = await runtime.reserve(
        _request("request-missing"),
        provider_id="provider-a",
        model="model-a",
        route_sequence=0,
    )
    uncertain = await runtime.settle(
        missing_usage,
        usage=None,
        media_item_count=0,
    )

    assert uncertain.status is BudgetReservationStatus.CONSUMED_UNCERTAIN
    assert uncertain.actual_microusd == 500
    assert uncertain.outcome_code == "MODEL_USAGE_MISSING"


@pytest.mark.asyncio
async def test_concurrent_reservations_cannot_exceed_period_budget() -> None:
    store = InMemoryModelBudgetStore()
    runtime = await _runtime(store, policy=_policy(request_limit=500, period_limit=500))

    results = await asyncio.gather(
        runtime.reserve(
            _request("request-one"),
            provider_id="provider-a",
            model="model-a",
            route_sequence=0,
        ),
        runtime.reserve(
            _request("request-two"),
            provider_id="provider-a",
            model="model-a",
            route_sequence=0,
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    errors = [result for result in results if isinstance(result, ModelBudgetError)]
    assert [error.code for error in errors] == ["MODEL_BUDGET_EXHAUSTED"]


@pytest.mark.asyncio
async def test_client_cannot_understate_large_payload_cost() -> None:
    store = InMemoryModelBudgetStore()
    runtime = await _runtime(store, policy=_policy(request_limit=50, period_limit=100))

    with pytest.raises(ModelBudgetError, match="MODEL_REQUEST_BUDGET_EXCEEDED"):
        await runtime.reserve(
            _request(payload_size=100),
            provider_id="provider-a",
            model="model-a",
            route_sequence=0,
        )
    assert store.reservations == {}


@pytest.mark.asyncio
async def test_inactive_or_missing_rate_fails_before_reservation() -> None:
    store = InMemoryModelBudgetStore()
    policy = _policy()
    await store.provision_account(
        build_budget_account(
            tenant_id="tenant-a", environment="test", policy=policy, now=NOW
        )
    )
    inactive = ModelBudgetRuntime(
        store=store,
        rate_card=_rate_card(effective_at=NOW + timedelta(days=1)),
        policy=policy,
        environment="test",
        clock=lambda: NOW,
    )

    with pytest.raises(ModelBudgetError, match="MODEL_RATE_CARD_INACTIVE"):
        await inactive.reserve(
            _request(), provider_id="provider-a", model="model-a", route_sequence=0
        )


@pytest.mark.asyncio
async def test_sql_store_persists_reservation_and_account_across_sessions(
    sql_store: SqlAlchemyModelBudgetStore,
) -> None:
    runtime = await _runtime(sql_store)
    reservation = await runtime.reserve(
        _request("request-sql"),
        provider_id="provider-a",
        model="model-a",
        route_sequence=0,
    )
    consumed = await runtime.consume_uncertain(
        reservation, outcome_code="PROVIDER_5XX"
    )
    loaded = await sql_store.get(reservation.reservation_id)
    account = await sql_store.get_account(
        "tenant-a", "test", NOW.date().isoformat()
    )

    assert loaded == consumed
    assert loaded is not None
    assert loaded.status is BudgetReservationStatus.CONSUMED_UNCERTAIN
    assert account is not None
    assert account.reserved_microusd == 0
    assert account.spent_microusd == 500
