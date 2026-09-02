import pytest

from poc.media_adapter_sandbox.contract import CapabilityRevoked, SyntheticSource
from poc.media_adapter_sandbox.replay_harness import (
    SyntheticMediaAdapter,
    temporary_artifact,
)
from poc.standalone_live_control_sandbox.media_session_bridge import (
    LIVE_ATTENDANCE_PURPOSE,
    AdultPlaybackContext,
    BindingStatus,
    ControlMediaBridge,
    InMemoryMediaBindingStore,
    LiveSessionProjection,
    MediaBindingConflict,
    MediaBridgeRejected,
    MediaProviderUnavailable,
    PlaybackCapabilityView,
    ReviewStatus,
    SessionStatus,
)


class FakeMediaRuntime:
    def __init__(self) -> None:
        self.started: list[dict[str, str]] = []
        self.revoked: list[dict[str, str]] = []
        self.issue_calls: list[dict[str, object]] = []
        self.fail_start = False
        self.fail_issue = False
        self.fail_revoke = False

    def start(self, **kwargs: str) -> tuple[str, str]:
        if self.fail_start:
            raise RuntimeError("provider down")
        self.started.append(kwargs)
        return "media.synthetic.1", "provider.synthetic"

    def issue_playback(self, **kwargs: object) -> PlaybackCapabilityView:
        if self.fail_issue:
            raise RuntimeError("capability authority down")
        self.issue_calls.append(kwargs)
        return PlaybackCapabilityView(
            token="capability.synthetic",
            media_session_ref=str(kwargs["media_session_ref"]),
            family_id=str(kwargs["family_id"]),
            ttl_seconds=int(kwargs["ttl_seconds"]),
        )

    def revoke(self, **kwargs: str) -> None:
        if self.fail_revoke:
            raise RuntimeError("provider revoke failed")
        self.revoked.append(kwargs)


class RealSandboxMediaPort:
    def __init__(self, source: SyntheticSource) -> None:
        self.source = source
        self.adapter = SyntheticMediaAdapter()

    def start(self, **kwargs: str) -> tuple[str, str]:
        assert kwargs["source_ref"] == "synthetic:fixture.mp4"
        media_session = self.adapter.start(self.source, kwargs["family_id"])
        return media_session.media_session_ref, media_session.provider_ref

    def issue_playback(self, **kwargs: object) -> PlaybackCapabilityView:
        capability = self.adapter.playback_capability(
            str(kwargs["media_session_ref"]),
            str(kwargs["family_id"]),
            int(kwargs["ttl_seconds"]),
        )
        return PlaybackCapabilityView(
            token=capability.token,
            media_session_ref=capability.media_session_ref,
            family_id=capability.family_ref,
            ttl_seconds=int(kwargs["ttl_seconds"]),
        )

    def revoke(self, **kwargs: str) -> None:
        self.adapter.revoke(kwargs["media_session_ref"])


def session(**overrides: object) -> LiveSessionProjection:
    values: dict[str, object] = {
        "tenant_id": "tenant.synthetic.alpha",
        "family_id": "family.synthetic.alpha",
        "session_ref": "live.synthetic.1",
        "review_status": ReviewStatus.APPROVED,
        "status": SessionStatus.LIVE,
    }
    values.update(overrides)
    return LiveSessionProjection(**values)


def adult(**overrides: str) -> AdultPlaybackContext:
    values = {
        "tenant_id": "tenant.synthetic.alpha",
        "family_id": "family.synthetic.alpha",
        "guardian_id": "guardian.synthetic.adult",
        "purpose": LIVE_ATTENDANCE_PURPOSE,
        "consent_ref": "consent.synthetic.active",
    }
    values.update(overrides)
    return AdultPlaybackContext(**values)


def make_bridge():
    media = FakeMediaRuntime()
    store = InMemoryMediaBindingStore()
    return ControlMediaBridge(media=media, store=store), media, store


def test_approved_live_session_binds_media_and_issues_scoped_capability() -> None:
    bridge, media, store = make_bridge()
    binding = bridge.start(
        session=session(),
        source_ref="synthetic:fixture.mp4",
        operator_id="human:operator-1",
        idempotency_key="start:1",
    )
    capability = bridge.authorize_playback(session=session(), adult=adult(), ttl_seconds=20)
    assert binding.status is BindingStatus.ACTIVE
    assert binding.media_session_ref == capability.media_session_ref
    assert capability.family_id == "family.synthetic.alpha"
    assert capability.ttl_seconds == 20
    assert len(media.started) == 1
    assert store.receipts[0]["audit_mode"] == "SANDBOX_RECEIPT_ONLY"
    assert store.receipts[0]["external_effect"] is False


@pytest.mark.parametrize(
    "projection",
    [
        session(review_status=ReviewStatus.DRAFT),
        session(review_status=ReviewStatus.WITHDRAWN),
        session(status=SessionStatus.SCHEDULED),
        session(status=SessionStatus.ENDED),
        session(status=SessionStatus.WITHDRAWN),
    ],
)
def test_unapproved_or_not_live_session_never_starts_media(
    projection: LiveSessionProjection,
) -> None:
    bridge, media, _ = make_bridge()
    with pytest.raises(MediaBridgeRejected):
        bridge.start(
            session=projection,
            source_ref="synthetic:fixture.mp4",
            operator_id="human:operator-1",
            idempotency_key="start:blocked",
        )
    assert media.started == []


def test_cross_family_missing_consent_and_provider_failure_fail_closed() -> None:
    bridge, media, _ = make_bridge()
    bridge.start(
        session=session(),
        source_ref="synthetic:fixture.mp4",
        operator_id="human:operator-1",
        idempotency_key="start:1",
    )
    for context in (
        adult(family_id="family.synthetic.other"),
        adult(purpose="other"),
        adult(consent_ref=""),
    ):
        with pytest.raises(MediaBridgeRejected):
            bridge.authorize_playback(session=session(), adult=context)
    media.fail_issue = True
    with pytest.raises(MediaProviderUnavailable):
        bridge.authorize_playback(session=session(), adult=adult())


def test_start_idempotency_and_payload_conflict() -> None:
    bridge, media, _ = make_bridge()
    first = bridge.start(
        session=session(),
        source_ref="synthetic:fixture.mp4",
        operator_id="human:operator-1",
        idempotency_key="start:replay",
    )
    second = bridge.start(
        session=session(),
        source_ref="synthetic:fixture.mp4",
        operator_id="human:operator-1",
        idempotency_key="start:replay",
    )
    assert first == second
    assert len(media.started) == 1
    with pytest.raises(MediaBindingConflict):
        bridge.start(
            session=session(),
            source_ref="synthetic:other.mp4",
            operator_id="human:operator-1",
            idempotency_key="start:replay",
        )


def test_provider_failure_does_not_create_binding() -> None:
    bridge, media, store = make_bridge()
    media.fail_start = True
    with pytest.raises(MediaProviderUnavailable):
        bridge.start(
            session=session(),
            source_ref="synthetic:fixture.mp4",
            operator_id="human:operator-1",
            idempotency_key="start:failure",
        )
    assert store.bindings == {}
    assert store.receipts == []


def test_commit_failure_compensates_by_revoking_orphan_media() -> None:
    bridge, media, store = make_bridge()
    store.fail_next_commit = True
    with pytest.raises(RuntimeError, match="binding commit"):
        bridge.start(
            session=session(),
            source_ref="synthetic:fixture.mp4",
            operator_id="human:operator-1",
            idempotency_key="start:commit-failure",
        )
    assert media.revoked[0]["reason"] == "compensate failed control binding commit"
    assert store.bindings == {}


def test_human_stop_revokes_capabilities_before_marking_binding_revoked() -> None:
    bridge, media, store = make_bridge()
    bridge.start(
        session=session(),
        source_ref="synthetic:fixture.mp4",
        operator_id="human:operator-1",
        idempotency_key="start:1",
    )
    stopped = bridge.stop(
        session=session(status=SessionStatus.WITHDRAWN),
        actor_id="human:moderator-1",
        reason="content safety withdrawal",
        idempotency_key="stop:1",
    )
    assert stopped.status is BindingStatus.REVOKED
    assert store.find(session().session_ref) == stopped
    assert media.revoked == [
        {
            "media_session_ref": "media.synthetic.1",
            "reason": "content safety withdrawal",
        }
    ]
    with pytest.raises(MediaBridgeRejected):
        bridge.authorize_playback(session=session(), adult=adult())


def test_ai_creator_and_failed_provider_cannot_claim_successful_stop() -> None:
    bridge, media, store = make_bridge()
    bridge.start(
        session=session(),
        source_ref="synthetic:fixture.mp4",
        operator_id="human:operator-1",
        idempotency_key="start:1",
    )
    for actor_id in ("ai:moderator", "creator:synthetic", "child:synthetic"):
        with pytest.raises(MediaBridgeRejected):
            bridge.stop(
                session=session(),
                actor_id=actor_id,
                reason="unauthorised",
                idempotency_key=f"stop:{actor_id}",
            )
    media.fail_revoke = True
    with pytest.raises(MediaProviderUnavailable):
        bridge.stop(
            session=session(),
            actor_id="human:operator-1",
            reason="provider failure drill",
            idempotency_key="stop:provider-failure",
        )
    assert store.find(session().session_ref).status is BindingStatus.ACTIVE


def test_bridge_drives_real_synthetic_video_and_revokes_new_capability() -> None:
    with temporary_artifact() as media_path:
        media = RealSandboxMediaPort(SyntheticSource(media_path))
        store = InMemoryMediaBindingStore()
        bridge = ControlMediaBridge(media=media, store=store)
        bridge.start(
            session=session(),
            source_ref="synthetic:fixture.mp4",
            operator_id="human:operator-1",
            idempotency_key="start:real-media",
        )
        first = bridge.authorize_playback(session=session(), adult=adult())
        assert media.adapter.playback_bytes(first.token)
        second = bridge.authorize_playback(session=session(), adult=adult())
        bridge.stop(
            session=session(status=SessionStatus.WITHDRAWN),
            actor_id="human:operator-1",
            reason="withdraw fixture",
            idempotency_key="stop:real-media",
        )
        with pytest.raises(CapabilityRevoked):
            media.adapter.playback_bytes(second.token)
