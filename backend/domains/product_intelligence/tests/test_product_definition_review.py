from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.intelligence.human_gate import (
    ActionProposal,
    ActorType,
    GateScope,
    HumanGateBase,
    SqlAlchemyHumanGate,
)
from backend.platform.audit import AuditBase, AuditRecorder, read_all_events

from ..api.dependencies import get_actor_context
from ..api.product_definition_review_dependencies import (
    get_product_definition_review_repository,
)
from ..api.product_definition_review_routes import router
from ..application.context import ActorContext
from ..application.product_definition_adoption import (
    ADOPT_PRODUCT_DEFINITION_ACTION,
    ADOPTION_PURPOSE,
)
from ..application.product_definition_review import (
    PRODUCT_DEFINITION_REVIEW_PERMISSION,
    ProductDefinitionReviewForbiddenError,
    get_product_definition_review_task,
)
from ..infrastructure.product_definition_review_repository import (
    FakeProductDefinitionReviewRepository,
    SqlAlchemyProductDefinitionReviewRepository,
)

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
PATH = "/product-intelligence/operator/product-definition-review-tasks"


def _arguments() -> dict[str, object]:
    return {
        "concept_id": "concept:one",
        "zone_assessment_id": "assessment:one",
        "source_decision_draft_ref": "decision-draft:one",
        "product_kind": "MICRO_CAMP",
        "duration_days": 21,
        "primary_contradiction": "理解与行动之间存在断点",
        "demand_ref": "demand:one",
        "market_insight_refs": ["insight:one"],
        "component_ids": ["component:action:v1"],
        "skill_ids": ["skill:compose:v1"],
        "success_metric_ids": ["metric:adoption"],
        "guardrail_ids": ["guardrail:consent"],
        "stop_conditions": ["stop:safety"],
        "pause_policy": "家长可随时暂停",
        "human_gate_policy": "敏感建议需人工复核",
    }


def _proposal(
    *,
    tenant: str = "tenant-a",
    proposal_id: str = "proposal:one",
    purpose: str = ADOPTION_PURPOSE,
    created_at: datetime = NOW,
    expires_at: datetime = datetime(2099, 9, 2, tzinfo=UTC),
) -> ActionProposal:
    return ActionProposal(
        proposal_id=proposal_id,
        draft_id="decision-draft:one",
        draft_status="DRAFT",
        action_name=ADOPT_PRODUCT_DEFINITION_ACTION,
        action_arguments=_arguments(),
        scope=GateScope(
            tenant_id=tenant,
            family_id=None,
            subject_ids=("concept:one", "assessment:one"),
            purpose=purpose,
            consent_version="processing-basis:internal-product-design:v1",
            correlation_id=f"trace:{proposal_id}",
        ),
        allowed_actor_types=(ActorType.OPERATOR,),
        risk_level="MEDIUM",
        provenance_ref="model-draft:product-package:one",
        created_at=created_at,
        expires_at=expires_at,
    )


def _context(
    *, tenant: str = "tenant-a", allowed: bool = True, actor_type: str = "HUMAN"
) -> ActorContext:
    return ActorContext(
        actor_id="operator:product-owner",
        actor_type=actor_type,
        tenant_scope=tenant,
        permissions=(frozenset({PRODUCT_DEFINITION_REVIEW_PERMISSION}) if allowed else frozenset()),
    )


def _client(
    repo: FakeProductDefinitionReviewRepository,
    context: ActorContext,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    async def override_repo():
        yield repo

    async def override_context():
        return context

    app.dependency_overrides[get_product_definition_review_repository] = override_repo
    app.dependency_overrides[get_actor_context] = override_context
    return TestClient(app)


@pytest.mark.asyncio
async def test_application_fails_closed_without_human_review_permission() -> None:
    repo = FakeProductDefinitionReviewRepository()
    for context in (_context(allowed=False), _context(actor_type="AI")):
        with pytest.raises(
            ProductDefinitionReviewForbiddenError,
            match="permission_required",
        ):
            await get_product_definition_review_task(
                repo,
                context,
                task_id="human-task:missing",
            )


def test_operator_lists_and_reads_only_tenant_scoped_open_tasks() -> None:
    own = _proposal()
    other = _proposal(tenant="tenant-b", proposal_id="proposal:other")
    unrelated = _proposal(
        proposal_id="proposal:unrelated",
        purpose="different_product_action",
    )
    current = datetime.now(UTC)
    expired = _proposal(
        proposal_id="proposal:expired",
        created_at=current - timedelta(minutes=2),
        expires_at=current - timedelta(minutes=1),
    )
    repo = FakeProductDefinitionReviewRepository()
    repo.gate.submit(own, task_id="human-task:one")
    repo.gate.submit(other, task_id="human-task:other")
    repo.gate.submit(unrelated, task_id="human-task:unrelated")
    repo.gate.submit(expired, task_id="human-task:expired")
    client = _client(repo, _context())

    listed = client.get(PATH)
    detail = client.get(f"{PATH}/human-task:one")
    hidden = client.get(f"{PATH}/human-task:other")

    assert listed.status_code == 200
    assert [item["task_id"] for item in listed.json()["items"]] == ["human-task:one"]
    assert detail.status_code == 200
    assert detail.headers["etag"] == detail.json()["etag"]
    assert detail.json()["action_arguments"]["zone_assessment_id"] == "assessment:one"
    assert hidden.status_code == 404


def test_accept_uses_server_identity_and_is_idempotent() -> None:
    repo = FakeProductDefinitionReviewRepository()
    repo.gate.submit(_proposal(), task_id="human-task:one")
    client = _client(repo, _context())
    etag = client.get(f"{PATH}/human-task:one").headers["etag"]
    headers = {"Idempotency-Key": "decision-key-one", "If-Match": etag}

    first = client.post(
        f"{PATH}/human-task:one/decision",
        headers=headers,
        json={"outcome": "ACCEPT", "reason": "证据足以进入 PDM 草案"},
    )
    replay = client.post(
        f"{PATH}/human-task:one/decision",
        headers=headers,
        json={"outcome": "ACCEPT", "reason": "证据足以进入 PDM 草案"},
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json() == first.json()
    body = first.json()
    assert body["task"]["etag"] != etag
    assert body["actor_id"] == "operator:product-owner"
    assert body["task"]["decision_outcome"] == "ACCEPT"
    assert body["task"]["request_id"].startswith("named-action-request:")
    assert body["execution_status"] == "PENDING"


def test_decision_rejects_forged_governance_fields_stale_etag_and_changed_replay() -> None:
    repo = FakeProductDefinitionReviewRepository()
    repo.gate.submit(_proposal(), task_id="human-task:one")
    client = _client(repo, _context())
    etag = client.get(f"{PATH}/human-task:one").headers["etag"]
    path = f"{PATH}/human-task:one/decision"

    forged = client.post(
        path,
        headers={"Idempotency-Key": "forged", "If-Match": etag},
        json={
            "outcome": "ACCEPT",
            "reason": "attempt",
            "actor_id": "operator:forged",
            "tenant_id": "tenant-b",
            "proposal_id": "proposal:forged",
            "provenance_ref": "model-draft:forged",
        },
    )
    stale = client.post(
        path,
        headers={"Idempotency-Key": "stale", "If-Match": '"wrong"'},
        json={"outcome": "REJECT", "reason": "证据不足"},
    )
    accepted = client.post(
        path,
        headers={"Idempotency-Key": "first", "If-Match": etag},
        json={"outcome": "REJECT", "reason": "证据不足"},
    )
    changed = client.post(
        path,
        headers={"Idempotency-Key": "changed", "If-Match": etag},
        json={"outcome": "ESCALATE", "reason": "需要法务复核"},
    )

    assert forged.status_code == 422
    assert stale.status_code == 409
    assert accepted.status_code == 200
    assert accepted.json()["task"]["request_id"] is None
    assert accepted.json()["execution_status"] == "NOT_APPLICABLE"
    assert changed.status_code == 409


@pytest.mark.asyncio
async def test_sql_review_decision_and_audit_commit_together() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(HumanGateBase.metadata.create_all)
        await connection.run_sync(AuditBase.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        gate = SqlAlchemyHumanGate(session)
        recorder = AuditRecorder()
        await gate.submit(_proposal(), recorder=recorder, task_id="human-task:sql")
        await gate.flush_audit(recorder)
        await gate.commit()

        repo = SqlAlchemyProductDefinitionReviewRepository(session)
        current = await repo.get(task_id="human-task:sql", tenant_scope="tenant-a")
        decided = await repo.decide(
            task_id=current.task_id,
            tenant_scope="tenant-a",
            actor_id="operator:product-owner",
            outcome="ACCEPT",
            reason="证据足以进入 PDM 草案",
            idempotency_key="sql-decision-key",
            if_match=current.etag,
        )

    async with factory() as session:
        persisted = await SqlAlchemyHumanGate(session).get("human-task:sql")
        events = await read_all_events(session)
    await engine.dispose()

    assert decided.task.request_id == persisted.action_request.request_id
    assert persisted.decision.actor_id == "operator:product-owner"
    assert [event.action for event in events] == [
        "CREATE_HUMAN_TASK",
        "DECIDE_HUMAN_TASK",
    ]
