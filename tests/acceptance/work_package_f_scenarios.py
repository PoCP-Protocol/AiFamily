"""Work package F red-team scenarios.

This module is an executable acceptance inventory, not a business fixture and
not an implementation of any application capability.  A scenario is passing
only when its evidence is produced against the same approved integration ref,
the default composition root, real HTTP, and a fresh PostgreSQL database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EvidenceStatus = Literal["PASS", "FAIL", "BLOCKED", "NOT_RUN"]


@dataclass(frozen=True, slots=True)
class AcceptanceScenario:
    scenario_id: str
    title: str
    hard_gate: str
    required_proof: tuple[str, ...]
    forbidden_substitutes: tuple[str, ...]


APPROVED_REF = "72eec31d178e14a32aa6a05b4189c8c515119975"


SCENARIOS: tuple[AcceptanceScenario, ...] = (
    AcceptanceScenario(
        "F-01",
        "Default composition root and real HTTP",
        "The candidate starts through default create_app without dependency overrides.",
        ("git ref", "startup command", "HTTP request/response", "route provenance"),
        ("direct service call", "TestClient-only fake wiring", "manual page inspection"),
    ),
    AcceptanceScenario(
        "F-02",
        "Fresh PostgreSQL persistence",
        (
            "The scenario uses a newly created PostgreSQL database and applies "
            "the candidate migrations."
        ),
        ("database identity", "migration head", "SQL rows", "HTTP response"),
        ("SQLite", "pre-seeded shared database", "in-memory repository", "fixture-only result"),
    ),
    AcceptanceScenario(
        "F-03",
        "Cross-process restart readback",
        "A new process reads the same durable record after the first process is stopped.",
        ("process A log", "process B log", "same record/version", "database row before/after"),
        ("same-process refresh", "module reload", "deterministic recomputation"),
    ),
    AcceptanceScenario(
        "F-04",
        "Browser golden path",
        (
            "An authenticated browser completes the intended visible flow and "
            "shows the real projection."
        ),
        ("URL/title", "DOM snapshot", "screenshot", "console health", "interaction state"),
        ("route exists", "component unit test", "static screenshot", "page-source assertion"),
    ),
    AcceptanceScenario(
        "F-05",
        "Two-family differential evidence",
        (
            "Two real families with different durable evidence produce "
            "explainably different projections."
        ),
        (
            "family A seed",
            "family B seed",
            "source rows",
            "different response fields",
            "lineage explanation",
        ),
        ("hard-coded tags", "test-only injected candidate", "same fixture with renamed family"),
    ),
    AcceptanceScenario(
        "F-06",
        "Guardian four-state matrix",
        (
            "Allowed, missing, revoked/expired, and wrong-scope Guardian states "
            "are all exercised over HTTP."
        ),
        (
            "identity state",
            "consent state",
            "HTTP status",
            "safe response body",
            "provider call count",
        ),
        ("unit policy test", "header-only actor injection", "fake consent without HTTP"),
    ),
    AcceptanceScenario(
        "F-07",
        "Published Knowledge and ModelGateway provenance",
        (
            "The displayed draft is grounded in published knowledge and a "
            "gateway-bound provenance record."
        ),
        (
            "published knowledge id/version",
            "gateway route",
            "model/prompt/schema refs",
            "response lineage",
        ),
        (
            "string reason",
            "unpublished fixture",
            "direct provider call",
            "missing provenance accepted",
        ),
    ),
    AcceptanceScenario(
        "F-08",
        "Replay, deletion, and cross-scope negatives",
        (
            "Duplicate, deleted, and cross-family/tenant requests fail or replay "
            "safely without leakage."
        ),
        (
            "first response",
            "replay response",
            "deletion proof",
            "cross-scope status/body",
            "side-effect rows",
        ),
        ("single happy-path run", "same-process dict", "status-only assertion"),
    ),
)


def scenario_ids() -> tuple[str, ...]:
    """Return stable scenario identifiers for evidence tooling."""

    return tuple(scenario.scenario_id for scenario in SCENARIOS)


def empty_evidence_record(scenario: AcceptanceScenario) -> dict[str, object]:
    """Create a neutral record that cannot be mistaken for a passing result."""

    return {
        "scenario_id": scenario.scenario_id,
        "approved_ref": APPROVED_REF,
        "status": "NOT_RUN",
        "commands": [],
        "artifacts": [],
        "observations": [],
        "counterexamples": [],
        "blockers": ["No evidence collected"],
    }


__all__ = [
    "APPROVED_REF",
    "AcceptanceScenario",
    "SCENARIOS",
    "empty_evidence_record",
    "scenario_ids",
]
