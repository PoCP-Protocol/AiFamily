from __future__ import annotations

import asyncio
from datetime import UTC, datetime

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
    ReleaseSetDeploymentError,
    ReleaseSetDeploymentReceipt,
)

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


class _Port:
    def __init__(self) -> None:
        self.bad_ack = False
        self.calls: list[tuple[str, str]] = []

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
        self.calls.append(("APPLY", release_set.release_set_id))
        return self._ack(
            release_set,
            transition_id,
            control_id,
            expected_effective_sequence,
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
        self.calls.append(("ROLLBACK", target.release_set_id))
        return self._ack(
            target,
            transition_id,
            control_id,
            expected_effective_sequence,
        )

    def _ack(
        self,
        release_set: FamilyExperienceReleaseSet,
        transition_id: str,
        control_id: str,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentAcknowledgement:
        return ReleaseSetDeploymentAcknowledgement(
            acknowledged_release_set_id=(
                "wrong" if self.bad_ack else release_set.release_set_id
            ),
            applied_config_digest=release_set.runtime_config_digest,
            external_ref=f"deploy:{release_set.release_set_id}",
            transition_id=transition_id,
            control_id=control_id,
            expected_effective_sequence=expected_effective_sequence,
        )


class _SignatureVerifier:
    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool:
        return bool(payload and actor_id) and signature == "valid-signature"


class _BlockingPort(_Port):
    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

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
        self.calls.append(("APPLY", release_set.release_set_id))
        self.entered.set()
        await self.release.wait()
        return self._ack(
            release_set,
            transition_id,
            control_id,
            expected_effective_sequence,
        )


class _FlakyPort(_Port):
    def __init__(self) -> None:
        super().__init__()
        self.fail = True

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
        self.calls.append(("APPLY", release_set.release_set_id))
        if self.fail:
            raise TimeoutError("external state unknown")
        return self._ack(
            release_set,
            transition_id,
            control_id,
            expected_effective_sequence,
        )


def _controls() -> InMemoryReleaseSetControlStore:
    return InMemoryReleaseSetControlStore(
        signature_verifier=_SignatureVerifier(),
        clock=lambda: NOW,
    )


def _service(port, store, controls):  # type: ignore[no-untyped-def]
    return FamilyExperienceReleaseSetDeploymentService(
        port,
        store,
        controls,
        clock=lambda: NOW,
    )


async def _authorization(
    controls: InMemoryReleaseSetControlStore,
    source: FamilyExperienceReleaseSet,
    *,
    phase: str = "ACTIVE",
    rollout_percent: int = 100,
    target: FamilyExperienceReleaseSet | None = None,
    expected_effective_sequence: int = 0,
    key: str,
) -> ReleaseSetDeploymentAuthorization:
    kind = "ROLLBACK" if target is not None else "APPLY"
    event = await controls.authorize(
        source,
        kind=kind,
        phase=phase,
        rollout_percent=rollout_percent,
        target=target,
        expected_effective_sequence=expected_effective_sequence,
        actor_id="operator:release",
        idempotency_key=key,
        reason="reviewed release transition",
        signature="valid-signature",
        signature_algorithm="external-kms-v1",
    )
    return ReleaseSetDeploymentAuthorization(event.control_id, event.actor_id)


def test_receipt_rejects_illegal_operation_phase_combination() -> None:
    with pytest.raises(ReleaseSetDeploymentError, match="TRANSITION_INVALID"):
        ReleaseSetDeploymentReceipt(
            sequence=1,
            receipt_id="receipt:invalid",
            idempotency_key="deploy:invalid",
            release_set_id="a" * 64,
            target_release_set_id=None,
            environment="staging",
            use_case="family_assistant_conversation",
            data_class="OPERATIONAL_TEXT",
            operation="APPLY",
            phase="ROLLED_BACK",
            rollout_percent=0,
            control_id="control:release",
            actor_id="operator:release",
            applied_config_digest="d" * 64,
            acknowledged_release_set_id="a" * 64,
            external_ref="deployment:invalid",
            created_at=NOW,
        )


@pytest.mark.asyncio
async def test_active_apply_is_atomic_idempotent_and_canary_is_not_effective() -> None:
    port = _Port()
    store = InMemoryReleaseSetDeploymentStore()
    controls = _controls()
    service = _service(port, store, controls)
    release_set = _release_set("a")
    canary_auth = await _authorization(
        controls,
        release_set,
        phase="CANARY",
        rollout_percent=5,
        key="control:canary",
    )
    await service.apply(
        release_set,
        canary_auth,
        phase="CANARY",
        rollout_percent=5,
        idempotency_key="deploy:canary",
    )
    assert (
        await store.latest_effective(
            environment="staging",
            use_case=release_set.use_case,
            data_class=release_set.data_class,
        )
        is None
    )
    active_auth = await _authorization(
        controls,
        release_set,
        key="control:active",
    )
    active = await service.apply(
        release_set,
        active_auth,
        phase="ACTIVE",
        rollout_percent=100,
        idempotency_key="deploy:active",
    )
    replay = await service.apply(
        release_set,
        active_auth,
        phase="ACTIVE",
        rollout_percent=100,
        idempotency_key="deploy:active",
    )
    assert replay == active
    assert active.sequence == 2
    assert port.calls == [("APPLY", release_set.release_set_id)] * 2


@pytest.mark.asyncio
async def test_rollback_requires_historically_active_target_and_restores_it() -> None:
    port = _Port()
    store = InMemoryReleaseSetDeploymentStore()
    controls = _controls()
    service = _service(port, store, controls)
    old = _release_set("a")
    current = _release_set("b")
    invalid_rollback_auth = await _authorization(
        controls,
        current,
        target=old,
        phase="ROLLED_BACK",
        rollout_percent=0,
        key="control:rollback:invalid",
    )
    with pytest.raises(ReleaseSetDeploymentError, match="TARGET_WAS_NOT_ACTIVE"):
        await service.rollback(
            current,
            old,
            invalid_rollback_auth,
            idempotency_key="rollback:invalid",
        )
    for expected_sequence, item in enumerate((old, current)):
        auth = await _authorization(
            controls,
            item,
            expected_effective_sequence=expected_sequence,
            key=f"control:apply:{item.release_set_id}",
        )
        await service.apply(
            item,
            auth,
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key=f"deploy:{item.release_set_id}",
        )
    rollback_auth = await _authorization(
        controls,
        current,
        target=old,
        phase="ROLLED_BACK",
        rollout_percent=0,
        expected_effective_sequence=2,
        key="control:rollback:old",
    )
    receipt = await service.rollback(
        current,
        old,
        rollback_auth,
        idempotency_key="rollback:old",
    )
    assert receipt.target_release_set_id == old.release_set_id
    assert receipt.acknowledged_release_set_id == old.release_set_id
    latest = await store.latest_effective(
        environment="staging",
        use_case=old.use_case,
        data_class=old.data_class,
    )
    assert latest == receipt


@pytest.mark.asyncio
async def test_external_ack_mismatch_is_not_recorded() -> None:
    port = _Port()
    port.bad_ack = True
    store = InMemoryReleaseSetDeploymentStore()
    controls = _controls()
    release_set = _release_set("a")
    auth = await _authorization(
        controls,
        release_set,
        key="control:bad-ack",
    )
    with pytest.raises(ReleaseSetDeploymentError, match="ACK_MISMATCH"):
        await _service(port, store, controls).apply(
            release_set,
            auth,
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key="deploy:bad-ack",
        )
    assert await store.get_by_idempotency("deploy:bad-ack") is None


@pytest.mark.asyncio
async def test_signed_control_cannot_authorize_another_release_set() -> None:
    port = _Port()
    store = InMemoryReleaseSetDeploymentStore()
    controls = _controls()
    source = _release_set("a")
    forged_target = _release_set("b")
    auth = await _authorization(controls, source, key="control:source-a")

    with pytest.raises(ReleaseSetDeploymentError, match="SIGNED_CONTROL_MISMATCH"):
        await _service(port, store, controls).apply(
            forged_target,
            auth,
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key="deploy:forged-b",
        )

    assert port.calls == []


@pytest.mark.asyncio
async def test_stale_signed_sequence_blocks_before_external_deployment() -> None:
    port = _Port()
    store = InMemoryReleaseSetDeploymentStore()
    controls = _controls()
    first = _release_set("a")
    stale = _release_set("b")
    first_auth = await _authorization(controls, first, key="control:first")
    stale_auth = await _authorization(
        controls,
        stale,
        expected_effective_sequence=0,
        key="control:stale",
    )
    service = _service(port, store, controls)
    await service.apply(
        first,
        first_auth,
        phase="ACTIVE",
        rollout_percent=100,
        idempotency_key="deploy:first",
    )

    with pytest.raises(ReleaseSetDeploymentError, match="STALE_CONTROL"):
        await service.apply(
            stale,
            stale_auth,
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key="deploy:stale",
        )

    assert port.calls == [("APPLY", first.release_set_id)]


@pytest.mark.asyncio
async def test_release_set_deployment_rejects_ai_actor_and_invalid_rollout() -> None:
    with pytest.raises(ReleaseSetDeploymentError, match="AI_RELEASE_SET_DEPLOYER"):
        ReleaseSetDeploymentAuthorization("control", "ai:operator")
    with pytest.raises(ReleaseSetDeploymentError, match="PHASE_INVALID"):
        await _service(
            _Port(),
            InMemoryReleaseSetDeploymentStore(),
            _controls(),
        ).apply(
            _release_set("a"),
            ReleaseSetDeploymentAuthorization("missing", "operator:release"),
            phase="ACTIVE",
            rollout_percent=99,
            idempotency_key="deploy:invalid",
        )


@pytest.mark.asyncio
async def test_prepared_transition_blocks_concurrent_external_side_effect() -> None:
    port = _BlockingPort()
    store = InMemoryReleaseSetDeploymentStore()
    controls = _controls()
    first = _release_set("a")
    competing = _release_set("b")
    first_auth = await _authorization(controls, first, key="control:concurrent:first")
    competing_auth = await _authorization(
        controls,
        competing,
        key="control:concurrent:competing",
    )
    first_service = _service(port, store, controls)
    competing_service = _service(port, store, controls)
    first_task = asyncio.create_task(
        first_service.apply(
            first,
            first_auth,
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key="deploy:concurrent:first",
        )
    )
    await port.entered.wait()

    with pytest.raises(ReleaseSetDeploymentError, match="TRANSITION_IN_PROGRESS"):
        await competing_service.apply(
            competing,
            competing_auth,
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key="deploy:concurrent:competing",
        )

    assert port.calls == [("APPLY", first.release_set_id)]
    port.release.set()
    await first_task


@pytest.mark.asyncio
async def test_unknown_external_result_blocks_new_transition_but_same_key_recovers() -> None:
    port = _FlakyPort()
    store = InMemoryReleaseSetDeploymentStore()
    controls = _controls()
    first = _release_set("a")
    competing = _release_set("b")
    first_auth = await _authorization(controls, first, key="control:unknown:first")
    competing_auth = await _authorization(
        controls,
        competing,
        key="control:unknown:competing",
    )
    service = _service(port, store, controls)
    with pytest.raises(TimeoutError):
        await service.apply(
            first,
            first_auth,
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key="deploy:unknown:first",
        )
    with pytest.raises(ReleaseSetDeploymentError, match="TRANSITION_IN_PROGRESS"):
        await service.apply(
            competing,
            competing_auth,
            phase="ACTIVE",
            rollout_percent=100,
            idempotency_key="deploy:unknown:competing",
        )

    port.fail = False
    receipt = await service.apply(
        first,
        first_auth,
        phase="ACTIVE",
        rollout_percent=100,
        idempotency_key="deploy:unknown:first",
    )
    assert receipt.release_set_id == first.release_set_id
    assert port.calls == [
        ("APPLY", first.release_set_id),
        ("APPLY", first.release_set_id),
    ]
