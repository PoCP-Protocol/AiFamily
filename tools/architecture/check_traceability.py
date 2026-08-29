#!/usr/bin/env python
"""Traceability broken-link reporter (T-08).

``docs/12_governance/DOCUMENT_GOVERNANCE.md`` §6 declares the chain every line
of business code must be traceable along::

    Strategy -> Business Capability -> Product Capability -> Domain
             -> Command/Event -> API -> Code -> Test -> Metric

``governance/CAPABILITY_REGISTRY.yaml`` already carries the
``Domain -> Command -> API -> Code -> Test`` segment, and
``tests/architecture/test_capability_registry.py`` already proves every declared
``code``/``tests`` path exists on disk. This tool deliberately does **not**
repeat that. It reports the three link classes nobody checks:

1. **UPSTREAM**   a capability with no business-capability attribution
                  (the chain snaps above Domain).
2. **CODE_GAP**   a directory under ``backend/`` holding ``.py`` files that no
                  capability's ``code`` field covers (code with no capability).
3. **API_ORPHAN** a FastAPI route registered in code with no registry entry, or
                  a registry ``api`` claim with no matching route in code.

Report mode, on purpose
-----------------------
This exits 0 no matter what it finds. The signal-to-noise ratio of broken-link
detection is unknown until it has been run against a real repository; a checker
that spits out forty findings on day one gets muted, and a muted checker is the
exact failure mode of the source repository's governance files (declared,
never executed, silently rotted). So it reports, and a human decides.

Findings are split into two confidence tiers:

* ``CERTAIN``  — mechanically verifiable. A route exists in code and no
  registry row mentions it; a registry row claims an API that no route serves.
  These are facts, not judgement calls.
* ``SUSPECTED`` — needs human reading. A code directory may be uncovered
  because it is genuinely orphaned, or because it is a shared primitive, a
  test fixture directory, or honestly logged under
  ``not_yet_capabilities``. We subtract the ledgered ones and still label the
  rest suspected.

Path to enforcement
-------------------
When the numbers below are judged acceptable, promote in this order:

1. **API_ORPHAN / registry-claims-missing-route** first. Zero judgement
   involved: the registry asserts an endpoint that does not exist. That is a
   lie in a file read as truth, and there is no legitimate reason to have one.
2. **UPSTREAM** second, once every capability carries ``business_capability``.
   Cheap to satisfy (one line per row) and it is the link the whole chain
   hangs from.
3. **API_ORPHAN / route-not-registered** third. Requires the registry to keep
   pace with every mounted router; safe only after T-04's API contract work
   settles the endpoint inventory.
4. **CODE_GAP** last, and possibly never as a hard gate. Overlaps R3
   (``test_migration_manifest.py`` already forbids unmanifested backend dirs)
   and its residue is mostly judgement about what constitutes "a capability".
   Better kept as a review-time report.

Usage::

    uv run python tools/architecture/check_traceability.py
    uv run python tools/architecture/check_traceability.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

CAPABILITY_REGISTRY = "governance/CAPABILITY_REGISTRY.yaml"
BACKEND_DIR = "backend"

# Sentinel a capability may declare instead of a business capability name when
# it is a platform primitive rather than something the business sells or
# promises. Chain-wise these terminate at the constitution/platform docs, not
# at BUSINESS_CAPABILITY_MAP.md, and pretending otherwise would invent
# attributions rather than record them.
PLATFORM_SENTINEL = "PLATFORM_INTERNAL"

# Directories under backend/ that are structurally exempt from CODE_GAP:
# a domain's own colocated tests are test artifacts, not an uncovered
# capability, and __pycache__ is not source.
CODE_GAP_EXEMPT_SEGMENTS = {"__pycache__", "tests", "test"}

CERTAIN = "CERTAIN"
SUSPECTED = "SUSPECTED"


@dataclass
class Finding:
    category: str
    confidence: str
    subject: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "subject": self.subject,
            "detail": self.detail,
        }


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, category: str, confidence: str, subject: str, detail: str) -> None:
        self.findings.append(Finding(category, confidence, subject, detail))

    def by_category(self, category: str) -> list[Finding]:
        return [f for f in self.findings if f.category == category]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_registry(repo_root: Path) -> dict[str, Any]:
    path = repo_root / CAPABILITY_REGISTRY
    if not path.is_file():
        raise SystemExit(f"{CAPABILITY_REGISTRY} not found under {repo_root}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{CAPABILITY_REGISTRY} must parse to a mapping")
    return data


# ---------------------------------------------------------------------------
# 1. Upstream attribution
# ---------------------------------------------------------------------------


def check_upstream(registry: dict[str, Any], report: Report) -> None:
    """Report capabilities whose chain snaps above Domain.

    Design choice — an explicit ``business_capability`` field rather than
    deriving attribution from ``domain``. Deriving would be free but would
    also be circular: ``domain: domains/membership`` only restates the code
    location, so a derived check can never fail and would certify every
    capability as attributed while proving nothing. The whole point of the
    upstream link is that a human asserted *why* the code exists. That
    assertion has to be written down somewhere, and the registry is the file
    already read as the code/doc bridge.
    """
    declared = registry.get("enums", {}).get("business_capability")
    legal = set(declared) if isinstance(declared, list) else set()
    if not legal:
        report.notes.append(
            "registry declares no `enums.business_capability` list — upstream names "
            "cannot be validated, only presence checked"
        )

    for entry in registry.get("capabilities") or []:
        name = entry.get("capability", "<unnamed>")
        attribution = entry.get("business_capability")
        if not attribution:
            report.add(
                "UPSTREAM",
                CERTAIN,
                name,
                "no `business_capability` field — chain breaks above Domain; cannot "
                "answer 'which business capability does this serve'",
            )
            continue
        if legal and attribution not in legal:
            report.add(
                "UPSTREAM",
                CERTAIN,
                name,
                f"business_capability {attribution!r} is not in the registry's declared "
                "enums.business_capability list",
            )


# ---------------------------------------------------------------------------
# 2. Code coverage gaps
# ---------------------------------------------------------------------------


def _covered_code_prefixes(registry: dict[str, Any]) -> set[str]:
    prefixes: set[str] = set()
    for entry in registry.get("capabilities") or []:
        code = entry.get("code") or {}
        for rel_path in code.values():
            if not rel_path:
                continue
            prefixes.add(str(rel_path).rstrip("/"))
    return prefixes


def _ledgered_paths(registry: dict[str, Any]) -> set[str]:
    """Paths the registry already admits are not capabilities.

    ``not_yet_capabilities`` is an honesty ledger. Reporting its entries as
    broken links would be reporting the repository for telling the truth, and
    is exactly the noise that gets a checker muted.
    """
    ledgered: set[str] = set()
    for entry in registry.get("not_yet_capabilities") or []:
        rel_path = entry.get("path")
        if rel_path:
            ledgered.add(str(rel_path).rstrip("/"))
    return ledgered


def _python_dirs(backend_dir: Path, repo_root: Path) -> list[str]:
    if not backend_dir.exists():
        return []
    dirs = {
        py_file.parent.relative_to(repo_root).as_posix()
        for py_file in backend_dir.rglob("*.py")
    }
    return sorted(
        d
        for d in dirs
        if not (set(d.split("/")) & CODE_GAP_EXEMPT_SEGMENTS)
    )


def check_code_coverage(registry: dict[str, Any], repo_root: Path, report: Report) -> None:
    """Report backend/ python directories no capability's `code` field covers.

    Distinct from ``test_migration_manifest.py`` (R3), which asks the
    *manifest* question — "was this directory approved for import" — at a
    coarse granularity where one `target` covers a whole subtree. This asks the
    *capability* question: "does a declared capability claim this code". A
    directory can be perfectly manifested and still be capability-orphaned;
    ``backend/domains/loyalty_points`` is that case at time of writing. To
    avoid duplicating R3's noise we never report a directory R3 would already
    flag, and we subtract everything the registry ledgers under
    ``not_yet_capabilities``.
    """
    covered = _covered_code_prefixes(registry)
    ledgered = _ledgered_paths(registry)
    code_dirs = _python_dirs(repo_root / BACKEND_DIR, repo_root)

    for rel_dir in code_dirs:
        if any(rel_dir == p or rel_dir.startswith(p + "/") for p in covered):
            continue
        if any(rel_dir == p or rel_dir.startswith(p + "/") for p in ledgered):
            continue
        # A directory whose descendants are covered, and whose own .py files
        # are all package markers, is a container — not a gap. Reporting
        # `backend/platform/audit` because a capability names
        # `backend/platform/audit/models.py` rather than the directory is noise
        # of exactly the kind that gets a checker muted.
        has_descendant_coverage = any(p.startswith(rel_dir + "/") for p in covered | ledgered)
        own_modules = sorted(
            p.name
            for p in (repo_root / rel_dir).glob("*.py")
            if p.name != "__init__.py"
            and not any(
                (rel_dir + "/" + p.name) == c or (rel_dir + "/" + p.name).startswith(c + "/")
                for c in covered | ledgered
            )
        )
        if has_descendant_coverage and not own_modules:
            continue

        if has_descendant_coverage:
            detail = (
                "descendants are covered but these modules in this directory are not "
                f"claimed by any capability `code` entry: {', '.join(own_modules)}"
            )
        else:
            detail = (
                "contains .py files but no capability's `code` field covers it and it "
                "is not ledgered under not_yet_capabilities — either register a "
                "capability or add an honest not_yet_capabilities row"
            )
        report.add("CODE_GAP", SUSPECTED, rel_dir, detail)


# ---------------------------------------------------------------------------
# 3. API orphans
# ---------------------------------------------------------------------------


def _decorator_route(node: ast.expr) -> tuple[str, str] | None:
    """Extract (METHOD, path) from an `@router.get("/x")` style decorator."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    method = func.attr.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        return None
    # Receiver must plausibly be a router/app, not an arbitrary object.
    receiver = func.value
    receiver_name = receiver.id if isinstance(receiver, ast.Name) else None
    if receiver_name not in {"router", "app", "application", "api"}:
        return None
    if not node.args:
        return None
    first = node.args[0]
    if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
        return None
    return method, first.value


def _router_prefix(tree: ast.AST) -> str:
    """Find a literal `prefix=` passed to an APIRouter(...) in this module."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        callee = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if callee != "APIRouter":
            continue
        for kw in node.keywords:
            if (
                kw.arg == "prefix"
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                return kw.value.value
    return ""


def discover_routes(repo_root: Path) -> dict[str, list[str]]:
    """Map "METHOD /path" -> [source files] for every route declared in code.

    Static (AST) extraction rather than importing the app. Importing would only
    see routers actually mounted in `create_app()`, and an unmounted router is
    precisely one of the orphan classes we are hunting — importing would hide
    the finding. It also keeps the checker runnable with no DB or settings.
    """
    backend = repo_root / BACKEND_DIR
    routes: dict[str, list[str]] = {}
    if not backend.exists():
        return routes

    for py_file in sorted(backend.rglob("*.py")):
        parts = set(py_file.relative_to(repo_root).as_posix().split("/"))
        if parts & {"__pycache__", "tests", "test"}:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        prefix = _router_prefix(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for deco in node.decorator_list:
                parsed = _decorator_route(deco)
                if parsed is None:
                    continue
                method, path = parsed
                key = f"{method} {prefix}{path}"
                routes.setdefault(key, []).append(
                    py_file.relative_to(repo_root).as_posix()
                )
    return routes


def _registry_api_claims(registry: dict[str, Any]) -> dict[str, list[str]]:
    """Map normalised "METHOD /path" -> [capability names] from `api` fields."""
    claims: dict[str, list[str]] = {}
    for entry in registry.get("capabilities") or []:
        api = entry.get("api")
        if not api:
            continue
        values = api if isinstance(api, list) else [api]
        for value in values:
            key = " ".join(str(value).split())
            method, _, path = key.partition(" ")
            key = f"{method.upper()} {path}"
            claims.setdefault(key, []).append(entry.get("capability", "<unnamed>"))
    return claims


def _capability_owning_file(registry: dict[str, Any], rel_file: str) -> str | None:
    """Which capability, if any, declares code covering this source file."""
    for entry in registry.get("capabilities") or []:
        for rel_path in (entry.get("code") or {}).values():
            if not rel_path:
                continue
            p = str(rel_path).rstrip("/")
            if rel_file == p or rel_file.startswith(p + "/"):
                return entry.get("capability")
    return None


def check_api_orphans(registry: dict[str, Any], repo_root: Path, report: Report) -> None:
    routes = discover_routes(repo_root)
    claims = _registry_api_claims(registry)

    for route, sources in sorted(routes.items()):
        if route in claims:
            continue
        owners = {
            owner
            for owner in (_capability_owning_file(registry, src) for src in sources)
            if owner
        }
        if owners:
            # The file is inside a registered capability, but that capability
            # does not declare this endpoint — the registry understates it.
            report.add(
                "API_ORPHAN",
                CERTAIN,
                route,
                f"declared in {', '.join(sorted(sources))}; the owning capability "
                f"({', '.join(sorted(owners))}) does not list this endpoint in its "
                "`api` field",
            )
        else:
            report.add(
                "API_ORPHAN",
                CERTAIN,
                route,
                f"declared in {', '.join(sorted(sources))} but no capability in the "
                "registry claims this code or this endpoint — fully unregistered "
                "HTTP surface",
            )

    for claim, owners in sorted(claims.items()):
        if claim in routes:
            continue
        report.add(
            "API_ORPHAN",
            CERTAIN,
            claim,
            f"capability {', '.join(sorted(owners))} claims this endpoint but no "
            "route decorator in backend/ declares it",
        )


# ---------------------------------------------------------------------------
# Orchestration & rendering
# ---------------------------------------------------------------------------


def run_checks(repo_root: Path = REPO_ROOT) -> Report:
    registry = load_registry(repo_root)
    report = Report()
    check_upstream(registry, report)
    check_code_coverage(registry, repo_root, report)
    check_api_orphans(registry, repo_root, report)
    return report


CATEGORY_TITLES = {
    "UPSTREAM": "1. UPSTREAM — capability has no business-capability attribution",
    "CODE_GAP": "2. CODE_GAP — backend/ python dirs no capability claims",
    "API_ORPHAN": "3. API_ORPHAN — routes vs registry `api` field",
}


def render(report: Report) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("AiFamily Traceability Broken-Link Report  (report mode — never fails CI)")
    lines.append("=" * 78)
    lines.append("")
    lines.append("Chain under test (DOCUMENT_GOVERNANCE.md §6):")
    lines.append("  Strategy -> Business Capability -> Product Capability -> Domain")
    lines.append("           -> Command/Event -> API -> Code -> Test -> Metric")
    lines.append("")
    lines.append("Not re-checked here (already enforced by")
    lines.append("tests/architecture/test_capability_registry.py): existence of declared")
    lines.append("code/tests paths, status & actor enum legality, R4 tested-needs-tests.")
    lines.append("")

    total_certain = sum(1 for f in report.findings if f.confidence == CERTAIN)
    total_suspected = sum(1 for f in report.findings if f.confidence == SUSPECTED)

    lines.append("-" * 78)
    lines.append("SUMMARY")
    lines.append("-" * 78)
    for category in CATEGORY_TITLES:
        found = report.by_category(category)
        certain = sum(1 for f in found if f.confidence == CERTAIN)
        suspected = len(found) - certain
        lines.append(
            f"  {category:<11} {len(found):>3} finding(s)  "
            f"[{certain} certain / {suspected} suspected]"
        )
    lines.append(
        f"  {'TOTAL':<11} {len(report.findings):>3} finding(s)  "
        f"[{total_certain} certain / {total_suspected} suspected]"
    )
    lines.append("")

    for category, title in CATEGORY_TITLES.items():
        found = report.by_category(category)
        lines.append("-" * 78)
        lines.append(title)
        lines.append("-" * 78)
        if not found:
            lines.append("  (none)")
            lines.append("")
            continue
        for f in found:
            lines.append(f"  [{f.confidence}] {f.subject}")
            for chunk in _wrap(f.detail, 70):
                lines.append(f"        {chunk}")
        lines.append("")

    if report.notes:
        lines.append("-" * 78)
        lines.append("NOTES")
        lines.append("-" * 78)
        for note in report.notes:
            lines.append(f"  - {note}")
        lines.append("")

    lines.append("-" * 78)
    lines.append("PROMOTION PATH (report mode -> enforced)")
    lines.append("-" * 78)
    lines.append("  Promote in this order once signal-to-noise is judged acceptable:")
    lines.append("   1) API_ORPHAN / registry-claims-a-route-that-does-not-exist —")
    lines.append("      zero judgement, a registry that lies about an endpoint has no")
    lines.append("      legitimate case. Safe to enforce first.")
    lines.append("   2) UPSTREAM — once every row carries business_capability. One line")
    lines.append("      per capability to satisfy; it is the link the chain hangs from.")
    lines.append("   3) API_ORPHAN / route-not-registered — after T-04 settles the API")
    lines.append("      contract inventory, otherwise it fights concurrent route work.")
    lines.append("   4) CODE_GAP — keep as report. It overlaps R3 in")
    lines.append("      test_migration_manifest.py and its residue is a judgement call")
    lines.append("      about what counts as 'a capability'.")
    lines.append("")
    lines.append("Exit code is always 0. This tool reports; humans decide.")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    words = " ".join(text.split()).split(" ")
    out: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            out.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        out.append(current)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT, help="repository root (default: inferred)"
    )
    args = parser.parse_args(argv)

    report = run_checks(args.repo_root)

    if args.json:
        print(
            json.dumps(
                {
                    "findings": [f.as_dict() for f in report.findings],
                    "notes": report.notes,
                    "counts": {
                        category: len(report.by_category(category))
                        for category in CATEGORY_TITLES
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render(report))

    # Report mode: never fail. See module docstring for the promotion path.
    return 0


if __name__ == "__main__":
    sys.exit(main())
