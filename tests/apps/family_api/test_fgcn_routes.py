"""HTTP tests for the FGCN AI draft -> Human Gate -> worker bridge.

The positive path proves that the mounted router can persist an OPEN task,
record a human ACCEPT, and let the worker command create exactly one durable
assignment.  The reverse checks prove that HTTP input cannot become identity or
scope, and that rejected/non-AI/replayed paths do not create business facts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.service.application.context import ActionContext
from backend.domains.service.fgcn.api import dependencies as deps
from backend.domains.service.fgcn.api.routes import register_exception_handlers, router
from backend.domains.service.fgcn.contracts import (
    BlueprintSnapshot,
    GateServiceScope,
    ServiceCase,
    ServiceTask,
    TaskStatus,
)
from backend.domains.service.fgcn.persistence import FGCNBase, SqlAlchemyFGCNRepository
from backend.intelligence.human_gate import (
    ActorType as GateActorType,
)
from backend.intelligence.human_gate import (
    HumanGateBase,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.intelligence.model_gateway.provenance import (
    ModelDraftRegistryBase,
    ModelDraftScope,
    SqlAlchemyModelDraftRegistry,
)
from backend.platform.audit import AuditBase
from backend.platform.identity.context import ActorContext, ActorType
from tests.domains.service.fgcn.admission_test_doubles import (
    AsyncProviderAdmissionStub,
    admitted_snapshot,
)

NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
TENANT = "00000000-0000-4000-8000-000000000101"
FAMILY = "00000000-0000-4000-8000-000000000102"
CHILD = "00000000-0000-4000-8000-000000000103"
CASE = "00000000-0000-4000-8000-000000000104"
TASK = "00000000-0000-4000-8000-000000000105"
INTENT = "00000000-0000-4000-8000-000000000106"
PLAN = "00000000-0000-4000-8000-000000000107"


def _case() -> ServiceCase:
    return ServiceCase(
        case_id=CASE,
        scope=GateServiceScope(
            tenant_id=TENANT,
            family_id=FAMILY,
            subject_person_id=CHILD,
            purpose="service_collaboration",
            consent_version="consent.v1",
            correlation_id="corr-http-fgcn",
        ),
        intent_ref=INTENT,
        plan_ref=PLAN,
        owner_id="steward-http-fgcn",
        blueprint=BlueprintSnapshot(
            blueprint_ref="blueprint-http-fgcn",
            version=1,
            status="PUBLISHED",
            policy_ref="shadow-policy.v1",
            policy_version=1,
            checksum="checksum-http-fgcn",
            task_template_keys=("AI_GUIDANCE_DELIVERY",),
        ),
        opened_at=NOW,
    )


def _task() -> ServiceTask:
    return ServiceTask(
        task_id=TASK,
        case_id=CASE,
        blueprint_ref="blueprint-http-fgcn",
        blueprint_version=1,
        task_key="AI_GUIDANCE_DELIVERY",
        title="Guidance delivery",
        description="Deliver the configured guidance activity.",
        role_key="DELIVERY_RESOURCE",
        acceptance_criteria=("Evidence reference is present",),
        required_capability_keys=("family_guidance",),
        task_weight=Decimal("1"),
        status=TaskStatus.PENDING,
        created_at=NOW,
    )


class _DraftProvenanceResolver:
    async def resolve(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> ModelDraft:
        if provenance_ref != "model-draft:http-fgcn":
            raise deps.DraftProvenanceNotFound(provenance_ref)
        assert (tenant_id, family_id, subject_person_id, purpose, correlation_id) == (
            TENANT,
            FAMILY,
            CHILD,
            "service_collaboration",
            "corr-http-fgcn",
        )
        return _model_draft()


def _model_draft(*, status: str = "DRAFT") -> ModelDraft:
    return ModelDraft(
        output={"candidate": "expert-http-fgcn"},
        provenance=AiProvenance(
            provider_id="fake-deterministic",
            model="fake-deterministic",
            model_version="1.0.0",
            prompt_version="service-matching.v1",
            schema_version="service-matching.v1",
            context_snapshot_ref="context:http-fgcn",
            latency_ms=1,
            data_class="MINOR_PERSONAL_DATA",
            use_case="service_matching_recommendation",
        ),
        status=status,  # type: ignore[arg-type]
    )


class _ValidatedDraftResolver:
    async def resolve(
        self,
        provenance_ref: str,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: str,
        correlation_id: str,
    ) -> ModelDraft:
        return _model_draft(status="VALIDATED")


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(FGCNBase.metadata.create_all)
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
        await connection.run_sync(ModelDraftRegistryBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        repository = SqlAlchemyFGCNRepository(session)
        await repository.save_case(_case())
        await repository.save_task(_task())
        await session.commit()
        yield session


class _Wiring:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.idempotency_key: str | None = None
        self.family_id = FAMILY
        self.actor_type = ActorType.AI
        self.reviewer = deps.HumanReviewerContext(
            actor_id="guardian-http-fgcn",
            actor_type=GateActorType.GUARDIAN,
            tenant_id=TENANT,
        )
        self.provenance_resolver: deps.DraftProvenanceResolver = _DraftProvenanceResolver()
        self.provider_admission = AsyncProviderAdmissionStub(
            admitted_snapshot(
                provider_ref="expert-http-fgcn",
                capability_keys=("family_guidance",),
            )
        )

    def context(self) -> ActionContext:
        return ActionContext(
            tenant_id=TENANT,
            family_id=self.family_id,
            actor_person_id="ai-http-fgcn",
            actor="ai-http-fgcn",
            correlation_id="corr-route-request",
            environment="TEST",
            idempotency_key=self.idempotency_key,
        )

    def actor(self) -> ActorContext:
        return ActorContext(
            actor_id="ai:http-fgcn" if self.actor_type is ActorType.AI else "human:http-fgcn",
            actor_type=self.actor_type,
            tenant_id=TENANT,
            correlation_id="corr-route-request",
        )

    def worker(self) -> ActorContext:
        return ActorContext(
            actor_id="workflow-worker:http-fgcn",
            actor_type=ActorType.SYSTEM,
            tenant_id=TENANT,
            correlation_id="corr-worker-request",
        )


@pytest.fixture
def client(seeded_session: AsyncSession) -> Iterator[tuple[TestClient, _Wiring]]:
    wiring = _Wiring(seeded_session)
    application = FastAPI()
    application.include_router(router)
    register_exception_handlers(application)

    async def get_session() -> AsyncIterator[AsyncSession]:
        yield seeded_session

    async def get_context() -> ActionContext:
        return wiring.context()

    async def get_actor() -> ActorContext:
        return wiring.actor()

    async def get_reviewer() -> deps.HumanReviewerContext:
        return wiring.reviewer

    def get_provenance_resolver() -> _DraftProvenanceResolver:
        return wiring.provenance_resolver

    def get_worker() -> ActorContext:
        return wiring.worker()

    def get_provider_admission() -> AsyncProviderAdmissionStub:
        return wiring.provider_admission

    application.dependency_overrides[deps.get_fgcn_session] = get_session
    application.dependency_overrides[deps.get_action_context] = get_context
    application.dependency_overrides[deps.get_actor_context] = get_actor
    application.dependency_overrides[deps.get_human_reviewer_context] = get_reviewer
    application.dependency_overrides[deps.get_draft_provenance_resolver] = get_provenance_resolver
    application.dependency_overrides[deps.get_workflow_worker_context] = get_worker
    application.dependency_overrides[deps.get_provider_admission] = get_provider_admission
    with TestClient(application) as test_client:
        yield test_client, wiring
    application.dependency_overrides.clear()


def _headers(wiring: _Wiring, key: str) -> dict[str, str]:
    wiring.idempotency_key = key
    return {"idempotency-key": key}


def _proposal_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "proposal_id": "proposal:http-fgcn",
        "draft_id": "draft:http-fgcn",
        "provenance_ref": "model-draft:http-fgcn",
        "provider_id": "expert-http-fgcn",
    }
    body.update(overrides)
    return body


def test_fgcn_http_path_persists_gate_and_creates_one_assignment(
    client: tuple[TestClient, _Wiring],
) -> None:
    test_client, wiring = client
    proposal = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(),
        headers=_headers(wiring, "proposal-http-1"),
    )
    assert proposal.status_code == 201, proposal.text
    task_id = proposal.json()["task_id"]
    assert proposal.json()["status"] == "OPEN"
    assert proposal.json()["proposal"]["scope"] == {
        "tenant_id": TENANT,
        "family_id": FAMILY,
        "subject_ids": [CHILD],
        "purpose": "service_collaboration",
        "consent_version": "consent.v1",
        "correlation_id": "corr-http-fgcn",
    }

    decision = test_client.post(
        f"/families/{FAMILY}/fgcn/human-tasks/{task_id}/decisions",
        json={"outcome": "ACCEPT"},
        headers=_headers(wiring, "decision-http-1"),
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "DECIDED"
    assert decision.json()["action_request"]["action_name"] == ("CONFIRM_SERVICE_TASK_ASSIGNMENT")

    consumed = test_client.post(
        f"/families/{FAMILY}/fgcn/human-tasks/{task_id}/consume",
        headers=_headers(wiring, "consume-http-1"),
    )
    assert consumed.status_code == 200, consumed.text
    replay = test_client.post(
        f"/families/{FAMILY}/fgcn/human-tasks/{task_id}/consume",
        headers=_headers(wiring, "consume-http-replay"),
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == consumed.json()

    reloaded = test_client.get(
        f"/families/{FAMILY}/fgcn/human-tasks/{task_id}",
        headers=_headers(wiring, "read-http-1"),
    )
    assert reloaded.status_code == 200, reloaded.text
    assert reloaded.json()["action_request"]["request_id"].startswith("named-action-request:")


@pytest.mark.asyncio
async def test_fgcn_http_accepts_a_draft_from_the_durable_provenance_registry(
    client: tuple[TestClient, _Wiring],
    seeded_session: AsyncSession,
) -> None:
    test_client, wiring = client
    await SqlAlchemyModelDraftRegistry(seeded_session).save(
        draft_id="draft:persisted-http-fgcn",
        provenance_ref="model-draft:persisted-http-fgcn",
        scope=ModelDraftScope(
            tenant_id=TENANT,
            family_id=FAMILY,
            subject_person_id=CHILD,
            purpose="service_collaboration",
            correlation_id="corr-http-fgcn",
        ),
        draft=_model_draft(),
        created_at=NOW,
    )
    await seeded_session.commit()
    wiring.provenance_resolver = SqlAlchemyModelDraftRegistry(seeded_session)

    proposal = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(
            proposal_id="proposal:persisted-provenance-http",
            draft_id="draft:persisted-http-fgcn",
            provenance_ref="model-draft:persisted-http-fgcn",
        ),
        headers=_headers(wiring, "persisted-provenance-http"),
    )

    assert proposal.status_code == 201, proposal.text
    assert proposal.json()["proposal"]["provenance_ref"] == "model-draft:persisted-http-fgcn"

    mismatched_id = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(
            proposal_id="proposal:persisted-provenance-id-mismatch",
            draft_id="draft:not-the-persisted-draft",
            provenance_ref="model-draft:persisted-http-fgcn",
        ),
        headers=_headers(wiring, "persisted-provenance-id-mismatch"),
    )
    assert mismatched_id.status_code == 422
    assert mismatched_id.json() == {"detail": "fgcn_draft_identity_mismatch"}


def test_fgcn_http_reverse_checks_reject_forged_scope_and_non_ai_proposal(
    client: tuple[TestClient, _Wiring],
) -> None:
    test_client, wiring = client

    wrong_family = test_client.post(
        "/families/another-family/fgcn/tasks/task-http-fgcn/assignment-proposals",
        json=_proposal_body(),
        headers=_headers(wiring, "wrong-family"),
    )
    assert wrong_family.status_code == 403

    proposal = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(proposal_id="proposal:reviewer-scope-http"),
        headers=_headers(wiring, "reviewer-scope-proposal"),
    )
    assert proposal.status_code == 201, proposal.text
    task_id = proposal.json()["task_id"]
    wiring.reviewer = deps.HumanReviewerContext(
        actor_id="professional-not-allowed",
        actor_type=GateActorType.PROFESSIONAL,
        tenant_id=TENANT,
    )
    unauthorized_read = test_client.get(
        f"/families/{FAMILY}/fgcn/human-tasks/{task_id}",
        headers=_headers(wiring, "reviewer-scope-read"),
    )
    assert unauthorized_read.status_code == 403

    unknown_provenance = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(
            proposal_id="proposal:unknown-provenance-http",
            provenance_ref="untrusted-client-string",
        ),
        headers=_headers(wiring, "unknown-provenance"),
    )
    assert unknown_provenance.status_code == 422

    wiring.provenance_resolver = _ValidatedDraftResolver()
    promoted_draft = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(proposal_id="proposal:promoted-draft-http"),
        headers=_headers(wiring, "promoted-draft"),
    )
    assert promoted_draft.status_code == 422

    wiring.actor_type = ActorType.HUMAN
    non_ai = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(),
        headers=_headers(wiring, "non-ai"),
    )
    assert non_ai.status_code == 403

    wiring.actor_type = ActorType.AI
    forged = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(
            actor_id="guardian-forged",
            scope={"tenant_id": "foreign-tenant"},
            action_request={"action_name": "WRITE"},
        ),
        headers=_headers(wiring, "forged-fields"),
    )
    assert forged.status_code == 422, forged.text


def test_fgcn_http_rejected_decision_cannot_be_consumed(
    client: tuple[TestClient, _Wiring],
) -> None:
    test_client, wiring = client
    proposal = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(proposal_id="proposal:rejected-http"),
        headers=_headers(wiring, "rejected-proposal"),
    )
    assert proposal.status_code == 201, proposal.text
    task_id = proposal.json()["task_id"]
    rejected = test_client.post(
        f"/families/{FAMILY}/fgcn/human-tasks/{task_id}/decisions",
        json={"outcome": "REJECT", "reason": "provider unavailable"},
        headers=_headers(wiring, "rejected-decision"),
    )
    assert rejected.status_code == 200, rejected.text
    consumed = test_client.post(
        f"/families/{FAMILY}/fgcn/human-tasks/{task_id}/consume",
        headers=_headers(wiring, "rejected-consume"),
    )
    assert consumed.status_code == 409, consumed.text


def test_fgcn_http_refuses_unadmitted_provider_before_assignment(
    client: tuple[TestClient, _Wiring],
) -> None:
    test_client, wiring = client
    proposal = test_client.post(
        f"/families/{FAMILY}/fgcn/tasks/{TASK}/assignment-proposals",
        json=_proposal_body(proposal_id="proposal:unadmitted-http"),
        headers=_headers(wiring, "unadmitted-proposal"),
    )
    assert proposal.status_code == 201, proposal.text
    task_id = proposal.json()["task_id"]
    decision = test_client.post(
        f"/families/{FAMILY}/fgcn/human-tasks/{task_id}/decisions",
        json={"outcome": "ACCEPT"},
        headers=_headers(wiring, "unadmitted-decision"),
    )
    assert decision.status_code == 200, decision.text

    wiring.provider_admission = AsyncProviderAdmissionStub(None)
    consumed = test_client.post(
        f"/families/{FAMILY}/fgcn/human-tasks/{task_id}/consume",
        headers=_headers(wiring, "unadmitted-consume"),
    )
    assert consumed.status_code == 403, consumed.text
    assert consumed.json() == {"detail": "fgcn_provider_not_admitted"}


def test_family_api_mounts_fgcn_routes_but_production_dependencies_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    from backend.apps.family_api.main import create_app

    application = create_app()
    paths = set(application.openapi()["paths"])
    assert "/families/{family_id}/fgcn/tasks/{service_task_id}/assignment-proposals" in paths
    assert "/families/{family_id}/fgcn/human-tasks/{task_id}/decisions" in paths
    assert deps.get_fgcn_session not in application.dependency_overrides
    assert deps.get_human_reviewer_context not in application.dependency_overrides
    assert deps.get_draft_provenance_resolver not in application.dependency_overrides
    assert deps.get_workflow_worker_context not in application.dependency_overrides
    assert deps.get_provider_admission not in application.dependency_overrides


@pytest.mark.asyncio
async def test_production_without_explicit_postgres_does_not_inherit_fgcn_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from backend.apps.family_api.main import create_app

    create_app()
    with pytest.raises(RuntimeError, match="FGCN session factory not configured"):
        async for _ in deps.get_fgcn_session():
            raise AssertionError("unconfigured production session must not yield")


@pytest.mark.asyncio
async def test_production_sqlite_database_is_rejected_for_fgcn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from backend.apps.family_api.main import create_app

    create_app()
    with pytest.raises(RuntimeError, match="FGCN session factory not configured"):
        async for _ in deps.get_fgcn_session():
            raise AssertionError("production FGCN must not use SQLite")


@pytest.mark.asyncio
async def test_explicit_test_database_is_wired_to_fgcn_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from backend.apps.family_api.main import create_app

    create_app()
    session_stream = deps.get_fgcn_session()
    try:
        session = await anext(session_stream)
        assert session.bind is not None
    finally:
        await session_stream.aclose()
