from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.invocation_fence import (
    SqlAlchemyModelInvocationFence,
)
from backend.intelligence.experience.release_bundle import FamilyExperienceReleaseBundle
from backend.intelligence.experience.release_bundle_persistence import (
    FamilyExperienceReleaseBundleBase,
    SqlAlchemyFamilyExperienceReleaseBundleStore,
)
from backend.intelligence.experience.release_set import FamilyExperienceReleaseSet
from backend.intelligence.experience.release_set_control import ReleaseSetControlEvent
from backend.intelligence.experience.release_set_deployment import (
    ReleaseSetDeploymentAcknowledgement,
    ReleaseSetDeploymentBase,
    ReleaseSetDeploymentError,
    ReleaseSetDeploymentReceipt,
    SqlAlchemyReleaseSetDeploymentStore,
    SqlAlchemyReleaseSetTransitionCoordinator,
)
from backend.intelligence.experience.release_set_persistence import (
    FamilyExperienceReleaseSetBase,
    SqlAlchemyFamilyExperienceReleaseSetStore,
)
from backend.intelligence.experience.runtime_release_binding import (
    RuntimeReleaseBindingError,
    SqlAlchemyActiveFamilyExperienceReleaseResolver,
)
from backend.intelligence.model_gateway.contracts import ModelReleaseBinding
from backend.intelligence.model_gateway.release_fence import ModelInvocationFenceError
from tests.intelligence.model_gateway.test_fail_closed import make_request

NOW = datetime(2026, 9, 1, 11, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(FamilyExperienceReleaseBundleBase.metadata.create_all)
        await connection.run_sync(FamilyExperienceReleaseSetBase.metadata.create_all)
        await connection.run_sync(ReleaseSetDeploymentBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _bundle(marker: str) -> FamilyExperienceReleaseBundle:
    return FamilyExperienceReleaseBundle(
        bundle_id=marker.upper() * 64,
        candidate_id=f"candidate:{marker}",
        environment="staging",
        use_case="family_assistant_conversation",
        agent_id="parent_advisor",
        provider_id="provider-a",
        model="model-a",
        model_version="2026-09",
        prompt_ref="prompt:family",
        prompt_version="prompt.v1",
        schema_ref="schema:family",
        schema_version="schema.v1",
        safety_policy_version="safety.v1",
        routing_policy_version="routing.v1",
        rate_card_version="rates.v1",
        budget_policy_version="budget.v1",
        knowledge_refs=("knowledge:family",),
        data_class="OPERATIONAL_TEXT",
        report_ref=f"benchmark:{marker}",
        decision_id=marker * 64,
        control_id=marker.upper() * 64,
        approval_signature_ref=(marker + "s") * 32,
        approval_signature_algorithm="external-kms-v1",
        approved_by="operator:release",
        approved_at=NOW,
        asset_digest=marker * 64,
        human_gate_rule="REVIEW_REQUIRED",
    )


def _release_set(marker: str, bundle: FamilyExperienceReleaseBundle):
    return FamilyExperienceReleaseSet(
        release_set_id=marker * 64,
        environment=bundle.environment,
        use_case=bundle.use_case,
        data_class=bundle.data_class,
        provider_ids=(bundle.provider_id,),
        bundle_ids=(bundle.bundle_id,),
        routing_policy_version=bundle.routing_policy_version,
        route_config_digest="1" * 64,
        rate_card_version=bundle.rate_card_version,
        rate_card_digest="2" * 64,
        budget_policy_version=bundle.budget_policy_version,
        budget_policy_digest="3" * 64,
        agent_id=bundle.agent_id,
        prompt_ref=bundle.prompt_ref,
        prompt_version=bundle.prompt_version,
        schema_ref=bundle.schema_ref,
        schema_version=bundle.schema_version,
        safety_policy_version=bundle.safety_policy_version,
        safety_policy_digest="5" * 64,
        knowledge_refs=bundle.knowledge_refs,
        asset_digest=bundle.asset_digest,
        runtime_config_digest=marker * 64,
    )


def _receipt(
    release_set: FamilyExperienceReleaseSet,
    marker: str,
    *,
    operation: str = "APPLY",
    phase: str = "ACTIVE",
    target_release_set_id: str | None = None,
    acknowledged_release_set_id: str | None = None,
) -> ReleaseSetDeploymentReceipt:
    acknowledged = acknowledged_release_set_id or release_set.release_set_id
    return ReleaseSetDeploymentReceipt(
        sequence=0,
        receipt_id=f"receipt:{marker}",
        idempotency_key=f"deploy:{marker}",
        release_set_id=release_set.release_set_id,
        target_release_set_id=target_release_set_id,
        environment=release_set.environment,
        use_case=release_set.use_case,
        data_class=release_set.data_class,
        operation=operation,  # type: ignore[arg-type]
        phase=phase,  # type: ignore[arg-type]
        rollout_percent={"CANARY": 5, "ACTIVE": 100, "ROLLED_BACK": 0}[phase],
        control_id=f"control:{marker}",
        actor_id="operator:release",
        applied_config_digest=(
            release_set.runtime_config_digest
            if acknowledged == release_set.release_set_id
            else acknowledged
        ),
        acknowledged_release_set_id=acknowledged,
        external_ref=f"deployment:{marker}",
        created_at=NOW,
    )


def _control(
    release_set: FamilyExperienceReleaseSet,
    marker: str,
    *,
    expected_effective_sequence: int = 0,
) -> ReleaseSetControlEvent:
    return ReleaseSetControlEvent(
        control_id=f"control:{marker}",
        idempotency_key=f"control-key:{marker}",
        kind="APPLY",
        phase="ACTIVE",
        rollout_percent=100,
        source_release_set_id=release_set.release_set_id,
        target_release_set_id=None,
        environment=release_set.environment,
        use_case=release_set.use_case,
        data_class=release_set.data_class,
        runtime_config_digest=release_set.runtime_config_digest,
        expected_effective_sequence=expected_effective_sequence,
        actor_id="operator:release",
        reason="reviewed transition",
        signature_ref="signature:reviewed",
        signature_algorithm="external-kms-v1",
        created_at=NOW,
    )


async def _persist_manifest(session_factory, release_set, bundle) -> None:
    async with session_factory() as session, session.begin():
        await SqlAlchemyFamilyExperienceReleaseBundleStore(session).append(bundle)
        await SqlAlchemyFamilyExperienceReleaseSetStore(session).append(release_set)


@pytest.mark.asyncio
async def test_canary_never_authorizes_runtime_and_active_does(session_factory) -> None:
    bundle = _bundle("a")
    release_set = _release_set("a", bundle)
    await _persist_manifest(session_factory, release_set, bundle)
    async with session_factory() as session, session.begin():
        await SqlAlchemyReleaseSetDeploymentStore(session).append(
            _receipt(release_set, "canary", phase="CANARY")
        )
    resolver = SqlAlchemyActiveFamilyExperienceReleaseResolver(session_factory)
    with pytest.raises(RuntimeReleaseBindingError, match="NOT_FOUND"):
        await resolver.resolve(
            environment="staging",
            use_case=release_set.use_case,
            data_class=release_set.data_class,
        )
    async with session_factory() as session, session.begin():
        active = await SqlAlchemyReleaseSetDeploymentStore(session).append(
            _receipt(release_set, "active")
        )
    binding = await resolver.resolve(
        environment="staging",
        use_case=release_set.use_case,
        data_class=release_set.data_class,
    )
    assert binding.release_set == release_set
    assert binding.deployment_receipt == active


@pytest.mark.asyncio
async def test_rollback_restores_only_historically_active_target(session_factory) -> None:
    old_bundle = _bundle("a")
    old = _release_set("a", old_bundle)
    current_bundle = replace(
        _bundle("b"),
        bundle_id="B" * 64,
        candidate_id="candidate:b",
    )
    current = _release_set("b", current_bundle)
    await _persist_manifest(session_factory, old, old_bundle)
    await _persist_manifest(session_factory, current, current_bundle)
    async with session_factory() as session, session.begin():
        store = SqlAlchemyReleaseSetDeploymentStore(session)
        await store.append(_receipt(old, "old-active"))
        await store.append(_receipt(current, "current-active"))
        await store.append(
            replace(
                _receipt(
                    current,
                    "rollback",
                    operation="ROLLBACK",
                    phase="ROLLED_BACK",
                    target_release_set_id=old.release_set_id,
                    acknowledged_release_set_id=old.release_set_id,
                ),
                applied_config_digest=old.runtime_config_digest,
            )
        )
    binding = await SqlAlchemyActiveFamilyExperienceReleaseResolver(
        session_factory
    ).resolve(
        environment="staging",
        use_case=old.use_case,
        data_class=old.data_class,
    )
    assert binding.release_set == old
    assert binding.deployment_receipt.operation == "ROLLBACK"


@pytest.mark.asyncio
async def test_runtime_binding_rejects_missing_approved_bundle(session_factory) -> None:
    bundle = _bundle("a")
    release_set = _release_set("a", bundle)
    async with session_factory() as session, session.begin():
        await SqlAlchemyFamilyExperienceReleaseSetStore(session).append(release_set)
        await SqlAlchemyReleaseSetDeploymentStore(session).append(
            _receipt(release_set, "active")
        )
    with pytest.raises(RuntimeReleaseBindingError, match="BUNDLE_NOT_FOUND"):
        await SqlAlchemyActiveFamilyExperienceReleaseResolver(session_factory).resolve(
            environment="staging",
            use_case=release_set.use_case,
            data_class=release_set.data_class,
        )


@pytest.mark.asyncio
async def test_sql_invocation_fence_is_idempotent_and_rejects_stale_binding(
    session_factory,
) -> None:
    bundle = _bundle("a")
    release_set = _release_set("a", bundle)
    await _persist_manifest(session_factory, release_set, bundle)
    async with session_factory() as session, session.begin():
        receipt = await SqlAlchemyReleaseSetDeploymentStore(session).append(
            _receipt(release_set, "active")
        )
    binding = ModelReleaseBinding(
        release_set_id=release_set.release_set_id,
        deployment_receipt_id=receipt.receipt_id,
        deployment_sequence=receipt.sequence,
        runtime_config_digest=release_set.runtime_config_digest,
        control_id=receipt.control_id,
        provider_bundle_ids=((bundle.provider_id, bundle.bundle_id),),
    )
    request = replace(
        make_request(tenant_id="tenant-a", family_id="family-a"),
        use_case=release_set.use_case,
        data_class="OPERATIONAL_TEXT",
        release_binding=binding,
    )
    fence = SqlAlchemyModelInvocationFence(
        session_factory,
        environment="staging",
    )

    first = await fence.claim(request, provider_id=bundle.provider_id, route_sequence=0)
    replay = await fence.claim(request, provider_id=bundle.provider_id, route_sequence=0)
    assert replay == first

    stale_request = replace(
        request,
        release_binding=replace(
            binding,
            deployment_sequence=binding.deployment_sequence + 1,
        ),
    )
    with pytest.raises(ModelInvocationFenceError, match="STALE"):
        await fence.claim(
            stale_request,
            provider_id=bundle.provider_id,
            route_sequence=0,
        )


@pytest.mark.asyncio
async def test_sql_transition_survives_restart_and_commits_projection_atomically(
    session_factory,
) -> None:
    bundle = _bundle("a")
    release_set = _release_set("a", bundle)
    await _persist_manifest(session_factory, release_set, bundle)
    control = _control(release_set, "durable")
    first_coordinator = SqlAlchemyReleaseSetTransitionCoordinator(
        session_factory,
        clock=lambda: NOW,
    )
    claim = await first_coordinator.prepare(
        control,
        idempotency_key="deploy:durable",
    )
    restarted = SqlAlchemyReleaseSetTransitionCoordinator(
        session_factory,
        clock=lambda: NOW,
    )
    assert (
        await restarted.prepare(control, idempotency_key="deploy:durable")
    ).transition_id == claim.transition_id
    acknowledgement = ReleaseSetDeploymentAcknowledgement(
        acknowledged_release_set_id=release_set.release_set_id,
        applied_config_digest=release_set.runtime_config_digest,
        external_ref="deployment:durable",
        transition_id=claim.transition_id,
        control_id=claim.control_id,
        expected_effective_sequence=claim.expected_effective_sequence,
    )
    claim = await restarted.acknowledge(claim, acknowledgement)
    stored = await restarted.commit(
        claim,
        replace(
            _receipt(release_set, "durable"),
            control_id=control.control_id,
            idempotency_key="deploy:durable",
        ),
    )
    async with session_factory() as session:
        projection = await SqlAlchemyReleaseSetDeploymentStore(
            session
        ).get_active_binding(
            environment=release_set.environment,
            use_case=release_set.use_case,
            data_class=release_set.data_class,
        )
    assert projection is not None
    assert projection.deployment_sequence == stored.sequence
    assert projection.release_set_id == release_set.release_set_id

    competing = replace(
        control,
        control_id="control:competing",
        idempotency_key="control-key:competing",
        source_release_set_id=_release_set("b", _bundle("b")).release_set_id,
        runtime_config_digest="b" * 64,
    )
    with pytest.raises(ReleaseSetDeploymentError, match="STALE_CONTROL"):
        await restarted.prepare(
            competing,
            idempotency_key="deploy:competing",
        )
