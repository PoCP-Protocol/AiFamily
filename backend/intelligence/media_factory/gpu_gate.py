"""Local GPU gate for neural avatar inference (FAMILY-MEDIA-003).

Dedicated VRAM only — Windows shared GPU memory must not inflate the total.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

GpuGateStatus = Literal["PASS", "CONDITIONAL", "FAIL"]

# Policy (ADR-0018 Gate1 smoke): fail below 8 GiB; conditional 8–11; pass ≥12.
VRAM_FAIL_BELOW_MIB = 8 * 1024
VRAM_PASS_AT_OR_ABOVE_MIB = 12 * 1024


@dataclass(frozen=True, slots=True)
class GpuInfo:
    model: str
    vram_total_mib: int
    driver_version: str
    cuda_reported: str
    source: str


@dataclass(frozen=True, slots=True)
class GpuGateResult:
    status: GpuGateStatus
    info: GpuInfo | None
    reason: str
    local_real_inference_allowed: bool

    def to_manifest(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "local_real_inference_allowed": self.local_real_inference_allowed,
            "reason": self.reason,
            "gpu": (
                {
                    "model": self.info.model,
                    "vram_total_mib": self.info.vram_total_mib,
                    "driver_version": self.info.driver_version,
                    "cuda_reported": self.info.cuda_reported,
                    "source": self.info.source,
                }
                if self.info
                else None
            ),
            "policy": {
                "fail_below_mib": VRAM_FAIL_BELOW_MIB,
                "pass_at_or_above_mib": VRAM_PASS_AT_OR_ABOVE_MIB,
                "shared_memory_inflates_vram": False,
            },
        }


def evaluate_vram_mib(vram_total_mib: int) -> GpuGateStatus:
    if vram_total_mib < VRAM_FAIL_BELOW_MIB:
        return "FAIL"
    if vram_total_mib < VRAM_PASS_AT_OR_ABOVE_MIB:
        return "CONDITIONAL"
    return "PASS"


def probe_nvidia_smi() -> GpuInfo | None:
    """Read dedicated VRAM via nvidia-smi query (fail-closed if unavailable)."""
    if shutil.which("nvidia-smi") is None:
        return None
    # Older drivers may lack cuda_version as --query-gpu; banner parse fills CUDA.
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    line = completed.stdout.strip().splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        return None
    model, mem_s, driver = parts[0], parts[1], parts[2]
    try:
        vram = int(float(mem_s))
    except ValueError:
        return None

    cuda_reported = "UNKNOWN"
    try:
        banner = subprocess.run(
            ["nvidia-smi"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        match = re.search(r"CUDA Version:\s*([0-9.]+)", banner.stdout or "")
        if match:
            cuda_reported = match.group(1)
    except (OSError, subprocess.TimeoutExpired):
        pass

    return GpuInfo(
        model=model,
        vram_total_mib=vram,
        driver_version=driver,
        cuda_reported=cuda_reported,
        source="nvidia-smi",
    )


def evaluate_gpu_gate(
    *,
    probe: Callable[[], GpuInfo | None] | None = None,
) -> GpuGateResult:
    probe_fn = probe or probe_nvidia_smi
    info = probe_fn()
    if info is None:
        return GpuGateResult(
            status="FAIL",
            info=None,
            reason="GPU_PROBE_UNAVAILABLE: nvidia-smi missing or unreadable",
            local_real_inference_allowed=False,
        )
    status = evaluate_vram_mib(info.vram_total_mib)
    if status == "FAIL":
        return GpuGateResult(
            status="FAIL",
            info=info,
            reason=(
                f"GPU_GATE_FAIL: dedicated VRAM {info.vram_total_mib} MiB "
                f"< {VRAM_FAIL_BELOW_MIB} MiB ({info.model})"
            ),
            local_real_inference_allowed=False,
        )
    if status == "CONDITIONAL":
        return GpuGateResult(
            status="CONDITIONAL",
            info=info,
            reason=(
                f"GPU_GATE_CONDITIONAL: dedicated VRAM {info.vram_total_mib} MiB "
                f"in [8,12) GiB; allow only if upstream explicitly supports this VRAM"
            ),
            local_real_inference_allowed=False,
        )
    return GpuGateResult(
        status="PASS",
        info=info,
        reason=f"GPU_GATE_PASS: dedicated VRAM {info.vram_total_mib} MiB ({info.model})",
        local_real_inference_allowed=True,
    )


def gpu_gate_json(*, probe: Callable[[], GpuInfo | None] | None = None) -> str:
    return json.dumps(evaluate_gpu_gate(probe=probe).to_manifest(), indent=2) + "\n"
