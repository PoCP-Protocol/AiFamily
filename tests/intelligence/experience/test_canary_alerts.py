from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.canary_alerts import (
    CanaryAlertBase,
    CanaryAlertingSupervisor,
    CanaryAlertKind,
    CanaryAlertStatus,
    InMemoryCanaryAlertStore,
    SqlAlchemyCanaryAlertStore,
    build_canary_alert,
)
from backend.intelligence.experience.canary_supervision import (
    CanaryObservation,
    CanaryRollbackBlockedError,
    CanarySloPolicy,
    CanarySupervisionError,
    assess_canary,
)

NOW = datetime(2026, 8, 31, 14, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(CanaryAlertBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _assessment():
    observation = CanaryObservation(
        observation_id="observation-a",
        receipt_id="receipt-a",
        candidate_id="family-experience:candidate-a",
        environment="staging",
        observed_at=NOW,
        window_seconds=300,
        request_count=1,
        error_rate=0.0,
        p95_latency_ms=500,
        safety_violation_count=0,
        minor_safety_violation_count=1,
    )
    return assess_canary(
        observation,
        CanarySloPolicy("canary.v1", 100, 0.02, 1200, 3600),
        evaluated_at=NOW,
    )


def test_canary_alert_distinguishes_executed_and_blocked_outcomes() -> None:
    executed = build_canary_alert(
        _assessment(),
        rollback_receipt_id="rollback-receipt",
        error_code=None,
        opened_at=NOW,
    )
    blocked = build_canary_alert(
        _assessment(),
        rollback_receipt_id=None,
        error_code="PREAUTHORIZED_ROLLBACK_CONTROL_REQUIRED",
        opened_at=NOW,
    )

    assert executed.kind is CanaryAlertKind.ROLLBACK_EXECUTED
    assert blocked.kind is CanaryAlertKind.ROLLBACK_BLOCKED
    assert executed.status is CanaryAlertStatus.OPEN
    assert executed.alert_id != blocked.alert_id


@pytest.mark.asyncio
async def test_alert_acknowledgement_requires_human_and_is_idempotent() -> None:
    store = InMemoryCanaryAlertStore()
    alert = await store.append(
        build_canary_alert(
            _assessment(),
            rollback_receipt_id="rollback-receipt",
            error_code=None,
            opened_at=NOW,
        )
    )
    with pytest.raises(CanarySupervisionError, match="HUMAN_ACTOR_REQUIRED"):
        await store.acknowledge(
            alert.alert_id,
            actor_id="ai:monitor",
            acknowledged_at=NOW + timedelta(minutes=1),
        )

    acknowledged = await store.acknowledge(
        alert.alert_id,
        actor_id="operator-1",
        acknowledged_at=NOW + timedelta(minutes=1),
    )
    replay = await store.acknowledge(
        alert.alert_id,
        actor_id="operator-1",
        acknowledged_at=NOW + timedelta(minutes=2),
    )
    assert acknowledged.status is CanaryAlertStatus.ACKNOWLEDGED
    assert replay == acknowledged
    with pytest.raises(CanarySupervisionError, match="ALREADY_ACKNOWLEDGED"):
        await store.acknowledge(
            alert.alert_id,
            actor_id="operator-2",
            acknowledged_at=NOW + timedelta(minutes=2),
        )


@pytest.mark.asyncio
async def test_sql_alert_round_trips_and_acknowledges_across_sessions(
    session_factory,
) -> None:
    alert = build_canary_alert(
        _assessment(),
        rollback_receipt_id=None,
        error_code="ROLLBACK_CONTROL_EXPIRED",
        opened_at=NOW,
    )
    async with session_factory() as session:
        await SqlAlchemyCanaryAlertStore(session).append(alert)
        await session.commit()
    async with session_factory() as session:
        store = SqlAlchemyCanaryAlertStore(session)
        assert await store.get(alert.alert_id) == alert
        acknowledged = await store.acknowledge(
            alert.alert_id,
            actor_id="operator-1",
            acknowledged_at=NOW + timedelta(minutes=1),
        )
        await session.commit()
    async with session_factory() as session:
        reread = await SqlAlchemyCanaryAlertStore(session).get(alert.alert_id)
    assert reread == acknowledged
    assert reread is not None
    assert reread.acknowledged_by == "operator-1"


@pytest.mark.asyncio
async def test_one_assessment_cannot_be_rebound_to_another_alert_outcome() -> None:
    store = InMemoryCanaryAlertStore()
    await store.append(
        build_canary_alert(
            _assessment(),
            rollback_receipt_id="rollback-receipt",
            error_code=None,
            opened_at=NOW,
        )
    )
    with pytest.raises(CanarySupervisionError, match="CANARY_ALERT_CONFLICT"):
        await store.append(
            build_canary_alert(
                _assessment(),
                rollback_receipt_id=None,
                error_code="ROLLBACK_FAILED",
                opened_at=NOW,
            )
        )


class _Supervisor:
    def __init__(self, *, result=None, error=None) -> None:
        self.result = result
        self.error = error

    async def supervise(self, candidate, canary_receipt, **kwargs):
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_alerting_supervisor_records_blocked_breach_before_reraising() -> None:
    assessment = _assessment()
    store = InMemoryCanaryAlertStore()
    service = CanaryAlertingSupervisor(
        supervisor=_Supervisor(  # type: ignore[arg-type]
            error=CanaryRollbackBlockedError("ROLLBACK_CONTROL_EXPIRED", assessment)
        ),
        alerts=store,
        clock=lambda: NOW,
    )
    with pytest.raises(CanaryRollbackBlockedError, match="CONTROL_EXPIRED"):
        await service.supervise(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            rollback_control_id="control",
            idempotency_key="supervise:blocked",
        )
    alerts = await store.list_open(environment="staging")
    assert len(alerts) == 1
    assert alerts[0].kind is CanaryAlertKind.ROLLBACK_BLOCKED
    assert alerts[0].error_code == "ROLLBACK_CONTROL_EXPIRED"
