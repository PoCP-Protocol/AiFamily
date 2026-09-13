"""ADR-0172 — Deterministic Truth Projection + Generative Cognition.

Enforces the boundary the project owner froze after the WM-001~003
generative-vs-deterministic decision: FACT atoms are produced only by
deterministic projection of authoritative domain sources. Generative models
belong to the Cognition Layer (WM-004+), never inside a FACT adapter.

Four checks, per ADR-0172 Enforcement §Test A-D:
  A. No source adapter imports model_gateway or a provider SDK.
  B. AI-cannot-assert-FACT is covered by an existing test somewhere in the
     suite — this file asserts those tests still exist, so a future refactor
     cannot silently delete the regression coverage.
  C. Projecting the same authoritative source twice through the same adapter
     yields identical FACT atoms (except atom_id, which the caller assigns).
  D. No FACT adapter function accepts a WorldStateAtom as input — "inference
     cannot self-promote into fact" is a structural property (no such
     function exists), not a runtime check that could be forgotten.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import fields
from datetime import datetime
from pathlib import Path

from backend.domains.family.domain.entities import FamilyRelationship
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.source_adapters import (
    family_need_outcome_source_adapter,
    family_need_source_adapter,
    family_source_adapter,
    growth_source_adapter,
)
from backend.intelligence.context_engine.source_adapters.family_source_adapter import (
    family_relationship_atom,
)
from backend.intelligence.context_engine.world_state import WorldStateAtom

SOURCE_ADAPTERS_RELATIVE_PATH = "backend/intelligence/context_engine/source_adapters"


def _scope() -> ContextScope:
    return ContextScope(
        tenant_id="tenant-1",
        region_id="CN",
        family_id="family-1",
        subject_ids=("child-1", "mother-1"),
        purpose="family_growth_support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=DataClass.FAMILY_PRIVATE_TEXT,
        locale="zh-CN",
        deletion_ref="delete:family-1",
        correlation_id="corr-1",
        causation_id="cause-1",
    )


PROVIDER_PATTERNS = [
    re.compile(r"\bimport\s+openai\b"),
    re.compile(r"\bimport\s+anthropic\b"),
    re.compile(r"\bfrom\s+openai\b"),
    re.compile(r"\bfrom\s+anthropic\b"),
    re.compile(r"model_gateway"),
    re.compile(r"\bopenai\.[A-Za-z_]"),
    re.compile(r"\banthropic\.[A-Za-z_]"),
]

FACT_ADAPTER_MODULES = [
    family_source_adapter,
    family_need_source_adapter,
    growth_source_adapter,
    family_need_outcome_source_adapter,
]


# --- Test A: no ModelGateway / provider SDK dependency ---------------------


def test_fact_adapters_have_no_model_gateway_or_provider_dependency(repo_root: Path) -> None:
    adapters_dir = repo_root / SOURCE_ADAPTERS_RELATIVE_PATH
    violations: list[str] = []
    for py_file in sorted(adapters_dir.glob("*.py")):
        text = py_file.read_text(encoding="utf-8")
        for pattern in PROVIDER_PATTERNS:
            if pattern.search(text):
                violations.append(f"{py_file.name}: matched /{pattern.pattern}/")

    assert not violations, (
        "ADR-0172 violation: FACT adapter depends on a model provider / "
        "ModelGateway, breaking deterministic truth projection:\n" + "\n".join(violations)
    )


# --- Test B: AI-cannot-assert-FACT regression coverage still exists --------


def test_ai_cannot_assert_fact_regression_tests_still_exist(repo_root: Path) -> None:
    kernel_test = repo_root / "tests/intelligence/context_engine/test_world_state_kernel.py"
    repository_test = (
        repo_root / "tests/intelligence/context_engine/test_postgres_world_state_repository.py"
    )
    assert kernel_test.exists(), "AI-cannot-assert-FACT kernel test file was deleted"
    assert repository_test.exists(), "AI-cannot-assert-FACT repository test file was deleted"

    kernel_text = kernel_test.read_text(encoding="utf-8")
    repository_text = repository_test.read_text(encoding="utf-8")
    assert "AI_CANNOT_ASSERT_THIS_EPISTEMIC_KIND" in kernel_text or "ai_cannot" in kernel_text, (
        "Kernel test no longer covers the AI-cannot-assert-FACT invariant"
    )
    constraint_test_name = "test_ai_asserted_fact_is_rejected_at_the_database_check_constraint"
    assert constraint_test_name in repository_text, (
        "Repository test no longer covers the database CHECK constraint"
    )


# --- Test C: deterministic rebuild (same source -> same semantic FACT) -----


def test_projecting_the_same_source_twice_yields_identical_fact_semantics() -> None:
    relationship = FamilyRelationship(
        relationship_id="rel-determinism-1",
        family_id="family-1",
        person_a_id="child-1",
        person_b_id="mother-1",
        relationship_type="PARENT_CHILD",
        created_at=datetime(2026, 9, 13, 12, 0, 0),
    )
    first = family_relationship_atom(relationship, scope=_scope(), atom_id="rebuild-1")
    second = family_relationship_atom(relationship, scope=_scope(), atom_id="rebuild-2")

    first_semantic = {f.name: getattr(first, f.name) for f in fields(first) if f.name != "atom_id"}
    second_semantic = {
        f.name: getattr(second, f.name) for f in fields(second) if f.name != "atom_id"
    }
    assert first_semantic == second_semantic, (
        "ADR-0172 violation: same authoritative source produced two "
        "semantically different FACT atoms — full rebuild would not be "
        "stable"
    )


# --- Test D: no FACT adapter accepts a WorldStateAtom as input -------------


def test_no_fact_adapter_accepts_a_world_state_atom_as_input() -> None:
    violations: list[str] = []
    for module in FACT_ADAPTER_MODULES:
        for name, func in inspect.getmembers(module, inspect.isfunction):
            if func.__module__ != module.__name__:
                continue
            hints = inspect.signature(func).parameters
            for param_name, param in hints.items():
                annotation = param.annotation
                if annotation is WorldStateAtom or annotation == "WorldStateAtom":
                    violations.append(f"{module.__name__}.{name}(param={param_name})")

    assert not violations, (
        "ADR-0172 violation: a FACT adapter function accepts a WorldStateAtom "
        "as input — this would allow an inference (HYPOTHESIS/SYSTEM_INFERENCE) "
        "to self-promote into a FACT, which must remain structurally "
        f"impossible:\n{violations}"
    )
