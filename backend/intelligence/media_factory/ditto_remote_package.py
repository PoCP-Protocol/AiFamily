"""Build a reproducible Ditto Gate1 remote GPU execution package (no cloud purchase)."""

from __future__ import annotations

import json
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
)
from backend.intelligence.media_factory.gpu_gate import evaluate_gpu_gate

RECOMMENDED_GPU_SPEC: dict[str, Any] = {
    "priority": "Nvidia",
    "MINIMUM_EXPERIMENTAL": {
        "vram_gb": 12,
        "note": (
            "Official Ditto README does not publish a low-VRAM floor; tested on A100. "
            "12GB is an experimental lower bound for first PyTorch smoke — not guaranteed."
        ),
    },
    "RECOMMENDED_DEVELOPMENT": {
        "vram_gb": 16,
        "examples": ["RTX 4060 Ti 16GB", "RTX 4080 Laptop 16GB", "V100 16GB"],
    },
    "COMFORTABLE_BENCHMARK": {
        "vram_gb": 24,
        "examples": ["RTX 4090 24GB", "A10 24GB"],
    },
    "official_tested": {
        "gpu": "A100",
        "os": "Centos 7.2",
        "python": "3.10",
        "pytorch_env": "pytorch=2.5.1 + cuda12.1 (environment.yaml)",
        "tensorrt": "8.6.1",
    },
}


def build_remote_execution_package(
    *,
    image_locator: str,
    audio_locator: str,
    engine_root_hint: str = "/opt/aifamily-engines/ditto-talkinghead",
    model_root_hint: str = "/opt/aifamily-engines/ditto-talkinghead/checkpoints",
    python_hint: str = "/opt/aifamily-engines/ditto-talkinghead/.venv/bin/python",
) -> dict[str, Any]:
    gate = evaluate_gpu_gate()
    return {
        "package_id": "DITTO_GATE1_REMOTE_EXECUTION_V0",
        "purpose": "Reproduce first real neural Famili Gate1 smoke on a GPU node",
        "local_gpu_gate": gate.to_manifest(),
        "upstream": {
            "url": DITTO_UPSTREAM_URL,
            "commit_sha": DITTO_UPSTREAM_COMMIT_PIN,
            "code_license": DITTO_CODE_LICENSE,
            "weights": {
                "url": "https://huggingface.co/digital-avatar/ditto-talkinghead",
                "license": "LICENSE_REVIEW_REQUIRED",
            },
            "windows_support": "UNKNOWN (official README tested Centos 7.2; prefer Linux GPU node)",
            "linux_support": "YES (official)",
        },
        "first_smoke_backend": DITTO_FIRST_SMOKE_BACKEND,
        "recommended_gpu_spec": RECOMMENDED_GPU_SPEC,
        "engine_isolation": {
            "engine_root_env": "DITTO_ENGINE_ROOT",
            "python_env": "DITTO_PYTHON",
            "model_root_env": "DITTO_MODEL_ROOT",
            "device_env": "DITTO_DEVICE",
            "do_not_absorb_into_aifamily_pyproject": True,
            "hints": {
                "engine_root": engine_root_hint,
                "model_root": model_root_hint,
                "python": python_hint,
            },
        },
        "frozen_inputs": {
            "image": {
                "locator": image_locator,
                "sha256": CANONICAL_IDENTITY_SHA256,
                "modifications": "FORBIDDEN (no beautify/upscale/face-restore)",
            },
            "audio": {
                "locator": audio_locator,
                "sha256": CANONICAL_AUDIO_SHA256,
                "modifications": (
                    "FORBIDDEN (no re-TTS/denoise/pitch); "
                    "derive+record if format conversion required"
                ),
            },
        },
        "install_steps": [
            f'git clone {DITTO_UPSTREAM_URL} "$DITTO_ENGINE_ROOT"',
            f'cd "$DITTO_ENGINE_ROOT" && git checkout {DITTO_UPSTREAM_COMMIT_PIN}',
            "conda env create -f environment.yaml && conda activate ditto",
            (
                "OR create venv and install pytorch/cuda matching "
                "environment.yaml, then pip deps from README"
            ),
            (
                "git lfs install && git clone "
                "https://huggingface.co/digital-avatar/ditto-talkinghead checkpoints"
            ),
            "export DITTO_PYTHON=$(which python)",
            'export DITTO_MODEL_ROOT="$DITTO_ENGINE_ROOT/checkpoints"',
        ],
        "execution_command": {
            "cwd": "$DITTO_ENGINE_ROOT",
            "argv": [
                "$DITTO_PYTHON",
                "inference.py",
                "--data_root",
                "$DITTO_MODEL_ROOT/ditto_pytorch",
                "--cfg_pkl",
                "$DITTO_MODEL_ROOT/ditto_cfg/v0.4_hubert_cfg_pytorch.pkl",
                "--audio_path",
                "<frozen_audio.wav>",
                "--source_path",
                "<frozen_identity.png>",
                "--output_path",
                DITTO_GATE1_ARTIFACT_NAME,
            ],
        },
        "post_run_validation": [
            "ffprobe -show_streams -show_format -print_format json <output.mp4>",
            "Confirm video+audio streams, duration>0, frame_count>1",
            "Sample frames; if all identical → STATIC_VIDEO_SUSPECTED",
            "sha256sum output; record in provenance.json",
            "human_review.json status=PENDING_HUMAN_REVIEW (never auto Gate1 PASS)",
        ],
        "copy_back": [
            (
                "Copy FAMILI_DITTO_GATE1_R01.mp4 + logs + manifests into "
                "AiFamily artifacts/media_factory/benchmark_runs/<run_id>/"
            ),
            "Do not commit binaries to git",
        ],
        "cleanup": [
            "Unload CUDA contexts / exit ditto env",
            "Remove temporary onnx/trt conversion dirs if created",
            "Keep frozen input originals unmodified",
        ],
        "forbidden": [
            "No automatic cloud GPU purchase",
            "No credit-card binding by agents",
            "No EchoMimic/SadTalker in this package",
            "No fake static mux mp4",
        ],
    }


def write_remote_execution_package(dest_dir: Path, **kwargs: Any) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    payload = build_remote_execution_package(**kwargs)
    path = dest_dir / "ditto_gate1_remote_execution_package.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
