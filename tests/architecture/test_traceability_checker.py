"""The traceability checker must run — nothing more is asserted yet.

`tools/architecture/check_traceability.py` (T-08) is deliberately a *report*,
not a gate. So these tests assert only that it executes, produces the three
finding categories, and classifies confidence legally. They intentionally do
**not** assert "zero broken links": the signal-to-noise ratio of broken-link
detection is unknown until it has run against real code for a while, and a gate
that fires forty findings on day one gets muted. A muted checker is the source
repository's exact failure mode.

What these tests do protect: the checker cannot silently rot. If someone breaks
the AST route extraction or the YAML loading, this goes red — which is the
difference between this and the source repository's `--check` mode that exited 1
on the baseline commit because no CI ever invoked it.

When a category is promoted to enforced (order documented in the checker's
docstring), add the corresponding `assert not findings` here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.architecture.check_traceability import (
    CERTAIN,
    SUSPECTED,
    discover_routes,
    main,
    run_checks,
)


@pytest.fixture
def report(repo_root: Path):
    return run_checks(repo_root)


def test_checker_runs_without_error(report) -> None:
    assert isinstance(report.findings, list)


def test_exit_code_is_zero_report_mode(repo_root: Path, capsys) -> None:
    """Report mode is load-bearing: this tool must never redden CI on its own."""
    assert main(["--repo-root", str(repo_root)]) == 0
    assert "Traceability Broken-Link Report" in capsys.readouterr().out


def test_json_mode_is_machine_readable(repo_root: Path, capsys) -> None:
    import json

    assert main(["--repo-root", str(repo_root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload["counts"]) == {"UPSTREAM", "CODE_GAP", "API_ORPHAN"}


def test_every_finding_is_legally_classified(report) -> None:
    legal_categories = {"UPSTREAM", "CODE_GAP", "API_ORPHAN"}
    for finding in report.findings:
        assert finding.category in legal_categories, finding
        assert finding.confidence in {CERTAIN, SUSPECTED}, finding
        assert finding.subject and finding.detail, finding


def test_route_discovery_finds_the_known_health_endpoints(repo_root: Path) -> None:
    """A canary on the AST extraction.

    `/health` and `/ready` are the two endpoints AiFamily is certain to have
    (backend/apps/family_api/routes.py, registered in the capability registry).
    If they stop being discovered, the extractor is broken and every
    API_ORPHAN finding becomes meaningless noise rather than a real report.
    """
    routes = discover_routes(repo_root)
    assert "GET /health" in routes
    assert "GET /ready" in routes


def test_route_discovery_sees_unmounted_routers(repo_root: Path) -> None:
    """Static extraction must see routers `create_app()` never mounts.

    An unmounted router is one of the orphan classes being hunted, so importing
    the app to enumerate routes would hide exactly the findings that matter.
    product_intelligence's router is documented as unmounted, so its presence
    proves the extractor is static rather than runtime.
    """
    routes = discover_routes(repo_root)
    assert any(key.endswith("/product-intelligence/market-signals") for key in routes), (
        "the unmounted product_intelligence router should still be discovered"
    )


def test_upstream_attribution_is_now_clean(report) -> None:
    """The one category already promoted to enforced.

    UPSTREAM went from 10 findings to 0 when `business_capability` was added to
    every registry row, so it costs nothing to hold the line — and holding it
    is what stops the next capability from being added without an answer to
    "which business capability does this serve".
    `tests/architecture/test_capability_registry.py` enforces the same rule at
    the registry level; this asserts the checker agrees with it.
    """
    upstream = report.by_category("UPSTREAM")
    assert not upstream, "\n".join(f"{f.subject}: {f.detail}" for f in upstream)
