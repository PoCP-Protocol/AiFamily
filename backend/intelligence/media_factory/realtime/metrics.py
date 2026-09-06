"""Realtime avatar metrics schema (ADR-0019 §Metrics).

Two sentinel values, and they mean different things:

* ``NOT_RUN``  — the measurement was never attempted (no session, no GPU node).
* ``UNKNOWN``  — it was attempted but the value is genuinely unavailable (a
  remote node that reports frames but not its VRAM usage).

Neither may ever be replaced by a plausible-looking number. The default for
every field is ``NOT_RUN``, so a metrics object nobody filled in reads as
"nothing was measured" rather than as zeros — a benchmark table of zeros is
indistinguishable from a benchmark table of measurements at a glance, and that
is precisely the confusion this schema exists to prevent.

`source` is mandatory alongside the numbers: wall-clock timings taken from the
fixture provider are real timings *of a fake generator*, and a reader must be
able to tell them apart from timings of neural inference without reading code.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any, Literal

from backend.intelligence.media_factory.realtime.contracts import RealtimeAvatarError

NOT_RUN = "NOT_RUN"
UNKNOWN = "UNKNOWN"

MetricSentinel = Literal["NOT_RUN", "UNKNOWN"]
MetricValue = float | int | MetricSentinel

REALTIME_METRICS_SCHEMA = "FAMILI_REALTIME_AVATAR_METRICS_V0"

MetricSource = Literal[
    "NOT_RUN",
    "FIXTURE_SYNTHETIC",
    "REMOTE_GPU_NODE_ATTESTED",
    "REMOTE_TRANSPORT_UNATTESTED",
    "LOCAL_GPU",
]

_MEASURED_SOURCES: frozenset[str] = frozenset(
    {"FIXTURE_SYNTHETIC", "REMOTE_GPU_NODE_ATTESTED", "REMOTE_TRANSPORT_UNATTESTED", "LOCAL_GPU"}
)


@dataclass(frozen=True, slots=True)
class RealtimeMetrics:
    """The realtime metric set. Absent measurements stay absent."""

    identity_prepare_ms: MetricValue = NOT_RUN
    audio_chunk_to_motion_ms: MetricValue = NOT_RUN
    first_frame_latency_ms: MetricValue = NOT_RUN
    frame_interval_ms: MetricValue = NOT_RUN
    effective_fps: MetricValue = NOT_RUN
    dropped_frames: MetricValue = NOT_RUN
    queue_depth: MetricValue = NOT_RUN
    gpu_memory_mb: MetricValue = NOT_RUN
    source: MetricSource = NOT_RUN
    real_neural_inference: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        for f in fields(self):
            if f.name in {"source", "real_neural_inference", "note"}:
                continue
            value = getattr(self, f.name)
            if isinstance(value, str):
                if value not in {NOT_RUN, UNKNOWN}:
                    raise RealtimeAvatarError(
                        f"{f.name} must be a number or one of {NOT_RUN}/{UNKNOWN}, got {value!r}"
                    )
                continue
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise RealtimeAvatarError(f"{f.name} must be numeric or a sentinel, got {value!r}")
            if value < 0:
                raise RealtimeAvatarError(f"{f.name} must be >= 0, got {value!r}")

    @property
    def measured(self) -> bool:
        return self.source in _MEASURED_SOURCES

    @property
    def realtime_gate_eligible(self) -> bool:
        """Only attested real neural inference can support a realtime gate claim."""
        return self.real_neural_inference and self.source == "REMOTE_GPU_NODE_ATTESTED"

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema": REALTIME_METRICS_SCHEMA,
            "source": self.source,
            "measured": self.measured,
            "real_neural_inference": self.real_neural_inference,
            "realtime_gate_eligible": self.realtime_gate_eligible,
            "identity_prepare_ms": self.identity_prepare_ms,
            "audio_chunk_to_motion_ms": self.audio_chunk_to_motion_ms,
            "first_frame_latency_ms": self.first_frame_latency_ms,
            "frame_interval_ms": self.frame_interval_ms,
            "effective_fps": self.effective_fps,
            "dropped_frames": self.dropped_frames,
            "queue_depth": self.queue_depth,
            "gpu_memory_mb": self.gpu_memory_mb,
            "note": self.note,
        }


def not_run_metrics(*, note: str = "") -> RealtimeMetrics:
    """The honest answer when nothing has been measured."""
    return RealtimeMetrics(source=NOT_RUN, note=note)


class RealtimeMetricsRecorder:
    """Accumulates observations for one session and derives the metric set.

    Derived rather than declared: `effective_fps` comes from the frames actually
    handed out and the wall-clock span they covered, so it cannot be set to a
    number nobody observed. If fewer than two frames were emitted there is no
    interval to speak of and the interval-based fields stay ``UNKNOWN``.
    """

    def __init__(
        self,
        *,
        source: MetricSource,
        real_neural_inference: bool,
        clock: Callable[[], float] | None = None,
        note: str = "",
    ) -> None:
        self.source = source
        self.real_neural_inference = real_neural_inference
        self.note = note
        self._clock = clock or time.monotonic
        self._identity_prepare_ms: float | None = None
        self._turn_started_at: float | None = None
        self._first_frame_at: float | None = None
        self._last_audio_at: float | None = None
        self._audio_to_motion_ms: list[float] = []
        self._frame_times: list[float] = []
        self._dropped_frames = 0
        self._queue_depth = 0
        self._gpu_memory_mb: float | None = None

    def now(self) -> float:
        return self._clock()

    def record_identity_prepare(self, elapsed_ms: float) -> None:
        self._identity_prepare_ms = max(0.0, elapsed_ms)

    def start_turn(self) -> None:
        self._turn_started_at = self._clock()
        self._first_frame_at = None
        self._last_audio_at = None
        self._frame_times = []

    def record_audio_chunk(self) -> None:
        self._last_audio_at = self._clock()

    def record_motion_ready(self) -> None:
        """Close the audio-chunk-to-motion interval opened by the last chunk."""
        if self._last_audio_at is None:
            return
        self._audio_to_motion_ms.append((self._clock() - self._last_audio_at) * 1000.0)

    def record_frame(self) -> None:
        stamp = self._clock()
        self._frame_times.append(stamp)
        if self._first_frame_at is None:
            self._first_frame_at = stamp

    def record_dropped_frame(self, count: int = 1) -> None:
        self._dropped_frames += count

    def set_queue_depth(self, depth: int) -> None:
        self._queue_depth = max(0, depth)

    def set_gpu_memory_mb(self, value: float | None) -> None:
        self._gpu_memory_mb = value

    def snapshot(self) -> RealtimeMetrics:
        first_frame_latency: MetricValue = UNKNOWN
        if self._turn_started_at is not None and self._first_frame_at is not None:
            first_frame_latency = round((self._first_frame_at - self._turn_started_at) * 1000.0, 3)

        frame_interval: MetricValue = UNKNOWN
        effective_fps: MetricValue = UNKNOWN
        if len(self._frame_times) >= 2:
            span = self._frame_times[-1] - self._frame_times[0]
            intervals = len(self._frame_times) - 1
            frame_interval = round(span * 1000.0 / intervals, 3)
            effective_fps = round(intervals / span, 3) if span > 0 else UNKNOWN

        audio_to_motion: MetricValue = UNKNOWN
        if self._audio_to_motion_ms:
            audio_to_motion = round(
                sum(self._audio_to_motion_ms) / len(self._audio_to_motion_ms), 3
            )

        prepare_ms: MetricValue = UNKNOWN
        if self._identity_prepare_ms is not None:
            prepare_ms = round(self._identity_prepare_ms, 3)

        return RealtimeMetrics(
            identity_prepare_ms=prepare_ms,
            audio_chunk_to_motion_ms=audio_to_motion,
            first_frame_latency_ms=first_frame_latency,
            frame_interval_ms=frame_interval,
            effective_fps=effective_fps,
            dropped_frames=self._dropped_frames,
            queue_depth=self._queue_depth,
            gpu_memory_mb=UNKNOWN if self._gpu_memory_mb is None else self._gpu_memory_mb,
            source=self.source,
            real_neural_inference=self.real_neural_inference,
            note=self.note,
        )
