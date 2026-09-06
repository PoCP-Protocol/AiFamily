"""Remote Ditto online smoke harness — prepared, never auto-executed.

What this module does locally: split the frozen smoke WAV into realtime-sized
audio chunks (20 ms / 40 ms) and build a machine-readable plan describing the
run. Both are pure functions over a local file.

What it deliberately does not do: start a cloud GPU, open an SSH connection,
download weights, or run inference. There is no subprocess and no socket in this
file, which is a property `tests/architecture/test_realtime_boundaries.py`
asserts rather than a promise in a docstring.

Until a GPU node executes the plan, the result of the smoke is exactly:

    REAL_DITTO_ONLINE_SMOKE = NOT_RUN
"""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.intelligence.media_factory.contracts import (
    CANONICAL_AUDIO_SHA256,
    CANONICAL_IDENTITY_SHA256,
    DITTO_UPSTREAM_COMMIT_PIN,
    DITTO_UPSTREAM_URL,
)
from backend.intelligence.media_factory.realtime.contracts import (
    BYTES_PER_PCM16_SAMPLE,
    REQUIRED_AUDIO_CHANNELS,
    REQUIRED_AUDIO_SAMPLE_RATE_HZ,
    AudioChunk,
    AudioChunkRejectedError,
)
from backend.intelligence.media_factory.realtime.ditto_provider import DITTO_REALTIME_ENV_VARS
from backend.intelligence.media_factory.realtime.gpu_node_boundary import (
    gpu_node_boundary_manifest,
)
from backend.intelligence.media_factory.realtime.metrics import NOT_RUN, REALTIME_METRICS_SCHEMA
from backend.intelligence.media_factory.realtime.protocol import REALTIME_PROTOCOL_VERSION

SMOKE_HARNESS_ID = "FAMILI_DITTO_REALTIME_ONLINE_SMOKE_V0"

#: The two chunk sizes the harness supports. 20 ms is the common browser
#: `AudioWorklet` frame; 40 ms halves the message rate at the cost of latency.
SUPPORTED_CHUNK_MS: tuple[int, ...] = (20, 40)

SMOKE_IDENTITY_ASSET = "FAMILI_V2_IDENTITY_MASTER_R01.png"
SMOKE_AUDIO_ASSET = "FAMILI_RDH_SMOKE_AUDIO_V0.wav"


def split_wav_to_chunks(
    wav_path: Path | str,
    *,
    session_id: str,
    turn_id: str,
    chunk_ms: int = 20,
) -> tuple[AudioChunk, ...]:
    """Split a 16 kHz mono PCM16 WAV into realtime-sized chunks.

    Refuses to resample or downmix. Silently converting the frozen smoke audio
    would break the audio hash the whole Gate chain is anchored on, so a wrong
    input format is an error, not something to fix in passing.
    """
    if chunk_ms not in SUPPORTED_CHUNK_MS:
        raise AudioChunkRejectedError(
            f"chunk_ms must be one of {SUPPORTED_CHUNK_MS}, got {chunk_ms}"
        )
    path = Path(wav_path)
    if not path.is_file():
        raise AudioChunkRejectedError(f"smoke audio missing: {path}")

    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())

    if channels != REQUIRED_AUDIO_CHANNELS:
        raise AudioChunkRejectedError(
            f"smoke audio must be mono, got {channels} channels; the harness does not downmix"
        )
    if sample_width != BYTES_PER_PCM16_SAMPLE:
        raise AudioChunkRejectedError(
            f"smoke audio must be PCM16, got {sample_width * 8}-bit samples"
        )
    if sample_rate != REQUIRED_AUDIO_SAMPLE_RATE_HZ:
        raise AudioChunkRejectedError(
            f"smoke audio must be {REQUIRED_AUDIO_SAMPLE_RATE_HZ} Hz, got {sample_rate} Hz; "
            "the harness does not resample"
        )

    bytes_per_chunk = (sample_rate * chunk_ms // 1000) * BYTES_PER_PCM16_SAMPLE
    chunks: list[AudioChunk] = []
    offsets = range(0, len(frames), bytes_per_chunk)
    for sequence, offset in enumerate(offsets):
        payload = frames[offset : offset + bytes_per_chunk]
        chunks.append(
            AudioChunk(
                session_id=session_id,
                turn_id=turn_id,
                sequence=sequence,
                presentation_time_ms=sequence * chunk_ms,
                payload=payload,
                is_final=offset + bytes_per_chunk >= len(frames),
            )
        )
    return tuple(chunks)


@dataclass(frozen=True, slots=True)
class DittoOnlineSmokeReport:
    """The result slots. Everything defaults to NOT_RUN and stays that way.

    A GPU node fills these in after executing the plan. Until then the report is
    a statement that nothing was measured — which is a usable fact, unlike a
    table of zeros.
    """

    audio_chunk_count: int | str = NOT_RUN
    chunk_ms: int | str = NOT_RUN
    first_frame: bool | str = NOT_RUN
    frame_count: int | str = NOT_RUN
    effective_fps: float | str = NOT_RUN
    first_frame_latency_ms: float | str = NOT_RUN
    total_runtime_ms: float | str = NOT_RUN
    errors: tuple[str, ...] = ()
    real_neural_inference: bool | str = NOT_RUN
    executed: bool = False
    note: str = "REAL_DITTO_ONLINE_SMOKE=NOT_RUN"

    def to_manifest(self) -> dict[str, Any]:
        return {
            "harness_id": SMOKE_HARNESS_ID,
            "metrics_schema": REALTIME_METRICS_SCHEMA,
            "executed": self.executed,
            "REAL_DITTO_ONLINE_SMOKE": "EXECUTED" if self.executed else "NOT_RUN",
            "audio_chunk_count": self.audio_chunk_count,
            "chunk_ms": self.chunk_ms,
            "first_frame": self.first_frame,
            "frame_count": self.frame_count,
            "effective_fps": self.effective_fps,
            "first_frame_latency_ms": self.first_frame_latency_ms,
            "total_runtime_ms": self.total_runtime_ms,
            "real_neural_inference": self.real_neural_inference,
            "errors": list(self.errors),
            "note": self.note,
        }


def not_run_report(*, note: str = "GPU node offline") -> DittoOnlineSmokeReport:
    return DittoOnlineSmokeReport(note=f"REAL_DITTO_ONLINE_SMOKE=NOT_RUN ({note})")


def build_ditto_online_smoke_plan(
    *,
    identity_locator: str,
    audio_locator: str,
    chunk_ms: int = 20,
    session_id: str = "smoke-session-001",
    turn_id: str = "smoke-turn-001",
) -> dict[str, Any]:
    """A runnable-by-a-human plan for the GPU node. Building it runs nothing."""
    if chunk_ms not in SUPPORTED_CHUNK_MS:
        raise AudioChunkRejectedError(
            f"chunk_ms must be one of {SUPPORTED_CHUNK_MS}, got {chunk_ms}"
        )
    return {
        "harness_id": SMOKE_HARNESS_ID,
        "protocol_version": REALTIME_PROTOCOL_VERSION,
        "purpose": (
            "Feed the frozen smoke WAV to Ditto online mode as realtime chunks and "
            "record whether progressive frames appear at all."
        ),
        "execution": {
            "auto_executed_by_agent": False,
            "requires_human_operator": True,
            "REAL_DITTO_ONLINE_SMOKE": "NOT_RUN",
        },
        "upstream": {
            "url": DITTO_UPSTREAM_URL,
            "commit_sha": DITTO_UPSTREAM_COMMIT_PIN,
            "pipeline": "stream_pipeline_online (online_mode)",
            "verified_locally": False,
            "note": (
                "The pinned source is not present on the authoring machine; the online "
                "pipeline's chunk API must be confirmed on the node before the run. See "
                "docs/13_research/technology/FAMILY_REALTIME_001_DITTO_ONLINE_AUDIT.md"
            ),
        },
        "frozen_inputs": {
            "identity": {
                "asset": SMOKE_IDENTITY_ASSET,
                "locator": identity_locator,
                "sha256": CANONICAL_IDENTITY_SHA256,
                "modifications": "FORBIDDEN",
            },
            "audio": {
                "asset": SMOKE_AUDIO_ASSET,
                "locator": audio_locator,
                "sha256": CANONICAL_AUDIO_SHA256,
                "modifications": "FORBIDDEN (no resample/denoise/re-TTS)",
                "required_format": {
                    "codec": "PCM16",
                    "sample_rate_hz": REQUIRED_AUDIO_SAMPLE_RATE_HZ,
                    "channels": REQUIRED_AUDIO_CHANNELS,
                },
            },
        },
        "chunking": {
            "chunk_ms": chunk_ms,
            "supported_chunk_ms": list(SUPPORTED_CHUNK_MS),
            "session_id": session_id,
            "turn_id": turn_id,
            "splitter": (
                "backend.intelligence.media_factory.realtime.ditto_online_smoke.split_wav_to_chunks"
            ),
            "pacing": "feed chunks at wall-clock rate; do not batch the whole file",
        },
        "engine_isolation": {
            "environment_variables": list(DITTO_REALTIME_ENV_VARS),
            "engine_in_aifamily_worktree": False,
            "weights_in_aifamily_worktree": False,
            "do_not_absorb_into_aifamily_pyproject": True,
        },
        "node_boundary": gpu_node_boundary_manifest(),
        "record_fields": [
            "audio_chunk_count",
            "chunk_ms",
            "first_frame",
            "frame_count",
            "effective_fps",
            "first_frame_latency_ms",
            "total_runtime_ms",
            "real_neural_inference",
            "errors",
        ],
        "node_side_steps": [
            "Confirm the node attests engine=ditto-talkinghead, online_mode=true, device=cuda",
            "Prepare identity once; record identity_prepare_ms",
            "Start a session; start the turn clock at the first pushed chunk",
            "Push chunks at wall-clock pace until the final chunk",
            "Record the arrival time of the first frame, then every frame interval",
            "End the turn; drain remaining frames; record total_runtime_ms",
            "Report the filled DittoOnlineSmokeReport back to AiFamily",
        ],
        "forbidden": [
            "No automatic cloud GPU start or purchase",
            "No agent-initiated SSH to a GPU node",
            "No model weight download from this repository",
            "No fabricated latency or fps numbers — unmeasured stays NOT_RUN",
            "No family, minor or business state on the GPU node",
        ],
        "report_template": not_run_report().to_manifest(),
    }
