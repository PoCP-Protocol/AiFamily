"""PLT-01 contract for an adult-confirmation atomic mutation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    func,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.platform.audit import AuditBase, AuditEvent, AuditRecorder
from backend.platform.persistence import SqlAlchemyUnitOfWork, execute_atomic_mutation
from backend.platform.persistence.session import get_engine
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

metadata = MetaData()

confirmations = Table(
    "plt01_confirmations",
    metadata,
    Column("confirmation_id", String, primary_key=True),
    Column("tenant_id", String, nullable=False),
    Column("family_id", String, nullable=False),
)
outbox_events = Table(
    "outbox_events",
    metadata,
    Column("outbox_id", String, primary_key=True),
    Column("aggregate_type", String, nullable=False),
    Column("aggregate_id", String, nullable=False),
    Column("event_name", String, nullable=False),
    Column("event_version", Integer, nullable=False),
    Column("event_id", String, nullable=False, unique=True),
    Column("correlation_id", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
idempotency_receipts = Table(
    "idempotency_keys",
    metadata,
    Column("idempotency_key", String, primary_key=True),
    Column("action_name", String, nullable=False),
    Column("request_hash", String, nullable=False),
    Column("response_code", Integer, nullable=True),
    Column("response_body", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    url = f"sqlite+aiosqlite:///:memory:?plt01={uuid.uuid4().hex}"
    engine = get_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(AuditBase.metadata.create_all)
        await connection.run_sync(metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


@dataclass
class ConfirmationStages:
    tenant_id: str = "tenant-a"
    family_id: str = "family-a"
    actor_id: str = "guardian-a"
    idempotency_key: str = "confirm-1"
    request_hash: str = "hash-v1"
    confirmation_id: str = "confirmation-1"
    fail_at: str | None = None

    def __post_init__(self) -> None:
        self.audit = AuditRecorder()

    @property
    def scoped_key(self) -> str:
        return f"{self.tenant_id}:{self.family_id}:{self.idempotency_key}"

    async def load_replay_or_reserve(self, session: AsyncSession) -> dict[str, Any] | None:
        row = (
            await session.execute(
                select(idempotency_receipts).where(
                    idempotency_receipts.c.idempotency_key == self.scoped_key
                )
            )
        ).mappings().first()
        if row is not None:
            if row["request_hash"] != self.request_hash:
                raise ValueError("idempotency_key_payload_mismatch")
            response = row["response_body"]
            if response is None:
                raise RuntimeError("idempotency_reservation_incomplete")
            return dict(response)
        await session.execute(
            idempotency_receipts.insert().values(
                idempotency_key=self.scoped_key,
                action_name="GuardianDecision.Confirm",
                request_hash=self.request_hash,
                response_code=None,
                response_body=None,
                created_at=datetime.now(UTC),
                expires_at=None,
            )
        )
        return None

    async def apply_business_change(self, session: AsyncSession) -> dict[str, Any]:
        result = {
            "confirmation_id": self.confirmation_id,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
        }
        await session.execute(confirmations.insert().values(**result))
        self.audit.record(
            AuditEvent(
                actor_id=self.actor_id,
                tenant_id=self.tenant_id,
                action="guardian.confirm",
                resource_type="GuardianDecision",
                resource_id=self.confirmation_id,
                reason="adult confirmed the current family concern",
                correlation_id=self.idempotency_key,
                before=None,
                after={"status": "CONFIRMED", "family_id": self.family_id},
            )
        )
        return result

    async def flush_audit(self, session: AsyncSession) -> None:
        if self.fail_at == "audit":
            raise RuntimeError("injected_audit_failure")
        await self.audit.flush(session)

    async def append_outbox(self, session: AsyncSession, _: dict[str, Any]) -> None:
        if self.fail_at == "outbox":
            raise RuntimeError("injected_outbox_failure")
        await session.execute(
            outbox_events.insert().values(
                outbox_id=str(uuid.uuid4()),
                aggregate_type="GuardianDecision",
                aggregate_id=self.confirmation_id,
                event_id=f"event:{self.confirmation_id}",
                event_name="GuardianDecisionConfirmed",
                event_version=1,
                correlation_id=self.idempotency_key,
                payload={
                    "tenant_id": self.tenant_id,
                    "family_id": self.family_id,
                    "confirmation_id": self.confirmation_id,
                },
                occurred_at=datetime.now(UTC),
                published_at=None,
                retry_count=0,
                created_at=datetime.now(UTC),
            )
        )

    async def persist_receipt(self, session: AsyncSession, result: dict[str, Any]) -> None:
        if self.fail_at == "receipt":
            raise RuntimeError("injected_receipt_failure")
        await session.execute(
            update(idempotency_receipts)
            .where(idempotency_receipts.c.idempotency_key == self.scoped_key)
            .values(response_code=200, response_body=result)
        )


async def _execute(
    session_factory: async_sessionmaker[AsyncSession], stages: ConfirmationStages
):
    return await execute_atomic_mutation(
        unit_of_work=SqlAlchemyUnitOfWork(session_factory),
        load_replay_or_reserve=stages.load_replay_or_reserve,
        apply_business_change=stages.apply_business_change,
        flush_audit=stages.flush_audit,
        append_outbox=stages.append_outbox,
        persist_receipt=stages.persist_receipt,
    )


async def _counts(session_factory: async_sessionmaker[AsyncSession]) -> tuple[int, int, int, int]:
    async with session_factory() as session:
        counts = []
        for table in (
            confirmations,
            AuditBase.metadata.tables["platform_audit_events"],
            outbox_events,
            idempotency_receipts,
        ):
            result = await session.execute(select(func.count()).select_from(table))
            counts.append(int(result.scalar_one()))
        return tuple(counts)  # type: ignore[return-value]


async def test_confirmation_commits_business_audit_outbox_and_receipt_together(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    result = await _execute(session_factory, ConfirmationStages())

    assert result.replayed is False
    assert result.value["confirmation_id"] == "confirmation-1"
    assert await _counts(session_factory) == (1, 1, 1, 1)


@pytest.mark.parametrize("failure_stage", ["audit", "outbox", "receipt"])
async def test_any_platform_stage_failure_rolls_every_write_back(
    session_factory: async_sessionmaker[AsyncSession], failure_stage: str
) -> None:
    with pytest.raises(RuntimeError, match=f"injected_{failure_stage}_failure"):
        await _execute(session_factory, ConfirmationStages(fail_at=failure_stage))

    assert await _counts(session_factory) == (0, 0, 0, 0)


async def test_duplicate_request_replays_receipt_without_duplicate_writes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await _execute(session_factory, ConfirmationStages())
    replay = await _execute(session_factory, ConfirmationStages())

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.value == first.value
    assert await _counts(session_factory) == (1, 1, 1, 1)


async def test_same_key_with_different_payload_is_rejected_without_new_writes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _execute(session_factory, ConfirmationStages())

    with pytest.raises(ValueError, match="idempotency_key_payload_mismatch"):
        await _execute(session_factory, ConfirmationStages(request_hash="hash-v2"))

    assert await _counts(session_factory) == (1, 1, 1, 1)


async def test_failed_attempt_can_retry_after_its_reservation_rolls_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(RuntimeError, match="injected_outbox_failure"):
        await _execute(session_factory, ConfirmationStages(fail_at="outbox"))

    retry = await _execute(session_factory, ConfirmationStages())

    assert retry.replayed is False
    assert await _counts(session_factory) == (1, 1, 1, 1)


async def test_same_raw_key_cannot_replay_another_tenants_receipt(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a = await _execute(session_factory, ConfirmationStages())
    tenant_b = await _execute(
        session_factory,
        ConfirmationStages(
            tenant_id="tenant-b",
            family_id="family-b",
            confirmation_id="confirmation-2",
        ),
    )

    assert tenant_a.replayed is False
    assert tenant_b.replayed is False
    assert tenant_b.value["tenant_id"] == "tenant-b"
    assert await _counts(session_factory) == (2, 2, 2, 2)


async def test_committed_receipt_replays_after_engine_restart(tmp_path) -> None:
    database_path = tmp_path / "plt01-restart.sqlite3"
    first_engine = get_engine(f"sqlite+aiosqlite:///{database_path}?run=first")
    async with first_engine.begin() as connection:
        await connection.run_sync(AuditBase.metadata.create_all)
        await connection.run_sync(metadata.create_all)
    first_factory = async_sessionmaker(bind=first_engine, expire_on_commit=False)
    first = await _execute(first_factory, ConfirmationStages())
    await first_engine.dispose()

    restarted_engine = get_engine(f"sqlite+aiosqlite:///{database_path}?run=restarted")
    restarted_factory = async_sessionmaker(bind=restarted_engine, expire_on_commit=False)
    replay = await _execute(restarted_factory, ConfirmationStages())

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.value == first.value
    assert await _counts(restarted_factory) == (1, 1, 1, 1)
    await restarted_engine.dispose()


async def test_real_postgres_uses_the_same_atomic_contract() -> None:
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)

    postgres_metadata = MetaData()
    AuditBase.metadata.tables["platform_audit_events"].to_metadata(postgres_metadata)
    for table in metadata.sorted_tables:
        table.to_metadata(postgres_metadata)

    async with postgres_schema_engine(postgres_metadata) as engine:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        result = await _execute(factory, ConfirmationStages())

        assert result.replayed is False
        assert await _counts(factory) == (1, 1, 1, 1)

        with pytest.raises(RuntimeError, match="injected_outbox_failure"):
            await _execute(
                factory,
                ConfirmationStages(
                    idempotency_key="confirm-failure",
                    confirmation_id="confirmation-failure",
                    fail_at="outbox",
                ),
            )
        assert await _counts(factory) == (1, 1, 1, 1)
