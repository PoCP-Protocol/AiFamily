"""One-command launcher for the synthetic Xiao Ju Deng live platform sandbox."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEFAULT_PORTS = {
    "interaction": 55200,
    "control": 55300,
    "replay": 55303,
    "knowledge": 55304,
    "ai": 55305,
    "incident": 55306,
    "commerce": 55400,
    "observability": 55500,
    "web": 4192,
}
RUNTIME_SESSION_REF = "live.synthetic.runtime.1"


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    command: tuple[str, ...]
    cwd: Path
    health_url: str | None


@dataclass(frozen=True)
class RuntimeEvidence:
    source: str
    fixture_only: bool
    external_effect: bool
    launcher_pid: int
    runtime_dir: str
    web_url: str
    media_descriptor: str
    services: dict[str, dict[str, object]]


def assert_ports_available(ports: dict[str, int]) -> None:
    conflicts: list[str] = []
    for name, port in ports.items():
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                conflicts.append(f"{name}:{port}")
    if conflicts:
        raise RuntimeError(f"sandbox ports already in use: {', '.join(conflicts)}")


def build_service_specs(
    repo_root: Path,
    runtime_dir: Path,
    ports: dict[str, int],
    media_descriptor: Path,
    media_path: Path,
) -> list[ServiceSpec]:
    python = sys.executable
    url = lambda name: f"http://127.0.0.1:{ports[name]}"  # noqa: E731
    database = lambda name: str(runtime_dir / f"{name}.sqlite3")  # noqa: E731
    return [
        ServiceSpec(
            "media",
            (
                python,
                "-m",
                "poc.media_adapter_sandbox.replay_harness",
                "--serve",
                "--output",
                str(media_path),
                "--descriptor",
                str(media_descriptor),
                "--session-ref",
                RUNTIME_SESSION_REF,
                "--duration",
                "30",
                "--ttl",
                "60",
            ),
            repo_root,
            None,
        ),
        ServiceSpec(
            "control",
            (
                python,
                "-m",
                "poc.standalone_live_control_sandbox.session_api",
                "--serve",
                "--database",
                database("control"),
                "--port",
                str(ports["control"]),
                "--enable-synthetic-consent",
            ),
            repo_root,
            f"{url('control')}/health",
        ),
        ServiceSpec(
            "interaction",
            (
                python,
                "-m",
                "poc.standalone_live_moderation_sandbox.question_api",
                "--serve",
                "--database",
                database("interaction"),
                "--port",
                str(ports["interaction"]),
            ),
            repo_root,
            f"{url('interaction')}/health",
        ),
        ServiceSpec(
            "commerce",
            (
                python,
                "-m",
                "poc.standalone_live_commerce_sandbox.commerce_api",
                "--serve",
                "--database",
                database("commerce"),
                "--port",
                str(ports["commerce"]),
            ),
            repo_root,
            f"{url('commerce')}/health",
        ),
        ServiceSpec(
            "replay",
            (
                python,
                "-m",
                "poc.standalone_live_replay_sandbox.replay_api",
                "--serve",
                "--database",
                database("replay"),
                "--media",
                str(media_path),
                "--port",
                str(ports["replay"]),
                "--commerce-base-url",
                url("commerce"),
            ),
            repo_root,
            f"{url('replay')}/health",
        ),
        ServiceSpec(
            "knowledge",
            (
                python,
                "-m",
                "poc.standalone_live_replay_sandbox.knowledge_api",
                "--serve",
                "--database",
                database("knowledge"),
                "--replay-database",
                database("replay"),
                "--seed-approved-fixture",
                "--port",
                str(ports["knowledge"]),
            ),
            repo_root,
            f"{url('knowledge')}/health",
        ),
        ServiceSpec(
            "ai",
            (
                python,
                "-m",
                "poc.standalone_live_ai_sandbox.ai_api",
                "--serve",
                "--database",
                database("ai"),
                "--port",
                str(ports["ai"]),
            ),
            repo_root,
            f"{url('ai')}/health",
        ),
        ServiceSpec(
            "incident",
            (
                python,
                "-m",
                "poc.standalone_live_moderation_sandbox.incident_api",
                "--serve",
                "--database",
                database("incident"),
                "--port",
                str(ports["incident"]),
                "--control-base-url",
                url("control"),
            ),
            repo_root,
            f"{url('incident')}/health",
        ),
    ]


def wait_for_file(path: Path, timeout_seconds: float = 15) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size:
            return
        time.sleep(0.1)
    raise RuntimeError(f"sandbox artifact was not created: {path}")


def wait_for_health(url: str, timeout_seconds: float = 15) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    payload = json.loads(response.read())
                    if payload.get("fixture_only") is not True:
                        raise RuntimeError(f"unsafe health evidence from {url}")
                    return payload
        except Exception as exc:  # noqa: BLE001 - retry boundary records final cause
            last_error = exc
        time.sleep(0.15)
    raise RuntimeError(f"sandbox health check failed for {url}: {last_error}")


def wait_for_http(url: str, timeout_seconds: float = 15) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 - retry boundary records final cause
            last_error = exc
        time.sleep(0.15)
    raise RuntimeError(f"sandbox HTTP check failed for {url}: {last_error}")


def seed_live_session(control_base_url: str) -> dict[str, object]:
    now = datetime.now(UTC)
    headers = {
        "Content-Type": "application/json",
        "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
        "X-Fixture-Only": "true",
        "X-Tenant-Id": "tenant.synthetic.alpha",
        "X-Family-Id": "family.synthetic.alpha",
    }

    def post(path: str, role: str, actor: str, payload: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            f"{control_base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={**headers, "X-Actor-Id": actor, "X-Actor-Role": role},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read())

    session_ref = RUNTIME_SESSION_REF
    post(
        "/sandbox/live-control/sessions",
        "CREATOR",
        "actor.synthetic.creator",
        {
            "session_ref": session_ref,
            "idempotency_key": "runtime-create-live-1",
            "title": "小橘灯：家庭沟通中的温柔练习",
            "speaker": "小橘灯老师",
            "expert_summary": "围绕家庭沟通中的真实场景，练习先听懂、再回应。",
            "applicable_scope": "家长与照护者",
            "problem_tags": ["家庭沟通", "照护者"],
            "starts_at": (now - timedelta(minutes=5)).isoformat(),
            "ends_at": (now + timedelta(hours=1)).isoformat(),
            "audience_scope": "FAMILY",
        },
    )
    post(
        f"/sandbox/live-control/sessions/{session_ref}/review",
        "CONTENT_REVIEWER",
        "actor.synthetic.content_reviewer",
        {
            "decision_key": "runtime-review-live-1",
            "action": "APPROVE",
            "reason": "人工确认合成内容适合成年家庭成员",
            "review_ref": "review.synthetic.runtime.1",
        },
    )
    return post(
        f"/sandbox/live-control/sessions/{session_ref}/lifecycle",
        "LIVE_OPERATOR",
        "actor.synthetic.live_operator",
        {
            "action_key": "runtime-go-live-1",
            "action": "GO_LIVE",
            "reason": "启动可销毁的小橘灯完整 Sandbox",
        },
    )


def web_environment(ports: dict[str, int], media: dict[str, object]) -> dict[str, str]:
    base = lambda name: f"http://127.0.0.1:{ports[name]}"  # noqa: E731
    return {
        "VITE_MEDIA_PLAYBACK_DTO": json.dumps(media, separators=(",", ":")),
        "VITE_LIVE_INTERACTION_BASE_URL": base("interaction"),
        "VITE_LIVE_INTERACTION_WS_URL": f"ws://127.0.0.1:{ports['interaction']}",
        "VITE_LIVE_REPLAY_BASE_URL": base("replay"),
        "VITE_LIVE_REPLAY_KNOWLEDGE_BASE_URL": base("knowledge"),
        "VITE_LIVE_COMMERCE_BASE_URL": base("commerce"),
        "VITE_LIVE_OBSERVABILITY_BASE_URL": base("observability"),
        "VITE_LIVE_CONTROL_BASE_URL": base("control"),
        "VITE_LIVE_AI_BASE_URL": base("ai"),
        "VITE_LIVE_INCIDENT_BASE_URL": base("incident"),
    }


def terminate(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ("taskkill", "/PID", str(process.pid), "/T", "/F"),
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                process.terminate()
    for process in reversed(processes):
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def stop_runtime(runtime_dir: Path) -> dict[str, object]:
    manifest_path = runtime_dir / "runtime.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"sandbox runtime manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("source") != "SANDBOX_SYNTHETIC"
        or manifest.get("fixture_only") is not True
        or manifest.get("external_effect") is not False
    ):
        raise RuntimeError("refusing to stop an unverified runtime")
    launcher_pid = manifest.get("launcher_pid")
    if not isinstance(launcher_pid, int) or launcher_pid <= 0 or launcher_pid == os.getpid():
        raise RuntimeError("sandbox launcher pid is invalid")
    if os.name == "nt":
        result = subprocess.run(
            ("taskkill", "/PID", str(launcher_pid), "/T", "/F"),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode not in {0, 128}:
            raise RuntimeError(f"sandbox stop failed: {result.stderr.strip()}")
    else:
        with suppress(ProcessLookupError):
            os.kill(launcher_pid, signal.SIGTERM)
    receipt = {
        "source": "SANDBOX_SYNTHETIC",
        "fixture_only": True,
        "external_effect": False,
        "launcher_pid": launcher_pid,
        "stopped_at": datetime.now(UTC).isoformat(),
    }
    (runtime_dir / "stopped.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8"
    )
    return receipt


def run(runtime_dir: Path, ports: dict[str, int]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    runtime_dir.mkdir(parents=True, exist_ok=True)
    assert_ports_available(ports)
    media_descriptor = runtime_dir / "media.json"
    media_path = runtime_dir / "live.web-compatible.mp4"
    specs = build_service_specs(repo_root, runtime_dir, ports, media_descriptor, media_path)
    processes: list[subprocess.Popen[bytes]] = []
    logs: list[object] = []
    evidence: dict[str, dict[str, object]] = {}
    try:
        for spec in specs:
            log = (runtime_dir / f"{spec.name}.log").open("ab")
            logs.append(log)
            process = subprocess.Popen(spec.command, cwd=spec.cwd, stdout=log, stderr=log)
            processes.append(process)
            if spec.name == "media":
                wait_for_file(media_descriptor)
                media = json.loads(media_descriptor.read_text(encoding="utf-8"))
                evidence[spec.name] = {
                    "pid": process.pid,
                    "health": {"source": media["source"], "fixture_only": media["fixture_only"]},
                }
            elif spec.health_url:
                evidence[spec.name] = {
                    "pid": process.pid,
                    "health": wait_for_health(spec.health_url),
                }
                if spec.name == "control":
                    evidence[spec.name]["seed"] = seed_live_session(
                        f"http://127.0.0.1:{ports['control']}"
                    )

        media = json.loads(media_descriptor.read_text(encoding="utf-8"))
        observability = ServiceSpec(
            "observability",
            (
                sys.executable,
                "-m",
                "poc.standalone_live_observability_sandbox.health_api",
                "--media-url",
                str(media["control_url"]),
                "--interaction-url",
                f"http://127.0.0.1:{ports['interaction']}",
                "--replay-url",
                f"http://127.0.0.1:{ports['replay']}",
                "--commerce-url",
                f"http://127.0.0.1:{ports['commerce']}",
                "--port",
                str(ports["observability"]),
            ),
            repo_root,
            f"http://127.0.0.1:{ports['observability']}/health",
        )
        log = (runtime_dir / "observability.log").open("ab")
        logs.append(log)
        process = subprocess.Popen(observability.command, cwd=repo_root, stdout=log, stderr=log)
        processes.append(process)
        evidence[observability.name] = {
            "pid": process.pid,
            "health": wait_for_health(observability.health_url),
        }

        env = {**os.environ, **web_environment(ports, media)}
        web_log = (runtime_dir / "web.log").open("ab")
        logs.append(web_log)
        web_command = (
            "pnpm.cmd" if os.name == "nt" else "pnpm",
            "dev",
            "--host",
            "127.0.0.1",
            "--port",
            str(ports["web"]),
        )
        web = subprocess.Popen(
            web_command, cwd=repo_root / "frontend" / "web", env=env, stdout=web_log, stderr=web_log
        )
        processes.append(web)
        wait_for_http(f"http://127.0.0.1:{ports['web']}/")
        evidence["web"] = {
            "pid": web.pid,
            "health": {"fixture_only": True, "source": "SANDBOX_SYNTHETIC"},
        }

        runtime = RuntimeEvidence(
            source="SANDBOX_SYNTHETIC",
            fixture_only=True,
            external_effect=False,
            launcher_pid=os.getpid(),
            runtime_dir=str(runtime_dir.resolve()),
            web_url=f"http://127.0.0.1:{ports['web']}/#live-home",
            media_descriptor=str(media_descriptor.resolve()),
            services=evidence,
        )
        (runtime_dir / "runtime.json").write_text(
            json.dumps(asdict(runtime), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(json.dumps(asdict(runtime), ensure_ascii=False, sort_keys=True), flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        failed = next(process for process in processes if process.poll() is not None)
        raise RuntimeError(
            f"sandbox process exited unexpectedly: pid={failed.pid} code={failed.returncode}"
        )
    except KeyboardInterrupt:
        return 0
    finally:
        terminate(processes)
        for log in logs:
            log.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the complete synthetic Xiao Ju Deng sandbox")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--runtime-dir", type=Path)
    args = parser.parse_args()
    if args.stop:
        if args.runtime_dir is None:
            raise SystemExit("--stop requires --runtime-dir")
        print(json.dumps(stop_runtime(args.runtime_dir), sort_keys=True))
        return 0
    if not args.serve:
        raise SystemExit("use --serve or --stop")
    runtime_dir = args.runtime_dir or Path(tempfile.mkdtemp(prefix="xiaojudeng-runtime-"))
    return run(runtime_dir, DEFAULT_PORTS)


if __name__ == "__main__":
    raise SystemExit(main())
