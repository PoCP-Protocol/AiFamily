"""AI Runtime isolation — the two checks `AI_NATIVE_PRINCIPLES.md` §5 listed as 待补.

That section named them explicitly and then said the quiet part out loud:
"未被检查覆盖的判据只是意图，不是护栏". Both were unimplementable while
`backend/intelligence/` held nothing but a `NotImplementedError` placeholder; the
Model Gateway is the first real code there, so they become implementable and are
implemented here.

The rule being enforced comes from `MIGRATION_PLAN_V2.md` §0 (carried forward
unrepealed) and `AI_ARCHITECTURE.md` §4.3: `may_mutate_business_state=false`; the
AI Runtime must not import a business-domain repository; it may only produce
Draft / Hypothesis / Explanation / Proposal; canonical writes happen solely through
a domain's own Named Action.

The isolation is logical, not linguistic. Both sides are Python and both live in
the same repository, so nothing but a check like this stands between "AI Runtime
proposes" and an AI Runtime module quietly opening a session and writing a family
fact.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

AI_RUNTIME_DIR = "backend/intelligence"

FORBIDDEN_IMPORT_PREFIXES = ("backend.platform.persistence",)
"""The persistence layer, banned outright: importing a UnitOfWork or session
factory is how a module acquires the ability to write canonical state without
naming any specific domain. Excluding it would leave the rule satisfiable in
letter and defeated in substance.

Other `backend.platform.*` packages are *not* forbidden. `identity`, `consent` and
`audit` are supporting primitives an AI runtime legitimately needs — in order to
know who is asking and whether consent covers it. Banning those would push AI code
into re-implementing consent, which is worse for compliance, not better.
"""

FORBIDDEN_DOMAIN_LAYER_PATTERN = re.compile(
    r"^backend\.domains\.[A-Za-z_][A-Za-z0-9_]*\.(infrastructure|application)\b"
)
r"""Domain **infrastructure and application** layers — not the whole domain.

Getting this boundary right matters, and the written rule is narrower than
"backend.domains.\*". `MIGRATION_PLAN_V2.md` §0 says the AI Runtime "不得直接
import 业务域 repository"; `AI_ARCHITECTURE.md` §4.3 restates it as "AI Runtime
全程不接触业务域的 repository/ORM 层". Neither forbids a domain *entity* type.

The distinction is the one that carries the guarantee. A domain entity is an
immutable value shape — importing `ProductDefinition` gives a module the ability to
*describe* a product, not to persist one. A repository or application command
service gives it the ability to write canonical state, which is exactly what R9
forbids. Banning entity imports as well would force the AI Runtime to maintain a
parallel copy of every domain type, and a duplicated canonical shape is an R2
violation traded for no additional safety.

Concrete case this scoping preserves: `backend/intelligence/design_copilot`
imports `backend.domains.product_intelligence.domain.entities.ProductDefinition`,
and it does so *because* `MIGRATION_MANIFEST.yaml` recorded that the previously
duplicated definition in `packages/contracts` was deleted in favour of the
domain's canonical one. A wholesale ban would flag the fix and reward the
duplication.
"""

FORBIDDEN_NAME_FRAGMENTS = ("Repository", "UnitOfWork", "SessionFactory")
"""A repository or session handle reached under any import path — including
`from backend.domains.x.domain.ports import SomeRepository`, which the layer
pattern above would miss because `domain.ports` is a legitimate layer to import
*types* from. Matched case-sensitively against imported symbol names so that a
lowercase word like `repository_module` in a path does not trigger it.
"""

PROMOTED_STATUS_LITERALS = ("VALIDATED", "APPROVED", "CONFIRMED")
"""The statuses that mean "this is now a fact". No module under
`backend/intelligence/` may assign one — that transition belongs to a domain's
Named Action with a human actor (R8/R9). Declaring them as *rejected* values is
fine, which is why the check looks for assignment rather than mere mention.
"""


def _ai_runtime_files(repo_root: Path) -> list[Path]:
    root = repo_root / AI_RUNTIME_DIR
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_ai_runtime_does_not_import_business_domains(repo_root: Path) -> None:
    """The T-06 hard red line, and `MIGRATION_PLAN_V2.md` §0's isolation rule."""
    files = _ai_runtime_files(repo_root)
    assert files, f"{AI_RUNTIME_DIR} contains no Python files — this check would vacuously pass"

    violations: list[str] = []
    for path in files:
        rel = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            names: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
                names = [alias.name for alias in node.names]
            else:
                continue

            for module in modules:
                if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    violations.append(f"{rel}:{node.lineno} imports {module}")
                elif FORBIDDEN_DOMAIN_LAYER_PATTERN.match(module):
                    violations.append(
                        f"{rel}:{node.lineno} imports domain infrastructure/application "
                        f"layer {module}"
                    )
            for name in names:
                if any(fragment in name for fragment in FORBIDDEN_NAME_FRAGMENTS):
                    violations.append(f"{rel}:{node.lineno} imports repository symbol {name!r}")

    assert not violations, (
        "AI Runtime isolation violated. Code under backend/intelligence/ must not reach a "
        "business-domain repository/ORM layer or the persistence layer: it may only produce "
        "Draft/Hypothesis/Explanation/Proposal, and canonical writes must go through the "
        "owning domain's Named Action with a human actor (R9; MIGRATION_PLAN_V2.md §0; "
        "AI_ARCHITECTURE.md §4.3). Importing a domain *entity* type is permitted — see the "
        "scoping note on FORBIDDEN_DOMAIN_LAYER_PATTERN.\n" + "\n".join(violations)
    )


def test_ai_runtime_does_not_promote_its_own_output(repo_root: Path) -> None:
    """`AI_NATIVE_PRINCIPLES.md` §5's second 待补 check.

    Assignment, not mention: a module may legitimately name these statuses in order
    to reject them (a rejection list is a guard, not a promotion). What must not
    exist is a code path that *sets* one.
    """
    violations: list[str] = []
    for path in _ai_runtime_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            if node.value is None:
                continue
            assigned = ast.unparse(node.value)
            for literal in PROMOTED_STATUS_LITERALS:
                if f'"{literal}"' in assigned or f"'{literal}'" in assigned:
                    target_src = ", ".join(ast.unparse(t) for t in targets)
                    violations.append(f"{rel}:{node.lineno} assigns {literal!r} to {target_src}")

    assert not violations, (
        "AI Runtime code assigns a promoted status. AI output starts and stays DRAFT; only "
        "a domain's Named Action with a human actor may promote it (R9, PIPL 第24条 human "
        "review path).\n" + "\n".join(violations)
    )


def test_model_gateway_output_type_cannot_mutate_business_state(repo_root: Path) -> None:
    """`may_mutate_business_state = false` as a runtime fact, checked by running it.

    A grep for the string would pass on a comment. This imports the real type and
    asserts the property, and separately asserts the class exposes no field of that
    name — because a `False`-defaulted field would satisfy the property check today
    while being overridable at construction tomorrow.
    """
    import dataclasses

    from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft

    draft = ModelDraft(
        output={},
        provenance=AiProvenance(
            provider_id="p",
            model="m",
            model_version="1",
            prompt_version="v1",
            schema_version="s1",
            context_snapshot_ref="ctx",
            latency_ms=0,
            data_class="SYNTHETIC",
            use_case="u",
        ),
    )
    assert draft.may_mutate_business_state is False
    assert draft.status == "DRAFT"

    field_names = {f.name for f in dataclasses.fields(ModelDraft)}
    assert "may_mutate_business_state" not in field_names, (
        "may_mutate_business_state is a dataclass field, so a caller can pass True at "
        "construction. It must be a read-only property so that no instance can report True."
    )


def test_model_draft_rejects_runtime_status_promotion(repo_root: Path) -> None:
    """Typing-only Literal guards are insufficient at the provider boundary."""
    from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft

    provenance = AiProvenance(
        provider_id="p",
        model="m",
        model_version="1",
        prompt_version="v1",
        schema_version="s1",
        context_snapshot_ref="ctx",
        latency_ms=0,
        data_class="SYNTHETIC",
        use_case="u",
    )
    import pytest

    with pytest.raises(ValueError, match="status must remain DRAFT"):
        ModelDraft(output={}, provenance=provenance, status="APPROVED")


def test_credentials_are_read_only_inside_the_model_gateway(repo_root: Path) -> None:
    """R7: "凭据只由 Model Gateway 读取".

    Scanning for environment reads whose variable name looks like a model
    credential. The gateway's own provider factory is the single permitted site;
    the assertion is that the set of readers is exactly that.
    """
    credential_markers = ("API_KEY", "AUTH_TOKEN", "SECRET_KEY", "ACCESS_TOKEN")
    allowed_prefix = "backend/intelligence/model_gateway/providers/"

    backend = repo_root / "backend"
    offenders: list[str] = []
    for path in backend.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith(allowed_prefix):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            source = ast.unparse(node)
            reads_env = "os.environ" in source or "getenv" in source
            if reads_env and any(marker in source for marker in credential_markers):
                offenders.append(f"{rel}:{node.lineno} {source[:90]}")

    assert not offenders, (
        "R7 violation — a model credential is read outside the Model Gateway. Credentials "
        "must be read only by backend/intelligence/model_gateway/providers/, so that "
        "provider access stays centralised (which is also the precondition for the "
        "《儿童个人信息网络保护规定》第16条 delegated-processing assessment to mean "
        "anything).\n" + "\n".join(offenders)
    )


COGNITION_MODULE_DIRS = ("backend/intelligence/context_engine",)
"""Directories holding "cognition" modules — code that decides *what to ask
a model for* and *how to validate what it returns*, as opposed to the
Model Gateway/Agent Runtime infrastructure that actually executes a
request. AIFAMILY-FIL-001 (INV-02): every generative call in production
must go through `AgentRuntime.execute()`, never a directly-held
`ModelGateway` — otherwise cognition modules quietly grow into a second,
parallel execution path alongside Agent Runtime, which is exactly the
architecture drift this test exists to catch before it compounds. As more
cognition modules are added (primary contradiction, goal proposal,
reflection, ...), add their directory here rather than special-casing each
one.
"""

MODEL_GATEWAY_IMPORT_EXEMPT_PREFIXES = (
    "backend/intelligence/model_gateway/",
    "backend/intelligence/agent_runtime/",
)
"""Infrastructure that is *allowed* to import the concrete `ModelGateway`
class: the gateway module itself, and Agent Runtime's
`gateway_port.ModelGatewayExecutionPort` adapter (the one sanctioned place
that binds a gateway+provider_id to the `AgentExecutionPort` protocol
Agent Runtime depends on structurally)."""


def _cognition_module_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for rel_dir in COGNITION_MODULE_DIRS:
        root = repo_root / rel_dir
        if not root.exists():
            continue
        files.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def test_cognition_modules_do_not_import_model_gateway_directly(repo_root: Path) -> None:
    """AIFAMILY-FIL-001 INV-02: a cognition module may build a request and
    validate a response, but it may never hold a `ModelGateway` reference
    and call it directly — that execution boundary belongs solely to
    `AgentRuntime.execute()`. Gated real-model livecheck tests are exempt
    (they live under `tests/`, not `backend/`, and are explicitly documented
    as the one sanctioned exception that calls the gateway itself to prove
    a real round trip — see `test_family_scene_001_real_gateway_livecheck.py`).
    """

    files = _cognition_module_files(repo_root)
    assert files, "no cognition module files found — this check would vacuously pass"

    violations: list[str] = []
    for path in files:
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith(MODEL_GATEWAY_IMPORT_EXEMPT_PREFIXES):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.Import):
                module = ""
                names = [alias.name for alias in node.names]
            else:
                continue
            if module.endswith("model_gateway.gateway") and "ModelGateway" in names:
                violations.append(f"{rel}:{node.lineno} imports ModelGateway directly")
            for name in names:
                if name == "ModelGateway" or name.endswith(".ModelGateway"):
                    violations.append(f"{rel}:{node.lineno} imports {name}")

    assert not violations, (
        "Single Model Execution Path violated (AIFAMILY-FIL-001 INV-02): a cognition "
        "module under backend/intelligence/context_engine/ imports the concrete "
        "ModelGateway class instead of executing through AgentRuntime. Route the call "
        "through AgentRuntime.execute() (see belief_engine.generate_hypothesis / "
        "unknown_engine.generate_unknown for the pattern) instead of holding a gateway "
        "reference.\n" + "\n".join(violations)
    )
