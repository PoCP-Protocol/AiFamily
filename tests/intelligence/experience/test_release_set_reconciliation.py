from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.experience.release_set import FamilyExperienceReleaseSet
from backend.intelligence.experience.release_set_control import (
    InMemoryReleaseSetControlStore,
)
from backend.intelligence.experience.release_set_deployment import (
    FamilyExperienceReleaseSetDeploymentService,
    InMemoryReleaseSetDeploymentStore,
    ReleaseSetDeploymentAcknowledgement,
    ReleaseSetDeploymentAuthorization,
)
from backend.intelligence.experience.release_set_persistence import (
    InMemoryFamilyExperienceReleaseSetStore,
)
from backend.intelligence.experience.release_set_reconciliation import (
    ExternalTransitionObservation,
    ReconciliationOutcome,
    ReleaseSetReconciliationScheduler,
)

NOW = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


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


class _Verifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        return bool(payload and actor_id) and signature == "valid-signature"


class _UnknownThenObservedPort:
    def __init__(self) -> None:
        self.state = "APPLIED"
        self.apply_calls = 0
        self.observe_calls = 0

    async def apply(self, release_set, **kwargs):  # type: ignore[no-untyped-def]
        self.apply_calls += 1
        raise TimeoutError("external result is unknown")

    async def rollback(self, *args, **kwargs):  # pragma: no cover - protocol only
        raise AssertionError("rollback is not used")

    async def observe(self, transition):  # type: ignore[no-untyped-def]
        self.observe_calls += 1
        if self.state == "APPLIED":
            return ExternalTransitionObservation(
                state="APPLIED",
                acknowledgement=ReleaseSetDeploymentAcknowledgement(
                    acknowledged_release_set_id=transition.source_release_set_id,
                    applied_config_digest=transition.runtime_config_digest,
                    external_ref="deployment:observed",
                    transition_id=transition.transition_id,
                    control_id=transition.control_id,
                    expected_effective_sequence=(
                        transition.expected_effective_sequence
                    ),
                ),
            )
        return ExternalTransitionObservation(state="PENDING")


async def _unknown_runtime():
    release_set = _release_set()
    release_sets = InMemoryFamilyExperienceReleaseSetStore()
    await release_sets.append(release_set)
    controls = InMemoryReleaseSetControlStore(
        signature_verifier=_Verifier(),
        clock=lambda: NOW,
    )
    control = await controls.authorize(
        release_set,
        kind="APPLY",
        phase="ACTIVE",
        rollout_percent=100,
        target=None,
        expected_effective_sequence=0,
        actor_id="operator:release",
        idempotency_key="control:unknown",
        reason="reviewed release",
        signature="valid-signature",
        signature_algorithm="external-kms-v1",
    )
    port = _UnknownThenObservedPort()
    store = InMemoryReleaseSetDeploymentStore()
    deployment = FamilyExperienceReleaseSetDeploymentService(
        port,
        store,
        controls,
        clock=lambda: NOW,
    )
    with pytest.raises(TimeoutError):
        await deployment.apply(
            release_set,
            ReleaseSetDeploymentAuthorization(control.control_id, control.actor_id),
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key="deploy:unknown",
        )
    assert deployment.transitions is not None
    return release_set, release_sets, port, store, deployment


@pytest.mark.asyncio
async def test_unknown_transition_is_committed_from_exact_observed_ack() -> None:
    release_set, release_sets, port, store, deployment = await _unknown_runtime()
    scheduler = ReleaseSetReconciliationScheduler(
        environment="test",
        worker_id="reconciler:test:1",
        transitions=deployment.transitions,  # type: ignore[arg-type]
        release_sets=release_sets,
        observer=port,
        deployment=deployment,
        stale_after=timedelta(minutes=2),
        clock=lambda: NOW + timedelta(minutes=3),
    )

    report = await scheduler.run_once()

    assert report.claimed == 1
    assert report.results[0].outcome is ReconciliationOutcome.COMMITTED
    assert report.results[0].receipt_id is not None
    assert port.apply_calls == 1
    active = await store.get_active_binding(
        environment="test",
        use_case=release_set.use_case,
        data_class=release_set.data_class,
    )
    assert active is not None
    assert active.release_set_id == release_set.release_set_id


@pytest.mark.asyncio
async def test_pending_transition_is_backed_off_without_replaying_apply() -> None:
    _, release_sets, port, _, deployment = await _unknown_runtime()
    port.state = "PENDING"
    scheduler = ReleaseSetReconciliationScheduler(
        environment="test",
        worker_id="reconciler:test:1",
        transitions=deployment.transitions,  # type: ignore[arg-type]
        release_sets=release_sets,
        observer=port,
        deployment=deployment,
        stale_after=timedelta(minutes=2),
        retry_base=timedelta(minutes=1),
        clock=lambda: NOW + timedelta(minutes=3),
    )

    first = await scheduler.run_once()
    immediate = await scheduler.run_once()

    assert first.results[0].outcome is ReconciliationOutcome.RESCHEDULED
    assert immediate.claimed == 0
    assert port.apply_calls == 1


@pytest.mark.asyncio
async def test_acknowledged_crash_window_commits_without_external_requery() -> None:
    release_set, release_sets, port, store, deployment = await _unknown_runtime()
    transitions = deployment.transitions
    assert transitions is not None
    claim = await transitions.get_by_idempotency("deploy:unknown")
    assert claim is not None
    acknowledgement = ReleaseSetDeploymentAcknowledgement(
        acknowledged_release_set_id=release_set.release_set_id,
        applied_config_digest=release_set.runtime_config_digest,
        external_ref="deployment:persisted-ack",
        transition_id=claim.transition_id,
        control_id=claim.control_id,
        expected_effective_sequence=claim.expected_effective_sequence,
    )
    await transitions.acknowledge(claim, acknowledgement)
    scheduler = ReleaseSetReconciliationScheduler(
        environment="test",
        worker_id="reconciler:test:ack",
        transitions=transitions,
        release_sets=release_sets,
        observer=port,
        deployment=deployment,
        stale_after=timedelta(minutes=2),
        clock=lambda: NOW + timedelta(minutes=3),
    )

    report = await scheduler.run_once()

    assert report.results[0].outcome is ReconciliationOutcome.COMMITTED
    assert port.observe_calls == 0
    active = await store.get_active_binding(
        environment="test",
        use_case=release_set.use_case,
        data_class=release_set.data_class,
    )
    assert active is not None
