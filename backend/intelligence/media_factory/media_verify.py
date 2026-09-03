"""Output media verification for Gate1 avatar artifacts.

Fail-closed: process exit code alone is never enough. Static single-frame+audio
mux must be flagged as STATIC_VIDEO_SUSPECTED (not a full visual quality score).
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.intelligence.media_factory.contracts import MediaFactoryError, sha256_file

# Sensible minimum for a short talking-head clip (bytes).
MIN_MP4_BYTES = 8_000


@dataclass(frozen=True, slots=True)
class MediaProbeResult:
    path: Path
    exists: bool
    size_bytes: int
    duration_seconds: float | None
    has_video_stream: bool
    has_audio_stream: bool
    fps: float | None
    width: int | None
    height: int | None
    frame_count: int | None
    artifact_sha256: str | None
    static_video_suspected: bool
    gate1_media_eligible: bool
    details: dict[str, Any]

    def to_manifest(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "has_video_stream": self.has_video_stream,
            "has_audio_stream": self.has_audio_stream,
            "fps": self.fps,
            "resolution": (
                {"width": self.width, "height": self.height}
                if self.width is not None and self.height is not None
                else None
            ),
            "frame_count": self.frame_count,
            "artifact_sha256": self.artifact_sha256,
            "static_video_suspected": self.static_video_suspected,
            "gate1_media_eligible": self.gate1_media_eligible,
            "details": self.details,
        }


def frames_are_static_suspect(frame_digests: list[str]) -> bool:
    """True when sampled frames are essentially identical (repeated still)."""
    if len(frame_digests) < 2:
        return True
    unique = {d for d in frame_digests if d}
    return len(unique) <= 1


def _run_ffprobe(path: Path) -> dict[str, Any]:
    if shutil.which("ffprobe") is None:
        raise MediaFactoryError("ffprobe not found; cannot verify avatar mp4")
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise MediaFactoryError(f"ffprobe failed for {path}: {(completed.stderr or '')[:500]}")
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise MediaFactoryError(f"ffprobe JSON unreadable for {path}") from exc


def _sample_frame_digests(path: Path, *, sample_count: int = 5) -> list[str]:
    """Extract evenly spaced frames via ffmpeg; hash bytes for static detection."""
    if shutil.which("ffmpeg") is None:
        return []
    work = path.parent / f".{path.stem}_frame_samples"
    work.mkdir(parents=True, exist_ok=True)
    digests: list[str] = []
    try:
        # fps filter picks ~sample_count frames across the clip when duration unknown.
        out_pattern = str(work / "frame_%02d.png")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-vf",
            f"fps={max(sample_count, 1)}/30",
            "-frames:v",
            str(sample_count),
            out_pattern,
        ]
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            return []
        frames = sorted(work.glob("frame_*.png"))
        for frame in frames[:sample_count]:
            digests.append(sha256_file(frame))
    finally:
        for leftover in work.glob("*"):
            leftover.unlink(missing_ok=True)
        if work.exists():
            with contextlib.suppress(OSError):
                work.rmdir()
    return digests


def verify_avatar_mp4(
    path: Path,
    *,
    min_bytes: int = MIN_MP4_BYTES,
    require_audio: bool = True,
    sample_static_check: bool = True,
) -> MediaProbeResult:
    path = Path(path)
    if not path.is_file():
        return MediaProbeResult(
            path=path,
            exists=False,
            size_bytes=0,
            duration_seconds=None,
            has_video_stream=False,
            has_audio_stream=False,
            fps=None,
            width=None,
            height=None,
            frame_count=None,
            artifact_sha256=None,
            static_video_suspected=True,
            gate1_media_eligible=False,
            details={"error": "file_missing"},
        )

    size = path.stat().st_size
    digest = sha256_file(path)
    probe = _run_ffprobe(path)
    streams = probe.get("streams") or []
    fmt = probe.get("format") or {}

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    has_video = len(video_streams) > 0
    has_audio = len(audio_streams) > 0

    width = height = fps = frame_count = None
    if video_streams:
        vs = video_streams[0]
        width = int(vs["width"]) if vs.get("width") is not None else None
        height = int(vs["height"]) if vs.get("height") is not None else None
        rate = vs.get("avg_frame_rate") or vs.get("r_frame_rate") or "0/1"
        if isinstance(rate, str) and "/" in rate:
            num_s, den_s = rate.split("/", 1)
            try:
                num, den = float(num_s), float(den_s)
                fps = (num / den) if den else None
            except ValueError:
                fps = None
        nb = vs.get("nb_frames")
        if nb not in (None, "N/A"):
            try:
                frame_count = int(nb)
            except ValueError:
                frame_count = None

    duration = None
    if fmt.get("duration") is not None:
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            duration = None

    static_suspected = False
    static_details: dict[str, Any] = {}
    if sample_static_check and has_video:
        digests = _sample_frame_digests(path)
        static_details["sampled_frame_count"] = len(digests)
        static_details["sampled_unique_digests"] = len(set(digests))
        if digests:
            static_suspected = frames_are_static_suspect(digests)
        elif frame_count is not None and frame_count <= 1:
            static_suspected = True
            static_details["reason"] = "frame_count_le_1"
        else:
            static_details["reason"] = "ffmpeg_sample_unavailable"

    eligible = (
        size >= min_bytes
        and has_video
        and (has_audio if require_audio else True)
        and (duration is None or duration > 0)
        and (frame_count is None or frame_count > 1)
        and not static_suspected
    )

    return MediaProbeResult(
        path=path.resolve(),
        exists=True,
        size_bytes=size,
        duration_seconds=duration,
        has_video_stream=has_video,
        has_audio_stream=has_audio,
        fps=fps,
        width=width,
        height=height,
        frame_count=frame_count,
        artifact_sha256=digest,
        static_video_suspected=static_suspected,
        gate1_media_eligible=eligible,
        details={
            "format_format_name": fmt.get("format_name"),
            "static_check": static_details,
            "min_bytes": min_bytes,
        },
    )


def require_verified_avatar_mp4(path: Path) -> MediaProbeResult:
    result = verify_avatar_mp4(path)
    if not result.exists:
        raise MediaFactoryError(f"output missing: {path}")
    if not result.has_video_stream:
        raise MediaFactoryError("output_requires_video_stream")
    if not result.has_audio_stream:
        raise MediaFactoryError("output_requires_audio_stream")
    if result.size_bytes < MIN_MP4_BYTES:
        raise MediaFactoryError(
            f"output too small ({result.size_bytes} B); not a sensible avatar mp4"
        )
    if result.duration_seconds is not None and result.duration_seconds <= 0:
        raise MediaFactoryError("output duration must be > 0")
    if result.frame_count is not None and result.frame_count <= 1:
        raise MediaFactoryError("output frame count must be > 1")
    if result.static_video_suspected:
        raise MediaFactoryError("STATIC_VIDEO_SUSPECTED: Gate1 media ineligible")
    if not result.gate1_media_eligible:
        raise MediaFactoryError("avatar mp4 failed media verification")
    return result
