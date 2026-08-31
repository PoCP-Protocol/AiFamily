"""Acceptance tests for the synthetic-only MediaAdapter and playable artifact."""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from poc.media_adapter_sandbox.contract import (
    CapabilityAuthority,
    CapabilityExpired,
    CapabilityReplay,
    CapabilityRevoked,
    CapabilityScopeMismatch,
    FaultKind,
    MediaState,
    ProviderFailure,
    SyntheticSource,
)
from poc.media_adapter_sandbox.fake_provider import FakeMediaProvider
from poc.media_adapter_sandbox.fault_injector import FaultInjector
from poc.media_adapter_sandbox.replay_harness import (
    SandboxPlayerServer,
    SyntheticMediaAdapter,
    SyntheticVideoFactory,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def video(tmp_path: Path) -> Path:
    return SyntheticVideoFactory.create(tmp_path / "synthetic.mp4", duration_seconds=1.5)


@pytest.fixture
def adapter() -> SyntheticMediaAdapter:
    return SyntheticMediaAdapter()


def test_real_playable_video_ingest_adapter_player_and_replay(
    video: Path, adapter: SyntheticMediaAdapter
) -> None:
    session = adapter.start(SyntheticSource(video), "family.synthetic.alpha")
    capability = adapter.playback_capability(session.media_session_ref, session.family_ref)

    ffprobe = "ffprobe"
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=format_name", "-of", "json", str(video)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    assert "mov" in json.loads(probe.stdout)["format"]["format_name"]
    assert hashlib.sha256(video.read_bytes()).hexdigest() == SyntheticVideoFactory.sha256(video)

    with SandboxPlayerServer(adapter) as server:
        player = urllib.request.urlopen(server.player_url(capability), timeout=2).read()
        assert b"<video" in player
        media = urllib.request.urlopen(adapter.playback_url(server, capability), timeout=2).read()
        assert media[4:8] == b"ftyp"


def test_lifecycle_covers_live_disconnected_restarted_stopped_and_revoked(
    video: Path, adapter: SyntheticMediaAdapter
) -> None:
    session = adapter.start(SyntheticSource(video), "family.synthetic.alpha")
    adapter.disconnect(session.media_session_ref)
    assert session.state is MediaState.DISCONNECTED
    adapter.reconnect(session.media_session_ref)
    adapter.stop(session.media_session_ref)
    assert session.state is MediaState.STOPPED
    assert session.history == [
        MediaState.NEW,
        MediaState.LIVE,
        MediaState.DISCONNECTED,
        MediaState.RESTARTED,
        MediaState.LIVE,
        MediaState.STOPPED,
    ]

    revoked = adapter.start(SyntheticSource(video), "family.synthetic.alpha")
    capability = adapter.playback_capability(revoked.media_session_ref, revoked.family_ref)
    adapter.revoke(revoked.media_session_ref)
    assert revoked.state is MediaState.REVOKED
    with pytest.raises(CapabilityRevoked):
        adapter.playback_bytes(capability.token)


def test_ttl_revoke_and_replay_negative_paths() -> None:
    clock = Clock()
    authority = CapabilityAuthority(clock=clock)
    capability = authority.issue("media.synthetic.1", "family.synthetic.alpha", ttl_seconds=1)
    authority.verify(capability.token, capability.media_session_ref, capability.family_ref)
    with pytest.raises(CapabilityReplay):
        authority.verify(capability.token, capability.media_session_ref, capability.family_ref)
    expiring = authority.issue("media.synthetic.2", "family.synthetic.alpha", ttl_seconds=1)
    clock.now += 2
    with pytest.raises(CapabilityExpired):
        authority.verify(expiring.token, "media.synthetic.2", "family.synthetic.alpha")


def test_token_revoke_and_cross_family_are_denied() -> None:
    authority = CapabilityAuthority()
    capability = authority.issue("media.synthetic.1", "family.synthetic.alpha")
    authority.revoke_token(capability.token)
    with pytest.raises(CapabilityRevoked):
        authority.verify(capability.token, "media.synthetic.1", "family.synthetic.alpha")

    other = authority.issue("media.synthetic.2", "family.synthetic.alpha")
    with pytest.raises(CapabilityScopeMismatch):
        authority.verify(other.token, "media.synthetic.2", "family.synthetic.beta")


def test_provider_failure_is_visible_and_does_not_create_live_session(video: Path) -> None:
    faults = FaultInjector()
    faults.inject(FaultKind.PROVIDER_FAILURE)
    adapter = SyntheticMediaAdapter(provider=FakeMediaProvider(faults), faults=faults)
    with pytest.raises(ProviderFailure, match="injected"):
        adapter.start(SyntheticSource(video), "family.synthetic.alpha")
    assert adapter.sessions["media.synthetic.1"].state is MediaState.FAILED


def test_stop_switch_rejects_new_admission_and_stops_existing(
    video: Path, adapter: SyntheticMediaAdapter
) -> None:
    session = adapter.start(SyntheticSource(video), "family.synthetic.alpha")
    adapter.stop_switch()
    assert session.state is MediaState.STOPPED
    with pytest.raises(ProviderFailure, match="stop switch"):
        adapter.start(SyntheticSource(video), "family.synthetic.alpha")


def test_synthetic_and_fixture_only_are_hard_requirements(
    video: Path, adapter: SyntheticMediaAdapter
) -> None:
    with pytest.raises(ValueError, match="synthetic"):
        adapter.start(
            SyntheticSource(video, source="real", fixture_only=False),
            "family.synthetic.alpha",
        )


def test_browser_control_disconnect_recover_stop_and_revoke(video: Path) -> None:
    adapter = SyntheticMediaAdapter()
    session = adapter.start(SyntheticSource(video), "family.synthetic.alpha")
    original = adapter.playback_capability(session.media_session_ref, session.family_ref)
    with SandboxPlayerServer(adapter) as server:
        control = f"{server.base_url}/control/{session.media_session_ref}"

        urllib.request.urlopen(urllib.request.Request(f"{control}/disconnect", method="POST"))
        assert session.state is MediaState.DISCONNECTED
        recovered = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(f"{control}/recover", method="POST")
            ).read()
        )
        assert recovered["state"] == "LIVE"
        assert recovered["playback_url"].startswith(server.base_url)
        urllib.request.urlopen(urllib.request.Request(f"{control}/stop", method="POST"))
        assert session.state is MediaState.STOPPED
        with pytest.raises(urllib.error.HTTPError) as stopped:
            urllib.request.urlopen(adapter.playback_url(server, original))
        assert stopped.value.code == 403
        revoked_response = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(f"{control}/revoke", method="POST")
            ).read()
        )
        assert revoked_response["state"] == "REVOKED"

    revoked_adapter = SyntheticMediaAdapter()
    revoked = revoked_adapter.start(SyntheticSource(video), "family.synthetic.alpha")
    token = revoked_adapter.playback_capability(revoked.media_session_ref, revoked.family_ref)
    with SandboxPlayerServer(revoked_adapter) as server:
        control = f"{server.base_url}/control/{revoked.media_session_ref}"
        urllib.request.urlopen(urllib.request.Request(f"{control}/revoke", method="POST"))
        assert revoked.state is MediaState.REVOKED
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(revoked_adapter.playback_url(server, token))
        assert denied.value.code == 403
