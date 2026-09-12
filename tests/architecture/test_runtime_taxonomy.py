"""Executable boundaries for the Family AGI run taxonomy.

ADR-0167 separates a provider execution (``AgentRun``) from a future cognitive
episode (``IntelligenceRun``).  The latter is not implemented on the current
main ref, while the legacy vertical runtime still uses ``EvaluationLedger``.
These checks therefore enforce the boundary that is true today and ratchet the
legacy dependency so it cannot spread while R2 convergence is in progress.
"""

from __future__ import annotations

import ast
from pathlib import Path

AI_RUNTIME_DIR = Path("backend/intelligence")
BACKEND_DIR = Path("backend")
AGENT_RUN_CONTRACTS = Path("backend/intelligence/agent_runtime/contracts.py")
AGENT_RUN_PERSISTENCE = Path("backend/intelligence/agent_runtime/persistence.py")

COGNITIVE_LINEAGE_FIELDS = {
    "goal_ref",
    "guardian_calibration",
    "guardian_decisions",
    "parent_intelligence_run_id",
    "plan_ref",
    "plan_revision",
    "reflection_refs",
    "revision_lineage",
    "world_state_ref",
}

PROVIDER_ACCOUNTING_FIELDS = {
    "completion_tokens",
    "estimated_cost",
    "input_tokens",
    "model_version",
    "output_tokens",
    "provider_id",
    "raw_provider_response",
    "retry_count",
    "token_usage",
    "total_tokens",
}

# Current debt on origin/main@7780b4cd.  R2.3/R2.6 must shrink this set; adding
# another production caller is an architecture regression.
ALLOWED_EVALUATION_LEDGER_PRODUCTION_USERS = {
    "backend/apps/family_api/production_vertical_family_growth_wiring.py",
    "backend/intelligence/agi_vertical_composition.py",
    "backend/intelligence/agi_vertical_dev_wiring.py",
    "backend/intelligence/agi_vertical_runtime.py",
}


def _class_field_names(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            names.add(statement.target.id)
        elif isinstance(statement, ast.Assign):
            names.update(target.id for target in statement.targets if isinstance(target, ast.Name))
    return names


def _production_python_files(repo_root: Path) -> list[Path]:
    return sorted(
        path for path in (repo_root / BACKEND_DIR).rglob("*.py") if "__pycache__" not in path.parts
    )


def _named_class(repo_root: Path, path: Path, class_name: str) -> ast.ClassDef:
    tree = ast.parse((repo_root / path).read_text(encoding="utf-8"))
    matches = [
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    assert len(matches) == 1, f"expected exactly one {class_name} in {path.as_posix()}"
    return matches[0]


def test_agent_run_remains_a_technical_execution_record(repo_root: Path) -> None:
    """AgentRun must not absorb Guardian, Goal, Plan or Reflection lineage."""

    run_contracts = (
        (AGENT_RUN_CONTRACTS, "AgentRun"),
        (AGENT_RUN_PERSISTENCE, "AgentRunRecord"),
    )
    for path, class_name in run_contracts:
        overlap = _class_field_names(_named_class(repo_root, path, class_name)) & (
            COGNITIVE_LINEAGE_FIELDS
        )
        assert not overlap, (
            f"{class_name} owns cognitive lineage fields {sorted(overlap)}. "
            "Those belong to IntelligenceRun; AgentRun is one technical execution."
        )


def test_intelligence_run_never_owns_provider_accounting(repo_root: Path) -> None:
    """Any present or future IntelligenceRun contract stays provider-neutral."""

    violations: list[str] = []
    for path in sorted((repo_root / AI_RUNTIME_DIR).rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "class IntelligenceRun" not in source:
            continue
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not node.name.startswith("IntelligenceRun"):
                continue
            overlap = _class_field_names(node) & PROVIDER_ACCOUNTING_FIELDS
            if overlap:
                rel = path.relative_to(repo_root).as_posix()
                violations.append(f"{rel}:{node.lineno} -> {sorted(overlap)}")

    assert not violations, (
        "IntelligenceRun is a provider-neutral cognitive episode. Token usage, provider "
        "retry details and raw provider responses belong to AgentRun/GatewayAttempt:\n"
        + "\n".join(violations)
    )


def test_evaluation_ledger_production_dependency_cannot_spread(repo_root: Path) -> None:
    """Ratchet the legacy ledger until R2 absorbs and deletes its callers."""

    users: set[str] = set()
    for path in _production_python_files(repo_root):
        source = path.read_text(encoding="utf-8")
        if "EvaluationLedger" not in source:
            continue
        rel = path.relative_to(repo_root).as_posix()
        is_legacy_definition = rel == "backend/intelligence/agi_vertical_runtime.py"
        imports_legacy_ledger = (
            "from backend.intelligence.agi_vertical_runtime import" in source
            and "EvaluationLedger" in source
        )
        if not is_legacy_definition and not imports_legacy_ledger:
            continue
        tree = ast.parse(source)
        uses_symbol = any(
            (isinstance(node, ast.Name) and node.id == "EvaluationLedger")
            or (isinstance(node, ast.Attribute) and node.attr == "EvaluationLedger")
            for node in ast.walk(tree)
        )
        if uses_symbol:
            users.add(rel)

    unexpected = users - ALLOWED_EVALUATION_LEDGER_PRODUCTION_USERS
    assert not unexpected, (
        "Legacy EvaluationLedger gained new production users. R2 requires migration toward "
        "AgentRun + IntelligenceRun, not another ledger caller:\n" + "\n".join(sorted(unexpected))
    )
    assert users <= ALLOWED_EVALUATION_LEDGER_PRODUCTION_USERS
