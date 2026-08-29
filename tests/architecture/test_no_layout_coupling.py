"""R12 — No Implicit Layout Coupling.

No code may rely on process cwd, sys.path injection, or directory depth
to resolve imports. All internal packages must resolve as real
installable packages. No hardcoded repository physical paths either —
this is precisely the source repository's `from packages.contracts
import ...` bug (only worked if cwd happened to be pinned at
50_开发_dev/backend) plus the `.pth` file hardcoding the source repo's
absolute path.

Wave 0 note: backend/ has no code yet, so this scan currently covers zero
files and passes trivially. The detection patterns are real and will
fire against future violations.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_RELATIVE_PATH = "backend"

SOURCE_REPO_PATH_LITERALS = [
    "50_开发_dev",
    "D:\\family-ai",
    "D:/family-ai",
]

PATTERNS = [
    re.compile(r"sys\.path\.insert"),
    re.compile(r"sys\.path\.append"),
    re.compile(r"^\s*from\s+packages\.", re.MULTILINE),
    re.compile(r"^\s*import\s+packages\.", re.MULTILINE),
]


def _iter_python_files(backend_dir: Path):
    if not backend_dir.exists():
        return
    yield from backend_dir.rglob("*.py")


def _code_only_source(text: str) -> str:
    """Return the module's source with comments and docstrings removed.

    Uses ast so that a legacy path sitting in a genuine string constant (which
    code could read) is still visible, while the same path cited in a docstring
    or `#` comment is not.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text  # unparseable — fall back to strict scanning

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                doc = body[0].value
                for lineno in range(doc.lineno, (doc.end_lineno or doc.lineno) + 1):
                    docstrings.add(lineno)

    kept: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if lineno in docstrings:
            continue
        code, _, _ = line.partition("#")
        kept.append(code)
    return "\n".join(kept)


def test_no_sys_path_injection_or_bare_packages_import(repo_root: Path) -> None:
    backend_dir = repo_root / BACKEND_RELATIVE_PATH
    violations: list[str] = []

    for py_file in _iter_python_files(backend_dir):
        rel_path = py_file.relative_to(repo_root).as_posix()
        text = py_file.read_text(encoding="utf-8", errors="ignore")

        for pattern in PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel_path}: matched /{pattern.pattern}/")

        # R12 targets *executable* coupling, not documentary citation.
        #
        # A docstring recording "this table came from
        # 50_开发_dev/database/migrations/0058_....sql" is provenance, and
        # provenance is worth keeping — the migration audit depends on being able
        # to trace a table back to the legacy migration that defined it. What R12
        # forbids is code that *resolves* a path through the legacy layout.
        #
        # So the literal check runs against code lines only. Stripping comments
        # and docstrings is done with ast rather than regex so that a legacy path
        # hidden inside a real string constant is still caught.
        for literal in SOURCE_REPO_PATH_LITERALS:
            if literal in _code_only_source(text) :
                violations.append(
                    f"{rel_path}: contains hardcoded source-repo path literal {literal!r} "
                    "in executable code (docstrings/comments may cite legacy paths as provenance)"
                )

    assert not violations, (
        "R12 violation: implicit layout coupling detected:\n" + "\n".join(violations) + "\n"
        "All internal packages must resolve via installable package names, not "
        "sys.path tricks, bare `packages.*` imports, or hardcoded repo paths."
    )
