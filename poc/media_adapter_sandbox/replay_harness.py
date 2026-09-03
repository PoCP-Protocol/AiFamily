"""Executable synthetic video producer, MediaAdapter, and sandbox player."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from poc.media_adapter_sandbox.contract import (
    CapabilityAuthority,
    CapabilityError,
    FaultKind,
    MediaAdapter,
    MediaSession,
    MediaState,
    PlaybackCapability,
    ProviderFailure,
    SyntheticSource,
)
from poc.media_adapter_sandbox.fake_provider import FakeMediaProvider
from poc.media_adapter_sandbox.fault_injector import FaultInjector


class SyntheticVideoFactory:
    """Create a real MP4 with ffmpeg; absence/failure is explicit, never a fallback."""

    @staticmethod
    def create(output: Path, duration_seconds: float = 2.0) -> Path:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg is required for the playable synthetic artifact")
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size=320x180:rate=15:duration={duration_seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration_seconds}",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {completed.stderr.strip()}")
        if not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("ffmpeg returned without a playable artifact")
        return output

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


class SyntheticMediaAdapter:
    def __init__(
        self,
        provider: FakeMediaProvider | None = None,
        authority: CapabilityAuthority | None = None,
        faults: FaultInjector | None = None,
        media_session_ref: str | None = None,
    ) -> None:
        self.faults = faults or FaultInjector()
        self.provider = provider or FakeMediaProvider(self.faults)
        self.authority = authority or CapabilityAuthority()
        self.sessions: dict[str, MediaSession] = {}
        self.admission_open = True
        self.media_session_ref = media_session_ref

    def start(self, source: SyntheticSource, family_ref: str) -> MediaSession:
        if not self.admission_open or self.faults.enabled(FaultKind.STOP_SWITCH):
            raise ProviderFailure("media admission stopped by stop switch")
        source.validate()
        media_session_ref = self.media_session_ref or f"media.synthetic.{len(self.sessions) + 1}"
        if media_session_ref in self.sessions:
            raise ValueError(f"duplicate media session: {media_session_ref}")
        session = MediaSession(
            media_session_ref=media_session_ref,
            family_ref=family_ref,
            source=source,
        )
        self.sessions[media_session_ref] = session
        try:
            handle = self.provider.ingest(media_session_ref, source)
        except Exception:
            session.transition(MediaState.FAILED)
            raise
        session.provider_ref = handle.provider_ref
        session.transition(MediaState.LIVE)
        return session

    def _session(self, media_session_ref: str) -> MediaSession:
        try:
            return self.sessions[media_session_ref]
        except KeyError as exc:
            raise KeyError(f"unknown media session: {media_session_ref}") from exc

    def playback_capability(
        self, media_session_ref: str, family_ref: str, ttl_seconds: int = 15
    ) -> PlaybackCapability:
        session = self._session(media_session_ref)
        if session.family_ref != family_ref:
            raise PermissionError("cross-family playback denied")
        if session.state not in {MediaState.LIVE, MediaState.ENDED}:
            raise PermissionError(f"playback unavailable in {session.state.value}")
        return self.authority.issue(media_session_ref, family_ref, ttl_seconds)

    def playback_bytes(self, capability_token: str) -> bytes:
        claims = self.authority.inspect(capability_token)
        session = self._session(str(claims["media_session_ref"]))
        self.authority.verify(
            capability_token,
            session.media_session_ref,
            session.family_ref,
            consume=True,
        )
        if session.state in {MediaState.STOPPED, MediaState.REVOKED, MediaState.FAILED}:
            raise PermissionError(f"playback unavailable in {session.state.value}")
        return self.provider.media_bytes(session.media_session_ref)

    def disconnect(self, media_session_ref: str) -> None:
        session = self._session(media_session_ref)
        if session.state != MediaState.LIVE:
            raise RuntimeError(f"disconnect requires LIVE, got {session.state.value}")
        session.transition(MediaState.DISCONNECTED)

    def reconnect(self, media_session_ref: str) -> None:
        session = self._session(media_session_ref)
        if session.state != MediaState.DISCONNECTED:
            raise RuntimeError(f"reconnect requires DISCONNECTED, got {session.state.value}")
        session.transition(MediaState.RESTARTED)
        session.transition(MediaState.LIVE)

    def end(self, media_session_ref: str) -> None:
        self._session(media_session_ref).transition(MediaState.ENDED)

    def stop(self, media_session_ref: str) -> None:
        session = self._session(media_session_ref)
        stoppable_states = {
            MediaState.LIVE,
            MediaState.DISCONNECTED,
            MediaState.RESTARTED,
            MediaState.ENDED,
        }
        if session.state not in stoppable_states:
            return
        session.transition(MediaState.STOPPED)

    def revoke(self, media_session_ref: str) -> None:
        session = self._session(media_session_ref)
        self.authority.revoke_session(media_session_ref)
        if session.state not in {MediaState.STOPPED, MediaState.REVOKED}:
            session.transition(MediaState.REVOKED)

    def stop_switch(self) -> None:
        self.admission_open = False
        self.faults.inject(FaultKind.STOP_SWITCH)
        for session in self.sessions.values():
            self.stop(session.media_session_ref)

    def playback_url(self, server: SandboxPlayerServer, capability: PlaybackCapability) -> str:
        query = urllib.parse.urlencode({"token": capability.token})
        return f"{server.base_url}/media/{capability.media_session_ref}.mp4?{query}"


class _PlayerHandler(BaseHTTPRequestHandler):
    adapter: SyntheticMediaAdapter
    server_ref: SandboxPlayerServer

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        allowed_origin = self._allowed_origin()
        if allowed_origin is not None:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib handler contract
        allowed_origin = self._allowed_origin()
        if allowed_origin is None:
            self._send(403, b"local browser origin required", "text/plain; charset=utf-8")
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", allowed_origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _allowed_origin(self) -> str | None:
        origin = self.headers.get("Origin")
        if origin is None:
            return None
        parsed = urllib.parse.urlparse(origin)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            return None
        if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
            return None
        return origin

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        token = query.get("token", [""])[0]
        if parsed.path.startswith("/player/"):
            session_ref = parsed.path.removeprefix("/player/")
            body = (
                "<!doctype html><meta charset='utf-8'><title>synthetic media player</title>"
                f"<h1>{session_ref}</h1><video controls autoplay playsinline width='640' "
                f"src='/media/{session_ref}.mp4?token={urllib.parse.quote(token)}'></video>"
            ).encode()
            self._send(200, body, "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/media/"):
            session_ref = parsed.path.removeprefix("/media/").removesuffix(".mp4")
            try:
                claims = self.adapter.authority.inspect(token)
                if claims["media_session_ref"] != session_ref:
                    raise CapabilityError("media path and capability mismatch")
                body = self.adapter.playback_bytes(token)
            except (CapabilityError, PermissionError, KeyError) as exc:
                self._send(403, str(exc).encode("utf-8"), "text/plain; charset=utf-8")
                return
            self._send(200, body, "video/mp4")
            return
        if parsed.path == "/health":
            self._send(200, b'{"source":"synthetic","fixture_only":true}', "application/json")
            return
        self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        parsed = urllib.parse.urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "control":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        _, session_ref, action = parts
        try:
            if action == "refresh":
                session = self.adapter._session(session_ref)
                capability = self.adapter.playback_capability(
                    session.media_session_ref, session.family_ref, ttl_seconds=60
                )
                payload = {
                    "state": session.state.value,
                    "playback_url": self.adapter.playback_url(self.server_ref, capability),
                }
                self._send(
                    200,
                    json.dumps(payload).encode("utf-8"),
                    "application/json",
                )
                return
            if action == "disconnect":
                self.adapter.disconnect(session_ref)
            elif action == "recover":
                self.adapter.reconnect(session_ref)
            elif action == "stop":
                self.adapter.stop(session_ref)
            elif action == "revoke":
                self.adapter.revoke(session_ref)
            else:
                self._send(404, b"unknown action", "text/plain; charset=utf-8")
                return
            session = self.adapter._session(session_ref)
            payload: dict[str, object] = {
                "state": "REVOKED" if action == "revoke" else session.state.value
            }
            if action == "recover":
                capability = self.adapter.playback_capability(
                    session.media_session_ref, session.family_ref, ttl_seconds=60
                )
                payload["playback_url"] = self.adapter.playback_url(self.server_ref, capability)
            self._send(
                200,
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        except (CapabilityError, PermissionError, KeyError, RuntimeError) as exc:
            self._send(409, str(exc).encode("utf-8"), "text/plain; charset=utf-8")

    def log_message(self, _format: str, *_args: object) -> None:
        return


class SandboxPlayerServer:
    def __init__(self, adapter: SyntheticMediaAdapter) -> None:
        self.adapter = adapter
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self.httpd is None:
            raise RuntimeError("sandbox player server is not running")
        host, port = self.httpd.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> SandboxPlayerServer:
        adapter = self.adapter

        class Handler(_PlayerHandler):
            pass

        Handler.adapter = adapter
        Handler.server_ref = self
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def player_url(self, capability: PlaybackCapability) -> str:
        query = urllib.parse.urlencode({"token": capability.token})
        return f"{self.base_url}/player/{capability.media_session_ref}?{query}"


@contextmanager
def temporary_artifact(duration_seconds: float = 2.0) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="media-sandbox-") as directory:
        yield SyntheticVideoFactory.create(Path(directory) / "synthetic.mp4", duration_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the synthetic MediaAdapter sandbox player")
    parser.add_argument("--serve", action="store_true", help="keep the local player server running")
    parser.add_argument("--output", type=Path, help="write the synthetic MP4 at this path")
    parser.add_argument("--descriptor", type=Path, help="write the sandbox playback DTO as JSON")
    parser.add_argument(
        "--session-ref", help="bind the media capability to a synthetic live session"
    )
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument(
        "--ttl", type=int, default=30, help="playback capability TTL in seconds (max 60)"
    )
    args = parser.parse_args()

    output = args.output or Path(tempfile.mkdtemp(prefix="media-sandbox-")) / "synthetic.mp4"
    artifact = SyntheticVideoFactory.create(output, args.duration)
    source = SyntheticSource(artifact)
    if args.session_ref is not None and not args.session_ref.startswith("live.synthetic."):
        raise SystemExit("--session-ref must use the live.synthetic.* namespace")
    adapter: MediaAdapter = SyntheticMediaAdapter(media_session_ref=args.session_ref)
    session = adapter.start(source, family_ref="family.synthetic.alpha")
    capability = adapter.playback_capability(
        session.media_session_ref,
        session.family_ref,
        ttl_seconds=args.ttl,
    )
    with SandboxPlayerServer(adapter) as server:
        payload = {
            "source": "synthetic",
            "fixture_only": True,
            "state": session.state.value,
            "media_session_ref": session.media_session_ref,
            "artifact": str(artifact.resolve()),
            "sha256": SyntheticVideoFactory.sha256(artifact),
            "player_url": server.player_url(capability),
            "playback_url": adapter.playback_url(server, capability),
            "control_url": f"{server.base_url}/control/{session.media_session_ref}",
        }
        if args.descriptor is not None:
            args.descriptor.parent.mkdir(parents=True, exist_ok=True)
            args.descriptor.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        print(json.dumps(payload, sort_keys=True))
        if args.serve:
            print("Press Ctrl-C to stop the sandbox player.", flush=True)
            with suppress(KeyboardInterrupt):
                threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
