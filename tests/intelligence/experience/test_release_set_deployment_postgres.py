"""Real-PostgreSQL concurrency proof for ReleaseSet deployment fencing."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.intelligence.experience.release_set import FamilyExperienceReleaseSet
from backend.intelligence.experience.release_set_control import (
    InMemoryReleaseSetControlStore,
)
from backend.intelligence.experience.release_set_deployment import (
    FamilyExperienceReleaseSetDeploymentService,
    ReleaseSetDeploymentAcknowledgement,
    ReleaseSetDeploymentAuthorization,
    ReleaseSetDeploymentBase,
    ReleaseSetDeploymentError,
    SessionPerCallReleaseSetDeploymentStore,
    SqlAlchemyReleaseSetTransitionCoordinator,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

NOW = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


def _release_set(marker: str) -> FamilyExperienceReleaseSet:
    return FamilyExperienceReleaseSet(
        release_set_id=marker * 64,
        environment="staging",
        use_case="family_assistant_conversation",
        data_class="OPERATIONAL_TEXT",
        provider_ids=("provider-a",),
        bundle_ids=(marker.upper() * 64,),
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
        runtime_config_digest=marker * 64,
    )


class _SignatureVerifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        return bool(payload and actor_id) and signature == "valid-signature"


class _BlockingPort:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[str] = []

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
        self.calls.append(release_set.release_set_id)
        self.entered.set()
        await self.release.wait()
        return ReleaseSetDeploymentAcknowledgement(
            acknowledged_release_set_id=release_set.release_set_id,
            applied_config_digest=release_set.runtime_config_digest,
            external_ref=f"deployment:{release_set.release_set_id}",
            transition_id=transition_id,
            control_id=control_id,
            expected_effective_sequence=expected_effective_sequence,
        )

    async def rollback(self, *args, **kwargs):  # pragma: no cover - protocol only
        raise AssertionError("rollback is not part of this concurrency proof")


async def _authorize(controls, release_set, key):  # type: ignore[no-untyped-def]
    event = await controls.authorize(
        release_set,
        kind="APPLY",
        phase="ACTIVE",
        rollout_percent=100,
        target=None,
        expected_effective_sequence=0,
        actor_id="operator:release",
        idempotency_key=key,
        reason="reviewed release transition",
        signature="valid-signature",
        signature_algorithm="external-kms-v1",
    )
    return ReleaseSetDeploymentAuthorization(event.control_id, event.actor_id)


@pytest.mark.asyncio
@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_postgres_scope_lock_allows_only_one_external_deployment() -> None:
    """Two independent coordinators cannot both cross the external-I/O fence."""

    async with postgres_schema_engine(ReleaseSetDeploymentBase.metadata) as engine:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        store = SessionPerCallReleaseSetDeploymentStore(session_factory)
        controls = InMemoryReleaseSetControlStore(
            signature_verifier=_SignatureVerifier(),
            clock=lambda: NOW,
        )
        first = _release_set("a")
        competing = _release_set("b")
        first_auth = await _authorize(controls, first, "control:postgres:first")
        competing_auth = await _authorize(
            controls,
            competing,
            "control:postgres:competing",
        )
        port = _BlockingPort()
        first_service = FamilyExperienceReleaseSetDeploymentService(
            port,
            store,
            controls,
            transitions=SqlAlchemyReleaseSetTransitionCoordinator(session_factory),
            clock=lambda: NOW,
        )
        competing_service = FamilyExperienceReleaseSetDeploymentService(
            port,
            store,
            controls,
            transitions=SqlAlchemyReleaseSetTransitionCoordinator(session_factory),
            clock=lambda: NOW,
        )

        first_task = asyncio.create_task(
            first_service.apply(
                first,
                first_auth,
                phase="ACTIVE",
                rollout_percent=100,
                idempotency_key="deploy:postgres:first",
            )
        )
        await asyncio.wait_for(port.entered.wait(), timeout=5)

        with pytest.raises(
            ReleaseSetDeploymentError,
            match="RELEASE_SET_TRANSITION_IN_PROGRESS",
        ):
            await competing_service.apply(
                competing,
                competing_auth,
                phase="ACTIVE",
                rollout_percent=100,
                idempotency_key="deploy:postgres:competing",
            )

        assert port.calls == [first.release_set_id]
        port.release.set()
        receipt = await asyncio.wait_for(first_task, timeout=5)
        active = await store.get_active_binding(
            environment="staging",
            use_case=first.use_case,
            data_class=first.data_class,
        )
        assert receipt.sequence == 1
        assert active is not None
        assert active.release_set_id == first.release_set_id
        assert active.deployment_sequence == 1


@pytest.mark.asyncio
@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_postgres_reconciliation_lease_is_single_owner() -> None:
    """Independent workers cannot lease the same uncertain transition."""

    async with postgres_schema_engine(ReleaseSetDeploymentBase.metadata) as engine:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        controls = InMemoryReleaseSetControlStore(
            signature_verifier=_SignatureVerifier(),
            clock=lambda: NOW,
        )
        release_set = _release_set("c")
        control = await controls.authorize(
            release_set,
            kind="APPLY",
            phase="ACTIVE",
            rollout_percent=100,
            target=None,
            expected_effective_sequence=0,
            actor_id="operator:release",
            idempotency_key="control:postgres:reconcile",
            reason="reviewed release transition",
            signature="valid-signature",
            signature_algorithm="external-kms-v1",
        )
        first = SqlAlchemyReleaseSetTransitionCoordinator(
            session_factory,
            clock=lambda: NOW,
        )
        second = SqlAlchemyReleaseSetTransitionCoordinator(
            session_factory,
            clock=lambda: NOW,
        )
        await first.prepare(control, idempotency_key="deploy:postgres:reconcile")
        claim_time = NOW + timedelta(minutes=3)

        claimed = await asyncio.gather(
            first.claim_reconcilable(
                environment="staging",
                worker_id="reconciler:one",
                now=claim_time,
                stale_after=timedelta(minutes=2),
                lease_ttl=timedelta(seconds=30),
                limit=1,
            ),
            second.claim_reconcilable(
                environment="staging",
                worker_id="reconciler:two",
                now=claim_time,
                stale_after=timedelta(minutes=2),
                lease_ttl=timedelta(seconds=30),
                limit=1,
            ),
        )

        assert sum(len(batch) for batch in claimed) == 1
        assert {lease.worker_id for batch in claimed for lease in batch} <= {
            "reconciler:one",
            "reconciler:two",
        }
