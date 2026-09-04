"""ADR-0019 boundaries, checked mechanically.

Three claims ADR-0019 makes that would otherwise be prose in a runbook:

1. **Offline Media Factory != Realtime Avatar Runtime.** Frozen by ADR-0018 §3
   and re-frozen by ADR-0019. A freeze nobody checks is a comment, so the
   import graph is checked: the offline benchmark must not reach into the
   realtime package, and the realtime package must not reuse the offline Gate1
   pipeline.

2. **Transport is separable from the provider contract.** The source
   repository's realtime layer welded provider semantics to a WebSocket
   handler, and the visible consequence was `WebSocket PASS` being read as
   "digital human works" (ADR-0018 §Context). Here the provider contract is
   structurally unable to import the transport module, so a future WebRTC
   binding cannot require rewriting a provider.

3. **The GPU smoke harness is prepared, not armed.** No subprocess, socket or
   SSH call may exist in it — otherwise "does not automatically start a GPU
   node" depends on nobody calling the wrong function.
"""

from __future__ import annotations

import ast
from pathlib import Path

REALTIME_PKG = "backend/intelligence/media_factory/realtime"
MEDIA_FACTORY_PKG = "backend/intelligence/media_factory"

REALTIME_MODULE_PREFIX = "backend.intelligence.media_factory.realtime"

#: The offline Gate1 pipeline. `contracts` and `gpu_gate` are excluded on
#: purpose: the frozen asset hashes and the upstream pin are repo-level
#: primitives shared by both runtimes, and duplicating them would be the R14
#: failure mode (two copies of one truth) traded for a tidier import graph.
OFFLINE_PIPELINE_MODULES = (
    f"{MEDIA_FACTORY_PKG.replace('/', '.')}.benchmark",
    f"{MEDIA_FACTORY_PKG.replace('/', '.')}.benchmark_cli",
    f"{MEDIA_FACTORY_PKG.replace('/', '.')}.human_gate",
    f"{MEDIA_FACTORY_PKG.replace('/', '.')}.media_verify",
    f"{MEDIA_FACTORY_PKG.replace('/', '.')}.provenance",
    f"{MEDIA_FACTORY_PKG.replace('/', '.')}.ditto_remote_package",
    f"{MEDIA_FACTORY_PKG.replace('/', '.')}.providers",
)

#: Modules that define the provider-facing contract. None may know a transport.
CONTRACT_MODULES = (
    "contracts.py",
    "provider.py",
    "session.py",
    "session_state.py",
    "sequencing.py",
    "metrics.py",
    "fixture_provider.py",
    "ditto_provider.py",
)

TRANSPORT_MODULE = f"{REALTIME_MODULE_PREFIX}.transport"

SMOKE_HARNESS = f"{REALTIME_PKG}/ditto_online_smoke.py"
EXECUTION_MODULES = frozenset({"subprocess", "socket", "asyncio", "paramiko", "http", "urllib"})


def _imported_modules(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_realtime_package_exists_and_is_scanned(repo_root: Path) -> None:
    files = _python_files(repo_root / REALTIME_PKG)
    assert files, f"{REALTIME_PKG} contains no Python files — these checks would pass vacuously"


def test_offline_media_factory_does_not_import_the_realtime_runtime(repo_root: Path) -> None:
    offline_files = [
        path
        for path in _python_files(repo_root / MEDIA_FACTORY_PKG)
        if REALTIME_PKG not in path.as_posix()
    ]
    assert offline_files, "offline media_factory modules not found"

    violations = [
        f"{path.relative_to(repo_root).as_posix()}:{lineno} imports {module}"
        for path in offline_files
        for lineno, module in _imported_modules(path)
        if module.startswith(REALTIME_MODULE_PREFIX)
    ]
    assert not violations, (
        "Offline Media Factory reaches into the Realtime Avatar Runtime. ADR-0018 §3 "
        "and ADR-0019 freeze these as separate runtimes: an offline benchmark run must "
        "not be able to open a realtime session, and `media_factory/__init__.py` must "
        "not re-export the realtime package.\n" + "\n".join(violations)
    )


def test_realtime_runtime_does_not_reuse_the_offline_gate1_pipeline(repo_root: Path) -> None:
    violations = [
        f"{path.relative_to(repo_root).as_posix()}:{lineno} imports {module}"
        for path in _python_files(repo_root / REALTIME_PKG)
        for lineno, module in _imported_modules(path)
        if module.startswith(OFFLINE_PIPELINE_MODULES)
    ]
    assert not violations, (
        "Realtime Avatar Runtime imports the offline Gate1 pipeline. Sharing the frozen "
        "asset constants from media_factory.contracts is permitted; reusing the offline "
        "benchmark runner, human gate, media verifier or offline providers is not "
        "(ADR-0019).\n" + "\n".join(violations)
    )


def test_provider_contract_cannot_reach_the_transport(repo_root: Path) -> None:
    violations: list[str] = []
    for module_name in CONTRACT_MODULES:
        path = repo_root / REALTIME_PKG / module_name
        assert path.is_file(), f"{REALTIME_PKG}/{module_name} is missing"
        violations.extend(
            f"{path.relative_to(repo_root).as_posix()}:{lineno} imports {module}"
            for lineno, module in _imported_modules(path)
            if module == TRANSPORT_MODULE
        )
    assert not violations, (
        "A provider-contract module imports the transport binding. Transport and "
        "provider contract must stay separate so a WebRTC binding can be added without "
        "touching any provider (ADR-0019 §Transport).\n" + "\n".join(violations)
    )


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of the string constants that are docstrings.

    Matched by position rather than by value: `ast.get_docstring` dedents what it
    returns, so comparing text would fail to recognise every indented docstring
    and the check would flag its own explanatory prose.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            ids.add(id(first.value))
    return ids


def test_no_provider_module_carries_a_wire_protocol_literal(repo_root: Path) -> None:
    """A provider may *explain* a transport in prose; it may not encode one.

    Docstrings are exempt because the boundary being defended is behavioural: a
    default `wss://` endpoint or a hand-rolled frame opcode inside a provider is
    the transport leaking into the contract, whereas a docstring naming WebSocket
    is documentation of where the seam lies.
    """
    markers = ("websocket", "webrtc", "ws://", "wss://")
    violations: list[str] = []
    for path in _python_files(repo_root / REALTIME_PKG):
        if path.name == "transport.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        exempt = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in exempt:
                continue
            lowered = node.value.lower()
            hit = next((m for m in markers if m in lowered), None)
            if hit:
                violations.append(
                    f"{path.relative_to(repo_root).as_posix()}:{node.lineno} "
                    f"string literal contains {hit!r}"
                )
    assert not violations, (
        "A realtime provider module carries a wire-protocol literal. Transport details "
        "belong in transport.py so a future WebRTC binding needs no provider change "
        "(ADR-0019 §Transport).\n" + "\n".join(violations)
    )


def test_smoke_harness_cannot_execute_anything(repo_root: Path) -> None:
    path = repo_root / SMOKE_HARNESS
    assert path.is_file(), f"{SMOKE_HARNESS} is missing"

    offenders = [
        f"{SMOKE_HARNESS}:{lineno} imports {module}"
        for lineno, module in _imported_modules(path)
        if module.split(".")[0] in EXECUTION_MODULES
    ]
    assert not offenders, (
        "The GPU smoke harness imports an execution or network module. FAMILY-REALTIME-001 "
        "requires the harness to be prepared and not executed: no GPU start, no SSH, no "
        "weight download, no inference.\n" + "\n".join(offenders)
    )


def test_realtime_package_declares_no_gpu_dependency(repo_root: Path) -> None:
    """No heavy engine dependency may leak into AiFamily's own runtime."""
    banned = {"torch", "tensorrt", "onnxruntime", "librosa", "cv2", "numpy", "soundfile"}
    violations = [
        f"{path.relative_to(repo_root).as_posix()}:{lineno} imports {module}"
        for path in _python_files(repo_root / REALTIME_PKG)
        for lineno, module in _imported_modules(path)
        if module.split(".")[0] in banned
    ]
    assert not violations, (
        "The realtime package imports an engine-side dependency. The avatar engine and "
        "everything it needs live on the GPU media compute node, outside this worktree; "
        "AiFamily's contract tests must run on a machine with no GPU (ADR-0019).\n"
        + "\n".join(violations)
    )
