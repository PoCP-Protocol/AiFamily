"""CLI entry for Gate1 benchmark foundation.

Example:
  uv run python -m backend.intelligence.media_factory.benchmark_cli \\
    --provider fixture --image ... --audio ... --runs-root artifacts/...
"""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.intelligence.media_factory.benchmark import BenchmarkRunner, default_runs_root
from backend.intelligence.media_factory.contracts import (
    CANONICAL_AUDIO_SHA256,
    CANONICAL_IDENTITY_SHA256,
    FamiliAvatarBenchmarkInput,
)
from backend.intelligence.media_factory.providers.avatar import AvatarProviderRegistry
from backend.intelligence.media_factory.providers.fixture import FixtureAvatarProvider


def build_default_registry() -> AvatarProviderRegistry:
    registry = AvatarProviderRegistry()
    registry.register(FixtureAvatarProvider())
    return registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Famili Gate1 avatar benchmark runner")
    parser.add_argument("--provider", default="fixture")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument(
        "--require-canonical-hashes",
        action="store_true",
        help="Enforce V2 identity + smoke audio sha256 locks",
    )
    parser.add_argument("--execution-target", default="LOCAL", choices=("LOCAL", "REMOTE_GPU_NODE"))
    args = parser.parse_args(argv)

    expected_image = CANONICAL_IDENTITY_SHA256 if args.require_canonical_hashes else None
    expected_audio = CANONICAL_AUDIO_SHA256 if args.require_canonical_hashes else None
    benchmark_input = FamiliAvatarBenchmarkInput.from_paths(
        args.image,
        args.audio,
        expected_image_sha256=expected_image,
        expected_audio_sha256=expected_audio,
    )
    registry = build_default_registry()
    runner = BenchmarkRunner(
        registry,
        runs_root=args.runs_root or default_runs_root(),
        execution_target=args.execution_target,
    )
    run_dir = runner.run(provider_id=args.provider, benchmark_input=benchmark_input)
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
