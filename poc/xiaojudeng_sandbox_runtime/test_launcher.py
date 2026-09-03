from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

from poc.xiaojudeng_sandbox_runtime.launcher import (
    DEFAULT_PORTS,
    assert_ports_available,
    build_service_specs,
    seed_live_session,
    web_environment,
)


def test_builds_one_explicit_command_per_live_capability(tmp_path: Path) -> None:
    specs = build_service_specs(
        tmp_path,
        tmp_path / "runtime",
        DEFAULT_PORTS,
        tmp_path / "media.json",
        tmp_path / "live.mp4",
    )

    assert [spec.name for spec in specs] == [
        "media",
        "control",
        "interaction",
        "commerce",
        "replay",
        "knowledge",
        "ai",
        "incident",
    ]
    assert all(spec.command[0] == sys.executable for spec in specs)
    assert "--enable-synthetic-consent" in next(
        spec.command for spec in specs if spec.name == "control"
    )
    assert all("0.0.0.0" not in " ".join(spec.command) for spec in specs)


def test_web_environment_connects_every_sandbox_without_production_hosts() -> None:
    media = {
        "source": "synthetic",
        "fixture_only": True,
        "playback_url": "http://127.0.0.1:43123/media/test.mp4?token=test",
        "control_url": "http://127.0.0.1:43123/control/test",
    }

    environment = web_environment(DEFAULT_PORTS, media)

    assert json.loads(environment["VITE_MEDIA_PLAYBACK_DTO"])["fixture_only"] is True
    assert environment["VITE_LIVE_CONTROL_BASE_URL"] == "http://127.0.0.1:55300"
    assert environment["VITE_LIVE_INTERACTION_WS_URL"] == "ws://127.0.0.1:55200"
    assert all("127.0.0.1" in value or value.startswith("{") for value in environment.values())


def test_port_conflicts_fail_closed() -> None:
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        with pytest.raises(RuntimeError, match=f"web:{port}"):
            assert_ports_available({"web": port})


def test_seed_live_session_requires_three_human_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, str], dict[str, object]]] = []

    class Response:
        status = 200

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"LIVE","fixture_only":true,"source":"SANDBOX_SYNTHETIC"}'

    def open_request(request: object, timeout: float) -> Response:
        calls.append(
            (
                request.full_url,  # type: ignore[attr-defined]
                dict(request.headers),  # type: ignore[attr-defined]
                json.loads(request.data),  # type: ignore[attr-defined]
            )
        )
        assert timeout == 3
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", open_request)

    result = seed_live_session("http://127.0.0.1:55300")

    assert result["status"] == "LIVE"
    assert [headers["X-actor-role"] for _, headers, _ in calls] == [
        "CREATOR",
        "CONTENT_REVIEWER",
        "LIVE_OPERATOR",
    ]
    assert all(payload for _, _, payload in calls)
