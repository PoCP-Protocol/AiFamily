from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.model_gateway.budget import (
    BudgetReservationStatus,
    InMemoryModelBudgetStore,
    ModelBudgetPolicy,
    ModelBudgetRuntime,
    ModelRate,
    ModelRateCard,
    build_budget_account,
)
from backend.intelligence.model_gateway.contracts import ModelReleaseBinding
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.model_gateway.release_fence import InMemoryModelInvocationFence
from backend.intelligence.model_gateway.routing import RoutingModelGateway
from tests.intelligence.model_gateway.test_fail_closed import (
    VALID_OUTPUT,
    fake_record,
    make_request,
)

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


class _FailingAttemptSink:
    def begin(self, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("database unavailable")

    def finish(self, attempt_id, outcome):  # type: ignore[no-untyped-def]
        return None


async def _budget(
    store: InMemoryModelBudgetStore,
    *,
    period_limit: int,
) -> ModelBudgetRuntime:
    policy = ModelBudgetPolicy(
        version="gateway-budget.v1",
        rate_card_version="gateway-rate.v1",
        per_request_limit_microusd=500,
        period_limit_microusd=period_limit,
        max_completion_tokens=100,
    )
    await store.provision_account(
        build_budget_account(
            tenant_id="tenant-a",
            environment="test",
            policy=policy,
            now=NOW,
        )
    )
    return ModelBudgetRuntime(
        store=store,
        rate_card=ModelRateCard(
            version="gateway-rate.v1",
            rates=(
                ModelRate("provider-first", "fake-deterministic", 100, 100),
                ModelRate("provider-second", "fake-deterministic", 100, 100),
            ),
            effective_at=NOW - timedelta(days=1),
            expires_at=NOW + timedelta(days=1),
        ),
        policy=policy,
        environment="test",
        clock=lambda: NOW,
    )


async def _gateway(
    first: FakeProvider,
    second: FakeProvider,
    *,
    period_limit: int,
):
    store = InMemoryModelBudgetStore()
    budget = await _budget(store, period_limit=period_limit)
    gateway = ModelGateway(
        {first.provider_id: first, second.provider_id: second},
        environment="test",
        registry=ProviderRegistry(
            (fake_record(first.provider_id), fake_record(second.provider_id))
        ),
        budget_runtime=budget,
    )
    return gateway, store


def _scoped_request():
    return make_request(tenant_id="tenant-a", family_id="family-a")


@pytest.mark.asyncio
async def test_gateway_reserves_before_call_and_settles_provider_usage() -> None:
    first = FakeProvider(
        {"assessment_interpretation": VALID_OUTPUT}, provider_id="provider-first"
    )
    second = FakeProvider(provider_id="provider-second")
    gateway, store = await _gateway(first, second, period_limit=500)

    draft = await gateway.generate_structured(
        _scoped_request(), provider_id="provider-first"
    )

    assert draft.status == "DRAFT"
    reservation = next(iter(store.reservations.values()))
    assert reservation.status is BudgetReservationStatus.SETTLED
    assert reservation.actual_microusd == 0
    assert len(first.invocations) == 1


@pytest.mark.asyncio
async def test_exhausted_budget_blocks_before_provider_invocation() -> None:
    first = FakeProvider(
        {"assessment_interpretation": VALID_OUTPUT}, provider_id="provider-first"
    )
    second = FakeProvider(provider_id="provider-second")
    gateway, store = await _gateway(first, second, period_limit=500)
    account_key = ("tenant-a", "test", NOW.date().isoformat())
    store.accounts[account_key] = replace(
        store.accounts[account_key], spent_microusd=500
    )

    with pytest.raises(ModelGatewayError) as excinfo:
        await gateway.generate_structured(
            _scoped_request(), provider_id="provider-first"
        )

    assert excinfo.value.kind == "BUDGET_REJECTED"
    assert first.invocations == []


@pytest.mark.asyncio
async def test_failed_first_attempt_consumes_hold_and_can_block_fallback() -> None:
    first = FakeProvider(fail_with="PROVIDER_5XX", provider_id="provider-first")
    second = FakeProvider(
        {"assessment_interpretation": VALID_OUTPUT}, provider_id="provider-second"
    )
    gateway, store = await _gateway(first, second, period_limit=500)
    routing = RoutingModelGateway(gateway, (first.provider_id, second.provider_id))

    with pytest.raises(ModelGatewayError) as excinfo:
        await routing.generate_structured(_scoped_request())

    assert excinfo.value.kind == "BUDGET_REJECTED"
    assert len(first.invocations) == 1
    assert second.invocations == []
    reservation = next(iter(store.reservations.values()))
    assert reservation.status is BudgetReservationStatus.CONSUMED_UNCERTAIN
    assert reservation.actual_microusd == 500


@pytest.mark.asyncio
async def test_each_fallback_attempt_has_an_independent_budget_reservation() -> None:
    first = FakeProvider(fail_with="NETWORK_ERROR", provider_id="provider-first")
    second = FakeProvider(
        {"assessment_interpretation": VALID_OUTPUT}, provider_id="provider-second"
    )
    gateway, store = await _gateway(first, second, period_limit=1000)
    release_binding = ModelReleaseBinding(
        release_set_id="release-set-1",
        deployment_receipt_id="receipt-1",
        deployment_sequence=1,
        runtime_config_digest="digest-1",
        control_id="control-1",
        provider_bundle_ids=(
            (first.provider_id, "bundle-first"),
            (second.provider_id, "bundle-second"),
        ),
    )
    gateway = gateway.with_invocation_fence(
        InMemoryModelInvocationFence(release_binding)
    )
    routing = RoutingModelGateway(gateway, (first.provider_id, second.provider_id))
    draft = await routing.generate_structured(
        replace(_scoped_request(), release_binding=release_binding)
    )

    assert draft.provenance.provider_id == second.provider_id
    reservations = tuple(store.reservations.values())
    assert [(item.provider_id, item.route_sequence) for item in reservations] == [
        (first.provider_id, 0),
        (second.provider_id, 1),
    ]
    assert reservations[0].status is BudgetReservationStatus.CONSUMED_UNCERTAIN
    assert reservations[1].status is BudgetReservationStatus.SETTLED
    assert [item.bundle_id for item in reservations] == [
        "bundle-first",
        "bundle-second",
    ]
    assert all(item.release_set_id == "release-set-1" for item in reservations)
    assert all(item.deployment_sequence == 1 for item in reservations)
    assert all(item.control_id == "control-1" for item in reservations)
    assert draft.provenance.bundle_id == "bundle-second"
    assert draft.provenance.deployment_receipt_id == "receipt-1"
    assert draft.provenance.deployment_sequence == 1
    assert draft.provenance.control_id == "control-1"
    assert draft.provenance.fence_claim_id is not None
    attempts = gateway.attempt_sink.all_attempts()  # type: ignore[attr-defined]
    assert all(item.deployment_sequence == 1 for item in attempts)
    assert all(item.runtime_config_digest == "digest-1" for item in attempts)
    assert all(item.control_id == "control-1" for item in attempts)


@pytest.mark.asyncio
async def test_stale_release_fence_blocks_provider_and_releases_budget() -> None:
    first = FakeProvider(
        {"assessment_interpretation": VALID_OUTPUT}, provider_id="provider-first"
    )
    second = FakeProvider(provider_id="provider-second")
    gateway, store = await _gateway(first, second, period_limit=500)
    active = ModelReleaseBinding(
        release_set_id="release-active",
        deployment_receipt_id="receipt-active",
        deployment_sequence=2,
        runtime_config_digest="digest-active",
        control_id="control-active",
        provider_bundle_ids=((first.provider_id, "bundle-active"),),
    )
    stale = replace(
        active,
        release_set_id="release-stale",
        deployment_receipt_id="receipt-stale",
        deployment_sequence=1,
        runtime_config_digest="digest-stale",
        control_id="control-stale",
    )
    gateway = gateway.with_invocation_fence(InMemoryModelInvocationFence(active))

    with pytest.raises(ModelGatewayError) as excinfo:
        await gateway.generate_structured(
            replace(_scoped_request(), release_binding=stale),
            provider_id=first.provider_id,
        )

    assert excinfo.value.kind == "RELEASE_FENCE_REJECTED"
    assert first.invocations == []
    reservation = next(iter(store.reservations.values()))
    assert reservation.status is BudgetReservationStatus.RELEASED
    assert reservation.actual_microusd == 0


@pytest.mark.asyncio
async def test_release_bound_attempt_start_failure_blocks_provider_and_releases_budget() -> None:
    first = FakeProvider(
        {"assessment_interpretation": VALID_OUTPUT}, provider_id="provider-first"
    )
    second = FakeProvider(provider_id="provider-second")
    gateway, store = await _gateway(first, second, period_limit=500)
    binding = ModelReleaseBinding(
        release_set_id="release-active",
        deployment_receipt_id="receipt-active",
        deployment_sequence=2,
        runtime_config_digest="digest-active",
        control_id="control-active",
        provider_bundle_ids=((first.provider_id, "bundle-active"),),
    )
    gateway = gateway.with_invocation_fence(
        InMemoryModelInvocationFence(binding)
    ).with_attempt_sink(_FailingAttemptSink())

    with pytest.raises(ModelGatewayError) as excinfo:
        await gateway.generate_structured(
            replace(_scoped_request(), release_binding=binding),
            provider_id=first.provider_id,
        )

    assert excinfo.value.kind == "ATTEMPT_LEDGER_REJECTED"
    assert first.invocations == []
    reservation = next(iter(store.reservations.values()))
    assert reservation.status is BudgetReservationStatus.RELEASED


@pytest.mark.asyncio
async def test_configured_release_fence_rejects_unbound_request() -> None:
    first = FakeProvider(
        {"assessment_interpretation": VALID_OUTPUT}, provider_id="provider-first"
    )
    second = FakeProvider(provider_id="provider-second")
    gateway, store = await _gateway(first, second, period_limit=500)
    binding = ModelReleaseBinding(
        release_set_id="release-active",
        deployment_receipt_id="receipt-active",
        deployment_sequence=2,
        runtime_config_digest="digest-active",
        control_id="control-active",
        provider_bundle_ids=((first.provider_id, "bundle-active"),),
    )
    gateway = gateway.with_invocation_fence(InMemoryModelInvocationFence(binding))

    with pytest.raises(ModelGatewayError) as excinfo:
        await gateway.generate_structured(
            _scoped_request(),
            provider_id=first.provider_id,
        )

    assert excinfo.value.kind == "RELEASE_FENCE_REJECTED"
    assert first.invocations == []
    reservation = next(iter(store.reservations.values()))
    assert reservation.status is BudgetReservationStatus.RELEASED
