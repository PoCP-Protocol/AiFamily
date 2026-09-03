"""DittoAvatarProvider — real neural adapter (engine stays outside the worktree).

SOURCE_CONCEPT (AUTOavantar): engine lifecycle / provenance / fail-closed IO.
REIMPLEMENTATION_NOTE: adapter + subprocess only; no Ditto tree vendoring,
no SQLite, no scheduler transplant.

Environment (isolated engine runtime — do not absorb into AiFamily pyproject):
  DITTO_ENGINE_ROOT   path to cloned antgroup/ditto-talkinghead
  DITTO_PYTHON        interpreter inside the Ditto conda/venv
  DITTO_MODEL_ROOT    checkpoints root (often <engine>/checkpoints)
  DITTO_DEVICE        optional device hint (cuda / cpu) — informational
"""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from backend.intelligence.media_factory.contracts import (
    CANONICAL_AUDIO_SHA256,
    CANONICAL_IDENTITY_SHA256,
    DITTO_CODE_LICENSE,
    DITTO_FIRST_SMOKE_BACKEND,
    DITTO_GATE1_ARTIFACT_NAME,
    DITTO_UPSTREAM_COMMIT_PIN,
    DITTO_UPSTREAM_URL,
    REAL_GATE1_ARTIFACT_NAME,
    AvatarProviderCapabilities,
    AvatarRenderRequest,
    AvatarRenderResult,
    MediaFactoryError,
    sha256_file,
)
from backend.intelligence.media_factory.gpu_gate import (
    GpuGateResult,
    GpuInfo,
    evaluate_gpu_gate,
)
from backend.intelligence.media_factory.media_verify import require_verified_avatar_mp4


class DittoAvatarProvider:
    """Offline Gate1 candidate provider for official Ditto talking-head."""

    provider_id = "ditto"

    def __init__(
        self,
        *,
        engine_root: Path | str | None = None,
        python_executable: str | None = None,
        model_root: Path | str | None = None,
        device: str | None = None,
        expected_image_sha256: str = CANONICAL_IDENTITY_SHA256,
        expected_audio_sha256: str = CANONICAL_AUDIO_SHA256,
        first_smoke_backend: str = DITTO_FIRST_SMOKE_BACKEND,
        upstream_commit: str = DITTO_UPSTREAM_COMMIT_PIN,
        provider_version: str = "0.1.0",
        gpu_probe: Callable[[], GpuInfo | None] | None = None,
        allow_conditional_vram: bool = False,
        invoke_inference: Callable[..., Path] | None = None,
    ) -> None:
        env_root = os.environ.get("DITTO_ENGINE_ROOT")
        env_py = os.environ.get("DITTO_PYTHON")
        env_model = os.environ.get("DITTO_MODEL_ROOT")
        env_device = os.environ.get("DITTO_DEVICE")

        self.engine_root = Path(engine_root or env_root or "")
        self.python_executable = python_executable or env_py or ""
        self.model_root = Path(model_root or env_model or "")
        self.device = device or env_device or "cuda"
        self.expected_image_sha256 = expected_image_sha256
        self.expected_audio_sha256 = expected_audio_sha256
        self.first_smoke_backend = first_smoke_backend
        self.upstream_commit = upstream_commit
        self.provider_version = provider_version
        self._gpu_probe = gpu_probe
        self.allow_conditional_vram = allow_conditional_vram
        self._invoke_inference = invoke_inference

    @property
    def capabilities(self) -> AvatarProviderCapabilities:
        return AvatarProviderCapabilities(
            offline_render=True,
            realtime=False,
            neural_avatar=True,
            gate1_eligible=True,
        )

    def health(self) -> dict[str, object]:
        gate = self._gpu_gate()
        engine_ok = bool(self.engine_root) and self.engine_root.is_dir()
        py_ok = bool(self.python_executable) and Path(self.python_executable).exists()
        model_ok = bool(self.model_root) and self.model_root.is_dir()
        return {
            "ok": engine_ok and py_ok and model_ok and gate.local_real_inference_allowed,
            "provider_id": self.provider_id,
            "real_neural_avatar": True,
            "gate1_eligible": True,
            "synthetic_fixture": False,
            "engine_root_configured": bool(str(self.engine_root)),
            "engine_root_exists": engine_ok,
            "python_configured": bool(self.python_executable),
            "python_exists": py_ok,
            "model_root_exists": model_ok,
            "first_smoke_backend": self.first_smoke_backend,
            "upstream_url": DITTO_UPSTREAM_URL,
            "upstream_commit_pin": self.upstream_commit,
            "code_license": DITTO_CODE_LICENSE,
            "gpu_gate": gate.to_manifest(),
        }

    def prepare(self, *, source_image: object) -> dict[str, object]:
        path = Path(str(source_image))
        if not path.is_file():
            raise MediaFactoryError(f"prepare: image missing: {path}")
        digest = sha256_file(path)
        if digest != self.expected_image_sha256:
            raise MediaFactoryError(
                f"ASSET_HASH_MISMATCH: image sha256 {digest} != {self.expected_image_sha256}"
            )
        return {
            "prepared": True,
            "source_image": str(path.resolve()),
            "image_sha256": digest,
            "preprocess": "NONE_BY_ADAPTER",
            "note": "Engine-internal crop/resize/normalize may still occur inside Ditto",
        }

    def render(self, request: AvatarRenderRequest) -> AvatarRenderResult:
        if request.output_path.name == REAL_GATE1_ARTIFACT_NAME:
            raise MediaFactoryError(
                f"ditto smoke must not claim master name {REAL_GATE1_ARTIFACT_NAME}; "
                f"use {DITTO_GATE1_ARTIFACT_NAME}"
            )

        self._assert_gpu_allows_inference()
        self._assert_engine_resolved()
        self._assert_asset_hashes(request)

        started = time.perf_counter()
        raw_out = request.output_path.parent / "_ditto_engine_raw.mp4"
        if raw_out.exists():
            raw_out.unlink()

        logs_dir = request.output_path.parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        try:
            produced = self._run_inference(request, raw_out, logs_dir)
            probe = require_verified_avatar_mp4(produced)
            if request.output_path.name != DITTO_GATE1_ARTIFACT_NAME:
                raise MediaFactoryError(
                    f"verified ditto output must be named {DITTO_GATE1_ARTIFACT_NAME}"
                )
            request.output_path.parent.mkdir(parents=True, exist_ok=True)
            if produced.resolve() != request.output_path.resolve():
                request.output_path.write_bytes(produced.read_bytes())
                if produced.exists() and produced.resolve() != request.output_path.resolve():
                    produced.unlink(missing_ok=True)
            final_digest = sha256_file(request.output_path)
            elapsed = time.perf_counter() - started
            resolution = (
                (probe.width, probe.height)
                if probe.width is not None and probe.height is not None
                else None
            )
            return AvatarRenderResult(
                artifact_path=request.output_path.resolve(),
                provider_id=self.provider_id,
                provider_version=self.provider_version,
                model="ditto-talkinghead",
                model_version=self.upstream_commit,
                provenance=self._provenance(
                    request=request,
                    inference_completed=True,
                    artifact_verified=True,
                    static_video_suspected=probe.static_video_suspected,
                    media=probe.to_manifest(),
                ),
                warnings=(),
                runtime_seconds=elapsed,
                resolution=resolution,
                fps=probe.fps,
                duration_seconds=probe.duration_seconds,
                peak_vram_mb=None,
                artifact_sha256=final_digest,
                synthetic_fixture=False,
                real_neural_avatar=True,
                gate1_eligible=True,
            )
        except MediaFactoryError:
            if request.output_path.exists():
                request.output_path.unlink(missing_ok=True)
            raise
        finally:
            if raw_out.exists() and (
                not request.output_path.exists()
                or raw_out.resolve() != request.output_path.resolve()
            ):
                raw_out.unlink(missing_ok=True)

    def _gpu_gate(self) -> GpuGateResult:
        return evaluate_gpu_gate(probe=self._gpu_probe)

    def _assert_gpu_allows_inference(self) -> None:
        gate = self._gpu_gate()
        if gate.status == "PASS" and gate.local_real_inference_allowed:
            return
        if gate.status == "CONDITIONAL" and self.allow_conditional_vram and gate.info is not None:
            # Official Ditto README does not claim <12GB; default is refuse.
            return
        raise MediaFactoryError(f"GPU_GATE_FAIL: local real inference blocked ({gate.reason})")

    def _assert_engine_resolved(self) -> None:
        if not str(self.engine_root).strip():
            raise MediaFactoryError(
                "MISSING_ENGINE_ROOT: set DITTO_ENGINE_ROOT to external ditto-talkinghead"
            )
        if not self.engine_root.is_dir():
            raise MediaFactoryError(
                f"MISSING_ENGINE_ROOT: engine path not a directory: {self.engine_root}"
            )
        inference = self.engine_root / "inference.py"
        if not inference.is_file():
            raise MediaFactoryError(
                f"MISSING_ENGINE_ROOT: inference.py not found under {self.engine_root}"
            )
        if not self.python_executable:
            raise MediaFactoryError(
                "MISSING_ENGINE_PYTHON: set DITTO_PYTHON to isolated engine interpreter"
            )
        if not Path(self.python_executable).exists():
            raise MediaFactoryError(f"MISSING_ENGINE_PYTHON: not found: {self.python_executable}")
        if not str(self.model_root).strip() or not self.model_root.is_dir():
            raise MediaFactoryError(
                "MISSING_MODEL_ROOT: set DITTO_MODEL_ROOT to external checkpoints"
            )

    def _assert_asset_hashes(self, request: AvatarRenderRequest) -> None:
        if not request.source_image.is_file() or not request.source_audio.is_file():
            raise MediaFactoryError("ditto render requires existing image and audio")
        image_sha = sha256_file(request.source_image)
        audio_sha = sha256_file(request.source_audio)
        if image_sha != self.expected_image_sha256:
            raise MediaFactoryError(
                f"ASSET_HASH_MISMATCH: image {image_sha} != {self.expected_image_sha256}"
            )
        if audio_sha != self.expected_audio_sha256:
            raise MediaFactoryError(
                f"ASSET_HASH_MISMATCH: audio {audio_sha} != {self.expected_audio_sha256}"
            )

    def _pytorch_paths(self) -> tuple[Path, Path]:
        data_root = self.model_root / "ditto_pytorch"
        cfg = self.model_root / "ditto_cfg" / "v0.4_hubert_cfg_pytorch.pkl"
        if not data_root.is_dir():
            # Allow model_root itself to be the pytorch folder.
            if (self.model_root / "models").is_dir():
                data_root = self.model_root
            else:
                raise MediaFactoryError(f"MISSING_PYTORCH_CHECKPOINTS: expected {data_root}")
        if not cfg.is_file():
            raise MediaFactoryError(f"MISSING_PYTORCH_CFG: expected {cfg}")
        return data_root, cfg

    def _run_inference(
        self,
        request: AvatarRenderRequest,
        raw_out: Path,
        logs_dir: Path,
    ) -> Path:
        if self._invoke_inference is not None:
            return self._invoke_inference(request=request, raw_out=raw_out, logs_dir=logs_dir)

        if self.first_smoke_backend != "pytorch":
            raise MediaFactoryError(
                f"unsupported first_smoke_backend={self.first_smoke_backend}; "
                "Gate1 first smoke is pytorch-only"
            )
        data_root, cfg = self._pytorch_paths()
        cmd = [
            self.python_executable,
            str(self.engine_root / "inference.py"),
            "--data_root",
            str(data_root),
            "--cfg_pkl",
            str(cfg),
            "--audio_path",
            str(request.source_audio),
            "--source_path",
            str(request.source_image),
            "--output_path",
            str(raw_out),
        ]
        (logs_dir / "ditto_command.txt").write_text(
            " ".join(cmd) + "\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            cmd,
            cwd=str(self.engine_root),
            check=False,
            capture_output=True,
            text=True,
            timeout=int(request.config.get("timeout_seconds", 3600)),
        )
        (logs_dir / "ditto_stdout.log").write_text(completed.stdout or "", encoding="utf-8")
        (logs_dir / "ditto_stderr.log").write_text(completed.stderr or "", encoding="utf-8")
        if completed.returncode != 0:
            raise MediaFactoryError(
                f"DITTO_INFERENCE_FAILED: exit={completed.returncode}; "
                f"see {logs_dir / 'ditto_stderr.log'}"
            )
        if not raw_out.is_file():
            raise MediaFactoryError("DITTO_INFERENCE_FAILED: output mp4 missing after run")
        return raw_out

    def _provenance(
        self,
        *,
        request: AvatarRenderRequest,
        inference_completed: bool,
        artifact_verified: bool,
        static_video_suspected: bool,
        media: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "real_neural_avatar": True,
            "synthetic_fixture": False,
            "inference_completed": inference_completed,
            "artifact_verified": artifact_verified,
            "static_video_suspected": static_video_suspected,
            "benchmark_run_id": request.benchmark_run_id,
            "upstream_url": DITTO_UPSTREAM_URL,
            "upstream_commit": self.upstream_commit,
            "code_license": DITTO_CODE_LICENSE,
            "weights_license": "LICENSE_REVIEW_REQUIRED",
            "first_smoke_backend": self.first_smoke_backend,
            "engine_root": str(self.engine_root),
            "model_root": str(self.model_root),
            "device": self.device,
            "input_image_sha256": sha256_file(request.source_image),
            "input_audio_sha256": sha256_file(request.source_audio),
            "adapter_preprocess": "NONE",
            "audio_transform": "NONE",
            "media_verification": dict(media),
            "gpu_gate": self._gpu_gate().to_manifest(),
        }
