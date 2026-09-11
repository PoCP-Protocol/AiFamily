"""R2.1 — Run Taxonomy architecture guard (ADR-0167).

ADR-0167 freezes a four-level Run model — GatewayAttempt -> AgentRun ->
IntelligenceRun -> NamedAction/DomainFact — with an explicit "must not
own" boundary per level: AgentRun is a pure technical execution record
and must never carry cognitive/lineage semantics (those belong to
IntelligenceRun), and EvaluationLedger is DEPRECATED and must not become
production canonical persistence.

This is the one remaining deliverable ADR-0167's own "R2.1定稿" section
called out as not yet written. It must be a real, executing check, not
another frozen paragraph nobody runs — same discipline
test_no_direct_provider_calls.py already applies to the provider-call
boundary.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from backend.intelligence.agent_runtime.contracts import AgentRun
from backend.intelligence.agi_vertical_durable import (
    DurableVerticalGrowthRuntime,
    DurableVerticalLedgerAdapter,
)
from backend.intelligence.agi_vertical_runtime import EvaluationLedger

# Field names that would signal AgentRun has grown cognitive/lineage
# semantics that ADR-0167 reserves for IntelligenceRun. Matched as
# substrings against actual field names so a differently-cased or
# suffixed variant (e.g. `guardian_calibration_ref`) still trips this.
FORBIDDEN_AGENT_RUN_FIELD_SUBSTRINGS = (
    "guardian_calibration",
    "guardian_decision",
    "plan_revision",
    "revision_lineage",
    "parent_run_id",
    "reflection",
    "replan",
)


def test_agent_run_carries_no_cognitive_or_lineage_fields() -> None:
    """AgentRun is "an immutable execution result; it is not a business
    fact" per its own docstring — it must stay that way. Guardian
    calibration, plan revision lineage, and reflection/replan chains are
    IntelligenceRun's job.
    """

    field_names = {f.name for f in dataclasses.fields(AgentRun)}

    violations = [
        name
        for name in field_names
        for forbidden in FORBIDDEN_AGENT_RUN_FIELD_SUBSTRINGS
        if forbidden in name
    ]

    assert not violations, (
        f"AgentRun has grown cognitive/lineage field(s) {violations} — "
        "these belong on IntelligenceRun, not AgentRun, per ADR-0167's "
        "four-level Run Taxonomy. Field names present: "
        f"{sorted(field_names)}"
    )


def test_agent_run_declares_it_may_not_mutate_business_state() -> None:
    """The `may_mutate_business_state` property is the executable half of
    "AgentRun is not a business fact" — a caller can check it instead of
    just trusting the docstring.
    """

    run = AgentRun(
        run_id="run-1",
        request_id="request-1",
        agent_id="agent-1",
        tenant_id="tenant-1",
        family_id="family-1",
        use_case="test-use-case",
        draft=object(),  # ModelDraft not needed for this assertion
    )

    assert run.may_mutate_business_state is False


def test_production_vertical_growth_runtime_persists_through_durable_ledger() -> None:
    """EvaluationLedger must not become production canonical persistence
    (ADR-0167: "EvaluationLedger = DEPRECATED... MUST NOT become
    production canonical persistence").

    `VerticalFamilyGrowthRuntime` still uses an in-memory `EvaluationLedger`
    internally to chain `revise()`/`reflect()` within one request — that is
    accepted as ephemeral in-process staging, not a violation by itself.
    The invariant this test actually enforces is narrower and executable:
    the durability-facing wrapper (`DurableVerticalGrowthRuntime`, the
    object every production composition installs onto `app.state`) must
    route its persisted operations through the injected
    `DurableVerticalLedgerAdapter`, never through a bare `EvaluationLedger`.
    """

    class _FakeInnerRuntime:
        async def run(self, **kwargs):  # pragma: no cover - not exercised
            raise AssertionError("not called by this test")

    fake_durable_ledger = object.__new__(DurableVerticalLedgerAdapter)

    wrapper = DurableVerticalGrowthRuntime(
        _FakeInnerRuntime(),
        fake_durable_ledger,
        lambda family_id: None,
    )

    assert wrapper._ledger is fake_durable_ledger
    assert not isinstance(wrapper._ledger, EvaluationLedger), (
        "DurableVerticalGrowthRuntime's persistence-facing ledger must be "
        "a DurableVerticalLedgerAdapter, never a bare EvaluationLedger — "
        "an in-memory ledger reaching this seam would make it production "
        "canonical persistence, which ADR-0167 forbids."
    )


BARE_EVALUATION_LEDGER_CONSTRUCTION = re.compile(r"\bEvaluationLedger\(\)")
DEF_LINE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)")
DEV_NAME_HINT = re.compile(r"dev", re.IGNORECASE)


def _enclosing_function_name(lines: list[str], match_line_index: int) -> str | None:
    for line in reversed(lines[: match_line_index + 1]):
        found = DEF_LINE.match(line)
        if found:
            return found.group(1)
    return None


def test_bare_evaluation_ledger_construction_stays_confined_to_dev_wiring(
    repo_root: Path,
) -> None:
    """Bare `EvaluationLedger()` construction (no caller-supplied durable
    adapter) is legitimate inside dev/test composition functions, and
    only there. If a future production-labeled composition function
    starts constructing one directly instead of requiring an explicit
    `EvaluationLedger`/`DurableVerticalLedgerAdapter` argument from its
    caller, that is exactly the regression ADR-0167 warns against.

    This is a narrow, textual regression guard — it walks each match back
    to the nearest enclosing `def` line and checks *that function's* name
    for a "dev" hint, rather than the file's name (the two current
    legitimate call sites are dev-named functions inside otherwise
    neutrally-named modules, e.g. `agi_vertical_composition.py`'s
    `build_development_vertical_family_growth_runtime`).
    """

    backend_dir = repo_root / "backend"
    violations: list[str] = []

    for py_file in backend_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        if not BARE_EVALUATION_LEDGER_CONSTRUCTION.search(text):
            continue
        rel_path = py_file.relative_to(repo_root).as_posix()
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not BARE_EVALUATION_LEDGER_CONSTRUCTION.search(line):
                continue
            enclosing = _enclosing_function_name(lines, index)
            if enclosing is None or not DEV_NAME_HINT.search(enclosing):
                violations.append(f"{rel_path}:{index + 1} (in {enclosing!r})")

    assert not violations, (
        "bare EvaluationLedger() construction found outside a dev-named "
        f"function: {violations} — a production composition path must "
        "require its caller to supply a durable ledger explicitly, not "
        "construct an in-memory EvaluationLedger itself."
    )
