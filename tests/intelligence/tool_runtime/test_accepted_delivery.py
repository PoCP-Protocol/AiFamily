from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.human_gate.contracts import ActorType, GateScope, NamedActionRequest
from backend.intelligence.tool_runtime.accepted_delivery import (
    AcceptedActionDeliveryBase,
    AcceptedActionDeliveryError,
    AcceptedActionDeliveryStatus,
    SqlAlchemyAcceptedActionDeliveryStore,
)
from backend.intelligence.tool_runtime.accepted_dispatch import ActionExecutionReceipt

NOW = datetime(2026, 8, 30, 10, tzinfo=UTC)


def _request(*, request_id: str = "request-delivery-001") -> NamedActionRequest:
    return NamedActionRequest(
        request_id=request_id,
        action_name="CONFIRM_SERVICE_TASK_ASSIGNMENT",
        action_arguments={"service_task_id": "task-001"},
        task_id="human-task-001",
        proposal_id="proposal-001",
        decision_id="decision-001",
        actor_id="guardian-001",
        actor_type=ActorType.GUARDIAN,
        scope=GateScope(
            tenant_id="tenant-delivery",
            family_id="family-delivery",
            subject_ids=("child-delivery",),
            purpose="service_collaboration",
            consent_version="consent.v1",
            correlation_id="corr-delivery",
        ),
        provenance_ref="human-gate:decision-001",
        idempotency_key="idem-delivery-001",
    )


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(AcceptedActionDeliveryBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_attempts_and_success_survive_session_restart(session_factory) -> None:
    request = _request()
    async with session_factory() as session:
        store = SqlAlchemyAcceptedActionDeliveryStore(session)
        first = await store.begin_attempt(request, now=NOW)
        second = await store.begin_attempt(request, now=NOW + timedelta(minutes=1))
        assert first.attempts == 1
        assert second.attempts == 2
        await store.mark_succeeded(
            request,
            ActionExecutionReceipt(
                request_id=request.request_id,
                action_name=request.action_name,
                result_ref="assignment-001",
            ),
            now=NOW + timedelta(minutes=1),
        )
        await store.commit()

    async with session_factory() as session:
        store = SqlAlchemyAcceptedActionDeliveryStore(session)
        replay = await store.get(request.request_id)
        assert replay is not None
        assert replay.status is AcceptedActionDeliveryStatus.SUCCEEDED
        assert replay.attempts == 2
        assert replay.result_ref == "assignment-001"


@pytest.mark.asyncio
async def test_dead_letter_is_terminal_and_replay_mismatch_fails(session_factory) -> None:
    request = _request()
    async with session_factory() as session:
        store = SqlAlchemyAcceptedActionDeliveryStore(session)
        await store.begin_attempt(request, now=NOW)
        dead = await store.mark_dead_lettered(request, error="ACTION_HANDLER_NOT_REGISTERED")
        await store.commit()
        assert dead.status is AcceptedActionDeliveryStatus.DEAD_LETTERED
        assert dead.attempts == 1
        letters = await store.list_dead_letters()
        assert [item.request_id for item in letters] == [request.request_id]
        with pytest.raises(ValueError, match="DELIVERY_LIMIT_INVALID"):
            await store.list_dead_letters(limit=-1)
        with pytest.raises(AcceptedActionDeliveryError, match="ALREADY_DEAD_LETTERED"):
            await store.mark_succeeded(
                request,
                ActionExecutionReceipt(
                    request_id=request.request_id,
                    action_name=request.action_name,
                    result_ref="assignment-001",
                ),
            )
