from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import pytest

from poc.xiaojudeng_sandbox_runtime.launcher import (
    DEFAULT_PORTS,
    RuntimeControlServer,
    assert_ports_available,
    build_service_specs,
    dynamic_ports,
    parse_port_overrides,
    process_exists,
    seed_live_session,
    stop_runtime,
    web_environment,
)


def test_process_exists_handles_current_and_invalid_processes() -> None:
    assert process_exists(os.getpid()) is True
    assert process_exists(0) is False
    assert process_exists(2_147_483_647) is False


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


def test_stop_runtime_requires_verified_control_identity_and_released_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = {
        "runtime_id": "runtime-test",
        "launcher_pid": 43210,
        "started_at": "2026-09-03T00:00:00+00:00",
        "executable": str(Path(sys.executable).resolve()),
        "runtime_dir": str(tmp_path.resolve()),
        "service_pids": {"media": 43211},
    }
    control = RuntimeControlServer("runtime-test", "secret-test", identity)
    control.start()
    media = tmp_path / "media.json"
    media.write_text(json.dumps({"control_url": "http://127.0.0.1:54321/control/live"}))
    manifest = {
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
        "external_effect": False,
        **{key: value for key, value in identity.items() if key != "service_pids"},
        "generation": "generation-test",
        "control_url": control.url,
        "ports": {"web": 54320},
        "media_descriptor": str(media),
        "services": {"media": {"pid": 43211}},
    }
    (tmp_path / "runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / ".runtime-control.json").write_text(
        json.dumps(
            {"runtime_id": "runtime-test", "control_url": control.url, "secret": "secret-test"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "poc.xiaojudeng_sandbox_runtime.launcher.process_exists", lambda _pid: False
    )
    monkeypatch.setattr("poc.xiaojudeng_sandbox_runtime.launcher.port_is_free", lambda _port: True)
    try:
        receipt = stop_runtime(tmp_path)
    finally:
        control.close()

    assert control.stop_event.is_set()
    assert receipt["status"] == "STOPPED"
    assert receipt["service_pids"] == {"media": 43211}
    assert receipt["released_ports"] == [54320, 54321]


def test_stop_runtime_rejects_unverified_manifest(tmp_path: Path) -> None:
    (tmp_path / "runtime.json").write_text(
        json.dumps({"source": "production", "fixture_only": False, "external_effect": True}),
        encoding="utf-8",
    )
    (tmp_path / ".runtime-control.json").write_text(
        json.dumps({"runtime_id": "bad", "control_url": "http://127.0.0.1:1", "secret": "bad"}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="unverified runtime"):
        stop_runtime(tmp_path)


def test_stop_runtime_rejects_dead_launcher_with_live_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "media.json"
    media.write_text(json.dumps({"control_url": "http://127.0.0.1:54321/control/live"}))
    manifest = {
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
        "external_effect": False,
        "runtime_id": "runtime-test",
        "launcher_pid": 43210,
        "started_at": "2026-09-03T00:00:00+00:00",
        "executable": str(Path(sys.executable).resolve()),
        "runtime_dir": str(tmp_path.resolve()),
        "generation": "generation-test",
        "control_url": "http://127.0.0.1:1",
        "ports": {"web": 54320},
        "media_descriptor": str(media),
        "services": {"media": {"pid": 43211}},
    }
    (tmp_path / "runtime.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / ".runtime-control.json").write_text(
        json.dumps(
            {"runtime_id": "runtime-test", "control_url": "http://127.0.0.1:1", "secret": "x"}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "poc.xiaojudeng_sandbox_runtime.launcher.process_exists",
        lambda process_id: process_id == 43211,
    )

    with pytest.raises(RuntimeError, match="resources remain"):
        stop_runtime(tmp_path)


def test_dynamic_ports_and_explicit_overrides_are_valid() -> None:
    ports = dynamic_ports()

    assert set(ports) == set(DEFAULT_PORTS)
    assert len(set(ports.values())) == len(ports)
    assert parse_port_overrides(["web=43192", "control=45300"]) == {
        "web": 43192,
        "control": 45300,
    }
    with pytest.raises(ValueError, match="invalid port override"):
        parse_port_overrides(["unknown=1234"])
