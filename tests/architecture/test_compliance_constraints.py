"""Compliance hard constraints — legal obligations as CI guardrails.

`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` records constraints that are
**法定强制**, not advisory, verified verbatim against primary sources (PIPL,
《未成年人网络保护条例》,《儿童个人信息网络保护规定》). Until this file existed,
every one of them was enforced only by whoever remembered to read the doc.

That is the exact failure mode `governance/REPOSITORY_CONSTITUTION.md` R14 was
written about: the source repository declared
`AI_GATEWAY_POLICY.business_module_direct_provider_call = 'forbidden'` as an
exported constant and then violated it, because a constant is not an enforcement
mechanism.

Scope honesty: not every legal obligation is mechanically checkable. Retention
periods, DPIA record-keeping, annual compliance audits and the
"不得转委托" provider-subprocessing question are organisational duties that no
unit test can verify — those stay tracked in the doc's §11 待办 list. What *is*
checkable is checked here, strictly.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

BACKEND_DIR = "backend"

# ---------------------------------------------------------------------------
# R9 red line + 商业设计红线: no scoring, no ranking, anywhere.
# ---------------------------------------------------------------------------
# Sources that agree on this independently:
#   * REPOSITORY_CONSTITUTION.md R9 (不做家庭总分 / 不做家庭排名)
#   * FELS legacy semantics: family_score -> RETIRE, ranking -> RETIRE
#   * COMPLIANCE_HARD_CONSTRAINTS.md §12 (与商业战略的冲突记录)
#   * backend/domains/membership/domain/policies.py FORBIDDEN_TIER_FIELD_TOKENS,
#     whose comment claimed "Enforced by a guardrail test that reflects over
#     every model" — that test did not exist. This is it, and it is repo-wide
#     rather than membership-only, because the red line is not membership's.
# R9 forbids scoring and ranking *families and children* — not scoring in general.
# Getting this scope right matters: `ProductZoneAssessment.commodity_score /
# advantage_score / unique_score` scores a *product's* competitive zone, which is
# exactly what the 三区方法论 (同质区/优势区/独占区) in
# docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md §8 requires. Banning the word
# "score" outright would forbid the strategy the platform is built on, while
# doing nothing extra to protect families.
#
# So the rule is two-part:
#   1. Names retired outright by the FELS legacy semantics — these are the exact
#      shapes that must never reappear (family_score -> RETIRE, ranking -> RETIRE).
#   2. Any field combining a family/person subject with a scoring verb.
RETIRED_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "family_score",
        "ranking",
        "family_ranking",
        "total_score",
        "leaderboard",
        "family_rank",
        "child_score",
        "child_rank",
    }
)

SUBJECT_TOKENS: frozenset[str] = frozenset(
    {"family", "child", "parent", "guardian", "student", "member"}
)

SCORING_TOKENS: frozenset[str] = frozenset(
    {"score", "rank", "ranking", "grade", "percentile", "leaderboard", "progress_pct"}
)

# Fields that pair a subject token with a scoring token but are legitimate.
# Each needs a reason — an unexplained exemption is how a red line erodes.
FIELD_TOKEN_EXEMPTIONS: dict[str, str] = {
    # "upgrade"/"downgrade" merely contain "grade" as a substring.
    "membership_upgraded_at": "substring of 'upgrade', not an academic grade",
    "membership_downgraded_at": "substring of 'downgrade', not an academic grade",
}


def _python_files(root: Path) -> list[Path]:
    backend = root / BACKEND_DIR
    if not backend.exists():
        return []
    return [p for p in backend.rglob("*.py") if "__pycache__" not in p.parts]


def _annotated_field_names(tree: ast.Module) -> list[tuple[str, int]]:
    """Every annotated class attribute — covers pydantic models, dataclasses and
    SQLAlchemy declarative columns alike, which is why reflection is done on the
    AST rather than by importing and inspecting `model_fields`."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                found.append((stmt.target.id, stmt.lineno))
    return found


def test_no_scoring_or_ranking_fields_anywhere(repo_root: Path) -> None:
    """R9 — the platform must not compute, store or expose a family score or ranking.

    This is the guardrail `membership/domain/policies.py:27` promised and never
    had. It reflects over every annotated field in every backend model.
    """
    violations: list[str] = []
    for path in _python_files(repo_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - a syntax error is another test's problem
            continue
        rel = path.relative_to(repo_root).as_posix()
        for field_name, lineno in _annotated_field_names(tree):
            if field_name in FIELD_TOKEN_EXEMPTIONS:
                continue
            lowered = field_name.lower()

            if lowered in RETIRED_FIELD_NAMES:
                violations.append(
                    f"{rel}:{lineno} field {field_name!r} is a retired legacy shape "
                    "(family_score / ranking were RETIRE-classified and must never return)"
                )
                continue

            has_subject = any(token in lowered for token in SUBJECT_TOKENS)
            scoring_hit = next((t for t in SCORING_TOKENS if t in lowered), None)
            if has_subject and scoring_hit:
                violations.append(
                    f"{rel}:{lineno} field {field_name!r} scores a family/person "
                    f"subject (matched {scoring_hit!r})"
                )

    assert not violations, (
        "R9 violation — the platform does not score or rank families or children. "
        "Scoring a product/strategy is fine (see 三区方法论); scoring a family is not. "
        "See governance/REPOSITORY_CONSTITUTION.md R9 and "
        "docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md §12.\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# PIPL 24/73 — AI evaluation output is an automated decision.
# ---------------------------------------------------------------------------
# Consequence for code: AI-produced records start life as DRAFT/PROPOSED and no
# code path may promote them without a human actor. The source repository's
# `dev-core-growth.service.ts` shipped `model_gateway: 'NOOP_NOT_INVOKED'` in its
# response body precisely because it had no such discipline to rely on.
AI_PROMOTED_STATUSES = ("VALIDATED", "APPROVED", "CONFIRMED")
AI_ACTOR_PREFIX = "ai:"


def test_ai_actor_prefix_is_rejected_somewhere(repo_root: Path) -> None:
    """R9 — an `ai:`-prefixed actor must be refused at a domain boundary.

    Asserting the *mechanism exists* rather than enumerating call sites: if no
    module anywhere checks for the AI actor prefix, then nothing stops AI from
    writing canonical facts, whatever the documents say.
    """
    checkers: list[str] = []
    for path in _python_files(repo_root):
        text = path.read_text(encoding="utf-8")
        if AI_ACTOR_PREFIX in text and ("raise" in text or "assert" in text):
            checkers.append(path.relative_to(repo_root).as_posix())

    assert checkers, (
        "No module enforces the `ai:` actor prefix rejection. R9 requires that AI "
        "output never becomes a canonical fact automatically; that needs a real "
        "guard, not a documented intention."
    )


def test_no_automatic_promotion_of_ai_output(repo_root: Path) -> None:
    """No code path may set an AI-generated record to VALIDATED/APPROVED without
    a human actor in scope.

    Heuristic but load-bearing: flags assignments that set one of the promoted
    statuses inside a function that has no human-actor parameter. The
    product_intelligence domain is the reference implementation —
    `validate_growth_hypothesis` takes `human_actor` explicitly and rejects
    `ai:` prefixes.
    """
    suspicious: list[str] = []
    # `context` counts: an ActorContext carries actor_id/actor_type, and the
    # product_intelligence zone commands gate on `context.actor_type == "HUMAN"`
    # before any load. Requiring a parameter literally named `human_actor` would
    # flag correct code for choosing a different — better — signature.
    human_markers = (
        "human_actor",
        "decided_by",
        "actor",
        "approved_by",
        "confirmed_by",
        "context",
    )

    for path in _python_files(repo_root):
        # Test modules assert *about* promotion (both that a human may and that AI
        # may not). Scanning them would flag the guard for being tested.
        if path.name.startswith("test_") or "tests" in path.parts:
            continue
        # Query modules read and filter by status; they cannot promote anything.
        if path.name.endswith("_queries.py") or path.name == "queries.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arg_names = {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
            if any(marker in " ".join(arg_names) for marker in human_markers):
                continue  # a human is named in the signature — out of scope here
            body_src = ast.unparse(node)
            for promoted in AI_PROMOTED_STATUSES:
                if f'"{promoted}"' in body_src or f"'{promoted}'" in body_src:
                    rel = path.relative_to(repo_root).as_posix()
                    suspicious.append(
                        f"{rel}:{node.lineno} {node.name}() references {promoted!r} "
                        "with no human actor in its signature"
                    )
                    break

    assert not suspicious, (
        "Possible automatic promotion of AI output (PIPL 24 requires a human review "
        "path; R9 forbids AI output becoming fact automatically):\n" + "\n".join(suspicious)
    )


# ---------------------------------------------------------------------------
# 儿童个人信息网络保护规定 9/10/14 — consent must be per-purpose.
# ---------------------------------------------------------------------------


def test_consent_is_scoped_per_purpose(repo_root: Path) -> None:
    """A blanket "consent for everything" must not be representable.

    《儿童个人信息网络保护规定》第10条 requires purpose-specific disclosure and a
    refusal option; PIPL 第29条 requires 单独同意 for sensitive data. A single
    catch-all purpose value would satisfy neither.
    """
    models = repo_root / "backend/platform/consent/models.py"
    assert models.is_file(), "backend/platform/consent/models.py is missing"

    tree = ast.parse(models.read_text(encoding="utf-8"))
    purposes: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ConsentPurpose":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
                    purposes.append(stmt.targets[0].id)

    assert len(purposes) >= 2, (
        f"ConsentPurpose declares {len(purposes)} purpose(s): {purposes}. Consent must "
        "be grantable per purpose; a single value collapses to blanket consent."
    )

    banned = {"ALL", "ANY", "EVERYTHING", "BLANKET", "GENERAL"}
    offending = sorted(set(purposes) & banned)
    assert not offending, (
        f"ConsentPurpose contains blanket value(s) {offending} — a catch-all purpose "
        "defeats per-purpose consent."
    )


def test_consent_gate_does_not_cache(repo_root: Path) -> None:
    """Withdrawal must take effect immediately.

    `FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` §10 called this out explicitly:
    consent is re-checked at every step, never cached across a flow. A memoised
    gate would silently keep serving a withdrawn subject.
    """
    gate = repo_root / "backend/platform/consent/gate.py"
    assert gate.is_file(), "backend/platform/consent/gate.py is missing"

    source = gate.read_text(encoding="utf-8")
    caching_markers = ["lru_cache", "cached_property", "@cache", "functools.cache"]
    found = [marker for marker in caching_markers if marker in source]
    assert not found, (
        f"ConsentGate uses caching ({found}); a withdrawn consent would keep passing. "
        "Withdrawal must take effect immediately."
    )


# ---------------------------------------------------------------------------
# 未成年人网络保护条例 24(3) — absolute prohibition on automated
# decision-making commercial marketing directed at minors.
# ---------------------------------------------------------------------------

COMMERCIAL_MARKETING_TERMS = (
    "recommend_product",
    "push_offer",
    "marketing",
    "promote_offer",
    "upsell",
)
CHILD_TARGET_TERMS = ("child", "minor", "student")


def test_no_commercial_marketing_targeted_at_children(repo_root: Path) -> None:
    """《未成年人网络保护条例》第24条第3款 is an absolute prohibition, with no
    exception and no age subdivision.

    Any function whose name pairs a commercial-marketing verb with a child-facing
    target is a violation by construction. The business design this blocks is
    real: the 新商业模式 PPT proposed 积分商城 / 成长拼团 / 会员权益 flows, and
    those must be parent-facing only.
    """
    violations: list[str] = []
    for path in _python_files(repo_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name.lower()
            if any(term in name for term in COMMERCIAL_MARKETING_TERMS) and any(
                term in name for term in CHILD_TARGET_TERMS
            ):
                rel = path.relative_to(repo_root).as_posix()
                violations.append(f"{rel}:{node.lineno} {node.name}()")

    assert not violations, (
        "Absolute prohibition violated — 《未成年人网络保护条例》第24条第3款 forbids "
        "automated-decision commercial marketing to minors. Commercial flows must be "
        "guardian-facing.\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# 儿童个人信息网络保护规定 20 — deletion covers derived data.
# ---------------------------------------------------------------------------
# Embeddings derived per-child remain identifiable child personal information,
# so a vector store without subject-scoped deletion is a standing legal defect.
# No vector storage exists yet; this test activates the moment one appears,
# which is the point — the constraint is cheapest to honour before the store is
# chosen. pgvector's row-level delete satisfies it; a rebuild-only index does not.
VECTOR_MARKERS = ("pgvector", "embedding", "vector_store", "faiss", "chromadb", "qdrant")
DELETION_MARKERS = ("delete_by_subject", "delete_for_subject", "purge_subject", "cascade_delete")


def test_vector_storage_supports_subject_scoped_deletion(repo_root: Path) -> None:
    modules_with_vectors: list[Path] = []
    for path in _python_files(repo_root):
        text = path.read_text(encoding="utf-8").lower()
        # A mention inside a comment or docstring is design discussion, not storage.
        code_lines = [
            line for line in text.splitlines() if not line.strip().startswith(("#", '"', "'"))
        ]
        code = "\n".join(code_lines)
        if any(marker in code for marker in VECTOR_MARKERS):
            modules_with_vectors.append(path)

    if not modules_with_vectors:
        pytest.skip("no vector/embedding storage exists yet — constraint not yet applicable")

    missing: list[str] = []
    for path in modules_with_vectors:
        text = path.read_text(encoding="utf-8")
        if not any(marker in text for marker in DELETION_MARKERS):
            missing.append(path.relative_to(repo_root).as_posix())

    assert not missing, (
        "《儿童个人信息网络保护规定》第20条: deletion must cover derived data. "
        "Per-child embeddings are still identifiable child personal information, so "
        "vector storage needs subject-scoped deletion "
        f"(one of {DELETION_MARKERS}):\n" + "\n".join(missing)
    )


# ---------------------------------------------------------------------------
# R7 / 儿童个人信息网络保护规定 16 — provider access is centralised.
# ---------------------------------------------------------------------------


def test_no_direct_provider_sdk_outside_model_gateway(repo_root: Path) -> None:
    """R7, reinforced by the 不得转委托 constraint.

    Centralising provider calls is not only architectural tidiness: 第16条 makes
    delegated processing a compliance matter (assessment, agreement, no
    sub-delegation), and that is unenforceable if arbitrary modules call
    providers directly. Complements `test_no_direct_provider_calls.py` by also
    catching direct HTTP to provider hosts.
    """
    provider_hosts = re.compile(
        r"api\.(openai|anthropic|deepseek)\.com|generativelanguage\.googleapis\.com"
    )
    allowed_prefix = "backend/intelligence/model_gateway"

    violations: list[str] = []
    for path in _python_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith(allowed_prefix):
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if provider_hosts.search(line):
                violations.append(f"{rel}:{lineno}")

    assert not violations, (
        "R7 violation — provider endpoints reached outside the Model Gateway. "
        "The source repository did exactly this in "
        "`orchestration/llm-gateway/family-llm-gateway.service.ts:58-63`, violating its "
        "own declared policy.\n" + "\n".join(violations)
    )
