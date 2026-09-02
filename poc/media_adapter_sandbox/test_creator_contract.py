"""Contract tests for synthetic, provider-neutral creator publishing."""

from __future__ import annotations

import pytest

from poc.media_adapter_sandbox.creator_contract import (
    DeviceCheckFailed,
    IdempotencyConflict,
    InvalidProducerTransition,
    ProducerDevice,
    ProducerState,
    ProviderFailure,
    PublishCapabilityAuthority,
    PublishCapabilityConsumed,
    PublishCapabilityExpired,
    PublishScopeMismatch,
    StopSwitchEngaged,
    SyntheticCreatorMediaAdapter,
    SyntheticCreatorProvider,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _start(
    adapter: SyntheticCreatorMediaAdapter,
    *,
    creator_ref: str = "creator.synthetic.mili",
    session_ref: str = "live.synthetic.parenting",
    idempotency_key: str = "start-001",
) -> str:
    device = ProducerDevice("device.synthetic.studio")
    capability = adapter.publish_capability(creator_ref, session_ref)
    producer = adapter.start_publish(
        capability.token,
        creator_ref,
        session_ref,
        device,
        idempotency_key,
    )
    return producer.producer_session_ref


def test_device_check_is_synthetic_only_and_requires_all_inputs() -> None:
    adapter = SyntheticCreatorMediaAdapter()
    result = adapter.device_check(ProducerDevice("device.synthetic.ready"))
    assert result.passed
    assert result.source == "synthetic"
    assert result.fixture_only is True

    with pytest.raises(DeviceCheckFailed, match="camera, microphone, and uplink"):
        adapter.device_check(ProducerDevice("device.synthetic.bad", camera_ready=False))
    with pytest.raises(DeviceCheckFailed, match="fixture_only synthetic"):
        adapter.device_check(
            ProducerDevice("device.real.forbidden", source="real", fixture_only=False)
        )


def test_publish_lifecycle_covers_ingesting_live_paused_ended() -> None:
    adapter = SyntheticCreatorMediaAdapter()
    producer_ref = _start(adapter)
    producer = adapter.sessions[producer_ref]
    assert producer.history == [ProducerState.INGESTING, ProducerState.LIVE]

    adapter.pause(producer_ref)
    adapter.resume(producer_ref)
    adapter.end(producer_ref)
    assert producer.history == [
        ProducerState.INGESTING,
        ProducerState.LIVE,
        ProducerState.PAUSED,
        ProducerState.INGESTING,
        ProducerState.LIVE,
        ProducerState.ENDED,
    ]
    with pytest.raises(InvalidProducerTransition):
        adapter.pause(producer_ref)


def test_publish_capability_has_short_ttl_and_is_one_time() -> None:
    clock = Clock()
    authority = PublishCapabilityAuthority(clock=clock)
    adapter = SyntheticCreatorMediaAdapter(authority=authority)
    device = ProducerDevice("device.synthetic.ready")

    with pytest.raises(ValueError, match="between 1 and 60"):
        adapter.publish_capability("creator.synthetic.a", "live.synthetic.a", ttl_seconds=61)

    expired = adapter.publish_capability(
        "creator.synthetic.a", "live.synthetic.expired", ttl_seconds=1
    )
    clock.now += 2
    with pytest.raises(PublishCapabilityExpired):
        adapter.start_publish(
            expired.token,
            expired.creator_ref,
            expired.session_ref,
            device,
            "expired-start",
        )

    first = adapter.publish_capability("creator.synthetic.a", "live.synthetic.once")
    adapter.start_publish(
        first.token,
        first.creator_ref,
        first.session_ref,
        device,
        "once-start",
    )
    with pytest.raises(PublishCapabilityConsumed):
        adapter.start_publish(
            first.token,
            first.creator_ref,
            first.session_ref,
            device,
            "different-retry-key",
        )


def test_start_is_idempotent_only_for_identical_scope_and_input() -> None:
    adapter = SyntheticCreatorMediaAdapter()
    device = ProducerDevice("device.synthetic.ready")
    capability = adapter.publish_capability("creator.synthetic.a", "live.synthetic.a")
    first = adapter.start_publish(
        capability.token,
        capability.creator_ref,
        capability.session_ref,
        device,
        "same-key",
    )
    retry = adapter.start_publish(
        capability.token,
        capability.creator_ref,
        capability.session_ref,
        device,
        "same-key",
    )
    assert retry is first
    assert first.history == [ProducerState.INGESTING, ProducerState.LIVE]

    with pytest.raises(IdempotencyConflict):
        adapter.start_publish(
            capability.token,
            capability.creator_ref,
            capability.session_ref,
            ProducerDevice("device.synthetic.changed"),
            "same-key",
        )


def test_cross_creator_and_session_scope_are_rejected() -> None:
    adapter = SyntheticCreatorMediaAdapter()
    device = ProducerDevice("device.synthetic.ready")
    capability = adapter.publish_capability("creator.synthetic.a", "live.synthetic.a")

    with pytest.raises(PublishScopeMismatch):
        adapter.start_publish(
            capability.token,
            "creator.synthetic.b",
            capability.session_ref,
            device,
            "cross-creator",
        )
    with pytest.raises(PublishScopeMismatch):
        adapter.start_publish(
            capability.token,
            capability.creator_ref,
            "live.synthetic.b",
            device,
            "cross-session",
        )


def test_provider_failure_is_visible_and_reconnect_can_recover() -> None:
    provider = SyntheticCreatorProvider()
    provider.fail_next("begin_publish")
    adapter = SyntheticCreatorMediaAdapter(provider=provider)
    capability = adapter.publish_capability("creator.synthetic.a", "live.synthetic.a")

    with pytest.raises(ProviderFailure, match="begin_publish"):
        adapter.start_publish(
            capability.token,
            capability.creator_ref,
            capability.session_ref,
            ProducerDevice("device.synthetic.ready"),
            "provider-failure",
        )
    producer = next(iter(adapter.sessions.values()))
    assert producer.state is ProducerState.FAILED

    adapter.reconnect(producer.producer_session_ref)
    assert producer.state is ProducerState.LIVE
    assert producer.history[-3:] == [
        ProducerState.FAILED,
        ProducerState.INGESTING,
        ProducerState.LIVE,
    ]


def test_connection_loss_and_reconnect_do_not_create_a_second_session() -> None:
    adapter = SyntheticCreatorMediaAdapter()
    producer_ref = _start(adapter)
    producer = adapter.sessions[producer_ref]

    adapter.connection_lost(producer_ref)
    assert producer.state is ProducerState.INGESTING
    adapter.reconnect(producer_ref)
    assert producer.state is ProducerState.LIVE
    assert len(adapter.sessions) == 1


def test_manual_stop_switch_stops_every_session_and_revokes_publish_scope() -> None:
    adapter = SyntheticCreatorMediaAdapter()
    first_ref = _start(
        adapter,
        session_ref="live.synthetic.first",
        idempotency_key="first",
    )
    second_ref = _start(
        adapter,
        session_ref="live.synthetic.second",
        idempotency_key="second",
    )
    adapter.pause(second_ref)

    adapter.stop_switch()
    assert adapter.sessions[first_ref].state is ProducerState.STOPPED
    assert adapter.sessions[second_ref].state is ProducerState.STOPPED
    with pytest.raises(StopSwitchEngaged):
        adapter.publish_capability("creator.synthetic.mili", "live.synthetic.third")
    with pytest.raises(StopSwitchEngaged):
        adapter.reconnect(first_ref)


def test_stop_switch_remains_fail_closed_when_provider_stop_fails() -> None:
    provider = SyntheticCreatorProvider()
    adapter = SyntheticCreatorMediaAdapter(provider=provider)
    first_ref = _start(
        adapter,
        session_ref="live.synthetic.first",
        idempotency_key="first",
    )
    second_ref = _start(
        adapter,
        session_ref="live.synthetic.second",
        idempotency_key="second",
    )
    provider.fail_next("stop")

    with pytest.raises(ProviderFailure, match="stop"):
        adapter.stop_switch()
    assert adapter.sessions[first_ref].state is ProducerState.STOPPED
    assert adapter.sessions[second_ref].state is ProducerState.STOPPED
    assert ("stop", second_ref) in provider.calls
    with pytest.raises(StopSwitchEngaged):
        adapter.publish_capability("creator.synthetic.mili", "live.synthetic.after-stop")
