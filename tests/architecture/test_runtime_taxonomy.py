"""ADR-0167: enforce run ownership without claiming R2 runtime convergence.

The legacy cognitive carrier is checked now; future IntelligenceRun declarations
join the same guard automatically. The one existing production ledger dependency
is explicit debt, not a zero-caller claim. No model, database or tool is invoked.
"""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.apps.family_api.production_vertical_family_growth_wiring import (
    ProductionVerticalFamilyGrowthComposition,
)
from backend.intelligence.agent_runtime.contracts import AgentRun
from backend.intelligence.agent_runtime.persistence import AgentRunRecord, AgentRunRow
from backend.intelligence.agi_vertical_runtime import EvaluationLedger, EvaluationLedgerEntry
from backend.intelligence.agi_vertical_runtime import VerticalFamilyGrowthRuntime as VerticalRuntime
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort
from backend.intelligence.experience.runs import RunCheckpoint, RunEvent, RunSnapshot

COGNITIVE_FIELDS = frozenset(
    {
        "guardian_calibration",
        "guardian_decisions",
        "guardian_decision",
        "parent_intelligence_run_id",
        "parent_run_id",
        "revision_lineage",
        "plan_revision",
        "plan_revision_id",
        "plan_revision_lineage",
        "reflection_lineage",
        "reflection_refs",
        "world_state_ref",
    }
)
PROVIDER_FIELDS = frozenset(
    {
        "token_usage",
        "usage",
        "token_accounting",
        "provider_token_accounting",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "provider_retry",
        "provider_retries",
        "retry_count",
        "raw_provider_response",
        "provider_response",
    }
)
LEGACY_MODULE = "backend.intelligence.agi_vertical_runtime"
LEGACY_LEDGER = f"{LEGACY_MODULE}.EvaluationLedger"
# R2.6 removes these old implementation/dev references after switching callers.
LEGACY_FILES = frozenset(
    {
        "backend/intelligence/agi_vertical_runtime.py",
        "backend/intelligence/agi_vertical_composition.py",
        "backend/intelligence/agi_vertical_dev_wiring.py",
    }
)
# R2.3/R2.6 must REMOVE this debt, never expand it. These are one import and one
# annotation, not permission to install an in-memory canonical production store.
PRODUCTION_DEBT_FILE = "backend/apps/family_api/production_vertical_family_growth_wiring.py"


@pytest.mark.parametrize("record", [AgentRun, AgentRunRecord, AgentRunRow])
def test_agent_run_does_not_own_cognitive_state(record: type) -> None:
    names = (
        set(record.__table__.columns.keys())
        if record is AgentRunRow
        else {item.name for item in fields(record)}
    )
    assert names, "The technical record guard must inspect a real schema"
    assert not names & COGNITIVE_FIELDS, (record.__name__, names & COGNITIVE_FIELDS)


@pytest.mark.parametrize("record", [EvaluationLedgerEntry, RunEvent, RunCheckpoint, RunSnapshot])
def test_existing_cognitive_carriers_do_not_own_provider_accounting(record: type) -> None:
    names = {item.name for item in fields(record)}
    assert names
    assert not names & PROVIDER_FIELDS, (record.__name__, names & PROVIDER_FIELDS)


def _declared_members(node: ast.ClassDef) -> set[str]:
    """Check declared fields, properties and self attributes, not nested drafts."""
    names: set[str] = set()
    for statement in node.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(statement.name)
        for item in ast.walk(statement):
            if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
                names.add(item.id)
            if (
                isinstance(item, ast.Attribute)
                and isinstance(item.ctx, ast.Store)
                and isinstance(item.value, ast.Name)
                and item.value.id == "self"
            ):
                names.add(item.attr)
    return names


def test_run_declarations_keep_their_layer(repo_root: Path) -> None:
    checked: set[str] = set()
    for path in (repo_root / "backend/intelligence").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name.startswith("IntelligenceRun"):
                forbidden = PROVIDER_FIELDS
            elif node.name in {"AgentRun", "AgentRunRecord", "AgentRunRow"}:
                forbidden = COGNITIVE_FIELDS
            else:
                continue
            checked.add(node.name)
            assert not _declared_members(node) & forbidden, (path, node.name)
    # IntelligenceRun is not implemented in R2.1. Do not skip this guard or
    # pretend future declarations were tested; anchor it to existing classes.
    assert {"AgentRun", "AgentRunRecord", "AgentRunRow"} <= checked


@pytest.mark.parametrize("name", ["guardian_calibration", "plan_revision_lineage", "total_tokens"])
@pytest.mark.parametrize(
    "declaration", ["{name}: str", "def __init__(self):\n        self.{name} = 1"]
)
def test_member_guard_detects_forbidden_declarations(name: str, declaration: str) -> None:
    node = ast.parse("class Run:\n    " + declaration.format(name=name)).body[0]
    assert isinstance(node, ast.ClassDef)
    assert name in _declared_members(node)


def _ledger_references(source: str) -> list[tuple[int, int]]:
    """Resolve direct/module imports and assignment aliases; ignore comments."""
    tree = ast.parse(source)
    aliases: dict[str, str] = {}
    references: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                qualified = f"{node.module}.{alias.name}"
                aliases[alias.asname or alias.name] = qualified
                if qualified == LEGACY_LEDGER or (
                    node.module == LEGACY_MODULE and alias.name == "*"
                ):
                    references.append((node.lineno, node.col_offset))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )

    def resolve(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{resolve(node.value)}.{node.attr}"
        return ""

    # Fixed point supports aliases declared before/after their referenced alias.
    for _ in range(len(list(ast.walk(tree)))):
        previous = dict(aliases)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and resolve(node.value) == LEGACY_LEDGER:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = LEGACY_LEDGER
        if aliases == previous:
            break
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Name, ast.Attribute))
            and isinstance(node.ctx, ast.Load)
            and resolve(node) == LEGACY_LEDGER
        ):
            references.append((node.lineno, node.col_offset))
    return references


def _legacy_annotation_debt(source: str) -> set[tuple[int, int]]:
    """Permit only the existing import and builder argument, never a call."""
    allowed = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == LEGACY_MODULE
            and any(a.name == "EvaluationLedger" and a.asname is None for a in node.names)
        ):
            allowed.add((node.lineno, node.col_offset))
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "build_sql_production_vertical_family_growth_composition"
        ):
            for argument in node.args.kwonlyargs:
                annotation = argument.annotation
                if (
                    argument.arg == "ledger"
                    and isinstance(annotation, ast.Name)
                    and annotation.id == "EvaluationLedger"
                ):
                    allowed.add((annotation.lineno, annotation.col_offset))
    return allowed


def test_deprecated_ledger_cannot_gain_production_wiring(repo_root: Path) -> None:
    violations = {}
    for path in (repo_root / "backend").rglob("*.py"):
        relative = path.relative_to(repo_root).as_posix()
        if relative in LEGACY_FILES:
            continue
        source = path.read_text(encoding="utf-8")
        references = set(_ledger_references(source))
        allowed = _legacy_annotation_debt(source) if relative == PRODUCTION_DEBT_FILE else set()
        if references - allowed:
            violations[relative] = sorted(references - allowed)
    assert not violations, f"Deprecated EvaluationLedger dependency expanded: {violations}"


@pytest.mark.parametrize(
    "source",
    [
        f"from {LEGACY_MODULE} import EvaluationLedger as Store\nStore()",
        f"import {LEGACY_MODULE} as old\nold.EvaluationLedger()",
        f"import {LEGACY_MODULE}\n{LEGACY_LEDGER}()",
        f"from {LEGACY_MODULE} import EvaluationLedger\nStore = EvaluationLedger\nStore()",
        f"from {LEGACY_MODULE} import *\nEvaluationLedger()",
    ],
)
def test_ledger_guard_detects_aliases(source: str) -> None:
    assert _ledger_references(source)


def test_ledger_guard_does_not_confuse_the_unrelated_evaluation_protocol() -> None:
    assert not _ledger_references(
        "from backend.intelligence.experience.multimodal_eval import EvaluationLedger\n"
        "def evaluate(ledger: EvaluationLedger): pass"
    )


def test_legacy_annotation_cannot_be_replaced_by_a_constructor() -> None:
    source = (
        f"from {LEGACY_MODULE} import EvaluationLedger\n"
        "def build_sql_production_vertical_family_growth_composition(*, ledger: object):\n"
        "    return EvaluationLedger()\n"
    )
    assert set(_ledger_references(source)) - _legacy_annotation_debt(source)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_production_rejects_process_local_ledger_as_durable_store(environment: str) -> None:
    factory = async_sessionmaker()
    broker = Mock(spec=AsyncContextBrokerPort, durability_mode="DURABLE", session_factory=factory)
    runtime = Mock(
        spec=VerticalRuntime,
        context_durability_mode="DURABLE",
        context_port=broker,
        _gateway=Mock(),
        _context=broker,
        _knowledge=Mock(),
        _feedback=Mock(),
        _consent=Mock(),
    )
    with pytest.raises(TypeError, match="durable_ledger must be a DurableVerticalLedgerAdapter"):
        ProductionVerticalFamilyGrowthComposition(
            environment=environment,
            session_factory=factory,
            runtime=runtime,
            context_broker=broker,
            durable_ledger=EvaluationLedger(),
            scope_factory=Mock(),
        )
