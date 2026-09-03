from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.family_experience_release_set_wiring import (
    build_sql_family_experience_release_set_reconciliation_scheduler,
    build_sql_family_experience_release_set_runtime,
)
from backend.intelligence.evaluation.operator_identity import (
    RELEASE_DEPLOY_SCOPE,
    OperatorIdentity,
)
from backend.intelligence.experience.http_release_set_deployment import (
    HttpReleaseSetDeploymentPort,
)
from backend.intelligence.experience.release_set import FamilyExperienceReleaseSet
from backend.intelligence.experience.release_set_control import (
    ReleaseSetControlBase,
    SqlAlchemyReleaseSetControlStore,
)
from backend.intelligence.experience.release_set_deployment import (
    ReleaseSetDeploymentAcknowledgement,
    ReleaseSetDeploymentBase,
    ReleaseSetTransitionClaim,
    SessionPerCallReleaseSetDeploymentStore,
)
from backend.intelligence.experience.release_set_persistence import (
    FamilyExperienceReleaseSetBase,
    SqlAlchemyFamilyExperienceReleaseSetStore,
)

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


class _Identity:
    async def resolve(self, *, environment: str) -> OperatorIdentity:
        return OperatorIdentity(
            operator_id="operator:release",
            environment=environment,
            authorization_ref="identity:release",
            scopes=(RELEASE_DEPLOY_SCOPE,),
        )


class _Verifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        return bool(payload and actor_id) and signature == "valid-signature"


class _Port:
    def __init__(self) -> None:
        self.calls = 0

    async def apply(
        self,
        release_set,
        *,
        phase,
        rollout_percent,
        idempotency_key,
        transition_id,
        control_id,
        expected_effective_sequence,
    ) -> ReleaseSetDeploymentAcknowledgement:
        self.calls += 1
        return ReleaseSetDeploymentAcknowledgement(
            acknowledged_release_set_id=release_set.release_set_id,
            applied_config_digest=release_set.runtime_config_digest,
            external_ref="deployment:sql-runtime",
            transition_id=transition_id,
            control_id=control_id,
            expected_effective_sequence=expected_effective_sequence,
        )

    async def rollback(
        self,
        source,
        target,
        *,
        idempotency_key,
        transition_id,
        control_id,
        expected_effective_sequence,
    ) -> ReleaseSetDeploymentAcknowledgement:
        raise AssertionError("rollback is not used by this test")

    async def observe(self, transition):  # pragma: no cover - no due transition
        raise AssertionError("observe is not expected without a transition")


def _release_set() -> FamilyExperienceReleaseSet:
    return FamilyExperienceReleaseSet(
        release_set_id="a" * 64,
        environment="test",
        use_case="family_assistant_conversation",
        data_class="SYNTHETIC",
        provider_ids=("provider-a",),
        bundle_ids=("b" * 64,),
        routing_policy_version="routing.v1",
        route_config_digest="1" * 64,
        rate_card_version="rates.v1",
        rate_card_digest="2" * 64,
        budget_policy_version="budget.v1",
        budget_policy_digest="3" * 64,
        agent_id="parent_advisor",
        prompt_ref="prompt:family",
        prompt_version="prompt.v1",
        schema_ref="schema:family",
        schema_version="schema.v1",
        safety_policy_version="safety.v1",
        safety_policy_digest="5" * 64,
        knowledge_refs=("knowledge:family",),
        asset_digest="4" * 64,
        runtime_config_digest="a" * 64,
    )


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(FamilyExperienceReleaseSetBase.metadata.create_all)
        await connection.run_sync(ReleaseSetControlBase.metadata.create_all)
        await connection.run_sync(ReleaseSetDeploymentBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sql_release_set_runtime_uses_pre_external_transition_in_test(
    session_factory,
) -> None:
    release_set = _release_set()
    async with session_factory() as session, session.begin():
        await SqlAlchemyFamilyExperienceReleaseSetStore(session).append(release_set)
        control = await SqlAlchemyReleaseSetControlStore(
            session,
            signature_verifier=_Verifier(),
            clock=lambda: NOW,
        ).authorize(
            release_set,
            kind="APPLY",
            phase="ACTIVE",
            rollout_percent=100,
            target=None,
            expected_effective_sequence=0,
            actor_id="operator:release",
            idempotency_key="control:test:active",
            reason="reviewed test release",
            signature="valid-signature",
            signature_algorithm="external-kms-v1",
        )
    port = _Port()
    runtime = build_sql_family_experience_release_set_runtime(
        environment="test",
        identity_port=_Identity(),
        deployment_port=port,
        session_factory=session_factory,
        clock=lambda: NOW,
    )

    receipt = await runtime.apply(
        release_set,
        control_id=control.control_id,
        phase="ACTIVE",
        rollout_percent=100,
        idempotency_key="deploy:test:active",
    )
    replay = await runtime.apply(
        release_set,
        control_id=control.control_id,
        phase="ACTIVE",
        rollout_percent=100,
        idempotency_key="deploy:test:active",
    )

    assert replay == receipt
    assert port.calls == 1
    active = await SessionPerCallReleaseSetDeploymentStore(
        session_factory
    ).get_active_binding(
        environment="test",
        use_case=release_set.use_case,
        data_class=release_set.data_class,
    )
    assert active is not None
    assert active.release_set_id == release_set.release_set_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "environment",
    ("development", "test", "staging", "production"),
)
async def test_reconciliation_scheduler_has_four_environment_sql_parity(
    session_factory,
    environment: str,
) -> None:
    scheduler = build_sql_family_experience_release_set_reconciliation_scheduler(
        environment=environment,
        worker_id=f"reconciler:{environment}:1",
        deployment_port=_Port(),
        session_factory=session_factory,
        clock=lambda: NOW,
    )

    report = await scheduler.run_once()

    assert report.claimed == 0
    assert scheduler.transitions.durability_mode == "DURABLE"


@pytest.mark.asyncio
async def test_http_release_set_port_sends_and_requires_external_fencing_echo() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        observed.update(body)
        observed["transition_header"] = request.headers["x-ai-transition-id"]
        return httpx.Response(
            200,
            json={
                "acknowledged_release_set_id": body["release_set_id"],
                "applied_config_digest": body["runtime_config_digest"],
                "transition_id": body["transition_id"],
                "control_id": body["control_id"],
                "expected_effective_sequence": body[
                    "expected_effective_sequence"
                ],
                "external_ref": "deployment:http",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        acknowledgement = await HttpReleaseSetDeploymentPort(
            base_url="https://deployment.example",
            token_provider=lambda: "short-lived-token",
            client=client,
        ).apply(
            _release_set(),
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key="deploy:http",
            transition_id="transition:http",
            control_id="control:http",
            expected_effective_sequence=0,
        )

    assert acknowledgement.transition_id == "transition:http"
    assert observed["transition_header"] == "transition:http"
    assert observed["provider_bundle_ids"] == [
        {"provider_id": "provider-a", "bundle_id": "b" * 64}
    ]
    assert observed["may_mutate_business_state"] is False


@pytest.mark.asyncio
async def test_http_release_set_observer_requires_exact_fencing_echo() -> None:
    claim = ReleaseSetTransitionClaim(
        transition_id="transition:observe",
        idempotency_key="deploy:observe",
        control_id="control:observe",
        environment="test",
        use_case="family_assistant_conversation",
        data_class="SYNTHETIC",
        operation="APPLY",
        phase="ACTIVE",
        rollout_percent=100,
        source_release_set_id="a" * 64,
        target_release_set_id=None,
        runtime_config_digest="a" * 64,
        expected_effective_sequence=0,
        status="UNKNOWN",
        acknowledged_release_set_id=None,
        applied_config_digest=None,
        external_ref=None,
        error_code="TimeoutError",
        created_at=NOW,
        updated_at=NOW,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["x-ai-transition-id"] == claim.transition_id
        return httpx.Response(
            200,
            json={
                "state": "APPLIED",
                "transition_id": claim.transition_id,
                "control_id": claim.control_id,
                "expected_effective_sequence": 0,
                "acknowledged_release_set_id": claim.source_release_set_id,
                "applied_config_digest": claim.runtime_config_digest,
                "external_ref": "deployment:observed",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        observation = await HttpReleaseSetDeploymentPort(
            base_url="https://deployment.example",
            token_provider=lambda: "short-lived-token",
            client=client,
        ).observe(claim)

    assert observation.state == "APPLIED"
    assert observation.acknowledgement is not None
    assert observation.acknowledgement.transition_id == claim.transition_id
