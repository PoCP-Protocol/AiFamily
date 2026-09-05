from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.service.fgcn.blueprint_proposal import (
    BlueprintProposalBase,
    BlueprintProposalError,
    FGCNBlueprintProposalHandler,
    SqlAlchemyServiceBlueprintProposalStore,
)
from backend.intelligence.human_gate.contracts import ActorType, GateScope, NamedActionRequest
from backend.platform.audit import AuditBase, AuditRecorder, read_all_events

NOW = datetime(2026, 8, 30, 10, tzinfo=UTC)


def _request(*, recommendation_status: str = "DRAFT") -> NamedActionRequest:
    return NamedActionRequest(
        request_id="request-blueprint-001",
        action_name="PROPOSE_SERVICE_BLUEPRINT",
        action_arguments={
            "blueprint_ref": "communication-21day-service-collab",
            "primary_contradiction_ref": "contradiction:communication",
            "action_refs": ["action:guided-practice"],
            "evidence_refs": ["evidence:assessment-001"],
            "recommendation_status": recommendation_status,
        },
        task_id="human-task-blueprint-001",
        proposal_id="proposal-blueprint-001",
        decision_id="decision-blueprint-001",
        actor_id="guardian-blueprint-001",
        actor_type=ActorType.GUARDIAN,
        scope=GateScope(
            tenant_id="tenant-blueprint",
            family_id="family-blueprint",
            subject_ids=("child-blueprint",),
            purpose="growth_support",
            consent_version="consent.v1",
            correlation_id="corr-blueprint",
        ),
        provenance_ref="intervention:draft-001",
        idempotency_key="idem-blueprint-001",
    )


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(BlueprintProposalBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_accepted_blueprint_proposal_is_durable_and_idempotent(session_factory) -> None:
    request = _request()
    async with session_factory() as session:
        recorder = AuditRecorder()
        handler = FGCNBlueprintProposalHandler(
            SqlAlchemyServiceBlueprintProposalStore(session), recorder=recorder
        )
        first = await handler(request)
        replay = await handler(request)
        assert first == replay
        assert first.result_ref == "service-blueprint-proposal:request-blueprint-001"
        events = await read_all_events(session, tenant_id="tenant-blueprint")
        assert [event.action for event in events] == ["PROPOSE_SERVICE_BLUEPRINT"]

    async with session_factory() as session:
        store = SqlAlchemyServiceBlueprintProposalStore(session)
        saved = await store.get_by_request_id(request.request_id)
        assert saved is not None
        assert saved.blueprint_ref == "communication-21day-service-collab"
        assert saved.accepted_by_actor_id == "guardian-blueprint-001"


@pytest.mark.asyncio
async def test_blueprint_proposal_requires_draft_recommendation(session_factory) -> None:
    async with session_factory() as session:
        handler = FGCNBlueprintProposalHandler(
            SqlAlchemyServiceBlueprintProposalStore(session), recorder=AuditRecorder()
        )
        with pytest.raises(BlueprintProposalError, match="draft_recommendation_required"):
            await handler(_request(recommendation_status="APPROVED"))
