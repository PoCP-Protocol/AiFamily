"""R7 — Domains Must Not Call Model Providers Directly.

No domain module, application service, or workflow may call an LLM
provider SDK or HTTP endpoint directly. All model access must go
through backend/intelligence/model_gateway. This is the rule the source
repository wrote down as a policy constant and then violated (see the
R7 scar in governance/REPOSITORY_CONSTITUTION.md) — so it must be a real,
executing check here, not another constant nobody runs.

Wave 0 note: backend/ has no code yet, so this test currently scans zero
files and passes trivially. The detection regex is real and will fire
the moment a violating pattern is introduced in a later wave.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_RELATIVE_PATH = "backend"
ALLOWED_PREFIX = "backend/intelligence/model_gateway"

# Patterns that indicate a direct provider SDK import/call or a direct HTTP
# call to a known provider API host. Intentionally broad: catching one false
# positive in the gateway's own allowed directory is fine (it is excluded by
# path below); missing a real violation is not.
PROVIDER_PATTERNS = [
    re.compile(r"\bimport\s+openai\b"),
    re.compile(r"\bimport\s+anthropic\b"),
    re.compile(r"\bopenai\.[A-Za-z_]"),
    re.compile(r"\banthropic\.[A-Za-z_]"),
    re.compile(r"\bfrom\s+openai\b"),
    re.compile(r"\bfrom\s+anthropic\b"),
    re.compile(r"requests\.(get|post)\(\s*[\"'].*api\.(openai|anthropic|deepseek)"),
    re.compile(r"httpx\.(get|post|Client)\(.*api\.(openai|anthropic|deepseek)"),
    re.compile(r"https://api\.(openai|anthropic|deepseek)\.com"),
]


def _iter_python_files(backend_dir: Path):
    if not backend_dir.exists():
        return
    yield from backend_dir.rglob("*.py")


def test_no_direct_provider_calls_outside_model_gateway(repo_root: Path) -> None:
    backend_dir = repo_root / BACKEND_RELATIVE_PATH
    violations: list[str] = []

    for py_file in _iter_python_files(backend_dir):
        rel_path = py_file.relative_to(repo_root).as_posix()
        if rel_path.startswith(ALLOWED_PREFIX):
            continue

        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for pattern in PROVIDER_PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel_path}: matched /{pattern.pattern}/")

    assert not violations, (
        "R7 violation: direct model provider SDK/HTTP usage found outside "
        f"{ALLOWED_PREFIX}:\n" + "\n".join(violations) + "\n"
        "Route all model access through backend/intelligence/model_gateway."
    )
