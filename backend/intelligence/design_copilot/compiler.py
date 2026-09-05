"""Deterministic Product Factory compiler.

The compiler is a pure design-time validator. It consumes a product-like
object (normally Product Intelligence ``ProductDefinition``) through
attribute access and an injected immutable catalog. It never imports a
business repository, calls a model/provider, or persists a result.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.domains.product_intelligence.domain.entities import ProductDefinition


class CompilerError(ValueError):
    """Raised for invalid compiler context construction."""


def _freeze(value: Any) -> Any:
    """Recursively freeze JSON-like catalog containers."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _catalog_map(value: Mapping[str, Any] | None, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise CompilerError(f"{field_name}_MUST_BE_MAPPING")
    return _freeze(value)


@dataclass(frozen=True, slots=True)
class CompilerCatalog:
    """Versioned validation inputs; no default entry is trusted implicitly."""

    components: Mapping[str, Any] = field(default_factory=dict)
    skills: Mapping[str, Any] = field(default_factory=dict)
    ai_use_cases: Mapping[str, Any] = field(default_factory=dict)
    resources: Mapping[str, Any] = field(default_factory=dict)
    costs: Mapping[str, Any] = field(default_factory=dict)
    evaluations: Mapping[str, Any] = field(default_factory=dict)
    slas: Mapping[str, Any] = field(default_factory=dict)
    context_boundaries: Mapping[str, Any] = field(default_factory=dict)
    safety_policies: Mapping[str, Any] = field(default_factory=dict)
    human_gates: Mapping[str, Any] = field(default_factory=dict)
    workflows: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "components",
            "skills",
            "ai_use_cases",
            "resources",
            "costs",
            "evaluations",
            "slas",
            "context_boundaries",
            "safety_policies",
            "human_gates",
            "workflows",
            "compatibility",
        ):
            object.__setattr__(self, name, _catalog_map(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class CompilerContext:
    """Immutable compiler policy and catalog dependency bundle."""

    catalog: CompilerCatalog = field(default_factory=CompilerCatalog)
    max_cost_microusd: float | None = None
    max_latency_ms: float | None = None
    required_sla_fields: tuple[str, ...] = ("p95_ms",)

    def __post_init__(self) -> None:
        if not isinstance(self.catalog, CompilerCatalog):
            raise CompilerError("catalog_required")
        if self.max_cost_microusd is not None and self.max_cost_microusd < 0:
            raise CompilerError("max_cost_microusd_invalid")
        if self.max_latency_ms is not None and self.max_latency_ms < 0:
            raise CompilerError("max_latency_ms_invalid")
        fields = tuple(str(value).strip() for value in self.required_sla_fields)
        if not fields or any(not value for value in fields):
            raise CompilerError("required_sla_fields_invalid")
        object.__setattr__(self, "required_sla_fields", fields)


@dataclass(frozen=True, slots=True)
class CompilerCheckResult:
    """One named deterministic check result."""

    passed: bool
    detail: str
    check_name: str = ""


@dataclass(frozen=True, slots=True)
class CompilerReport(Mapping[str, CompilerCheckResult]):
    """Aggregate of all 12 checks, usable as a read-only mapping."""

    checks: Mapping[str, CompilerCheckResult]
    passed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.checks, Mapping):
            raise CompilerError("checks_must_be_mapping")
        object.__setattr__(self, "checks", MappingProxyType(dict(self.checks)))

    @property
    def results(self) -> Mapping[str, CompilerCheckResult]:
        return self.checks

    def __getitem__(self, key: str) -> CompilerCheckResult:
        return self.checks[key]

    def __iter__(self):
        return iter(self.checks)

    def __len__(self) -> int:
        return len(self.checks)

    def to_payload(self) -> dict[str, object]:
        """Return a stable JSON-compatible read-only-report projection.

        The mapping is rebuilt in insertion order and contains only primitive
        values. Callers may serialize it for the Web boundary without
        exposing dataclass internals or mutating the compiler result.
        """

        return {
            "passed": self.passed,
            "checks": {
                name: {
                    "check_name": result.check_name or name,
                    "passed": result.passed,
                    "detail": result.detail,
                }
                for name, result in self.checks.items()
            },
        }


CompilerResult = CompilerReport


def _value(product: Any, name: str, default: Any = None) -> Any:
    if isinstance(product, Mapping):
        return product.get(name, default)
    return getattr(product, name, default)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _refs(value: Any) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Iterable):
        return ()
    refs = tuple(_text(item) for item in value)
    if not refs or any(not item for item in refs) or len(set(refs)) != len(refs):
        return ()
    return refs


def _entry(source: Mapping[str, Any], *keys: Any) -> Any:
    for key in keys:
        if key in source:
            return source[key]
    return None


def _entry_field(entry: Any, name: str, default: Any = None) -> Any:
    if isinstance(entry, Mapping):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _ok(name: str, detail: str) -> CompilerCheckResult:
    return CompilerCheckResult(True, detail, name)


def _fail(name: str, detail: str) -> CompilerCheckResult:
    return CompilerCheckResult(False, detail, name)


class ProductCompiler:
    """Compile a ProductDefinition-shaped draft without side effects."""

    CHECKS = (
        "check_schema",
        "check_component",
        "check_compatibility",
        "check_workflow",
        "check_resource",
        "check_ai_use_case",
        "check_context_boundary",
        "check_safety",
        "check_human_gate",
        "check_cost",
        "check_evaluation",
        "check_sla",
    )

    def __init__(self, context: CompilerContext | CompilerCatalog | None = None):
        if context is None:
            context = CompilerContext()
        elif isinstance(context, CompilerCatalog):
            context = CompilerContext(catalog=context)
        if not isinstance(context, CompilerContext):
            raise CompilerError("compiler_context_required")
        self.context = context

    @property
    def catalog(self) -> CompilerCatalog:
        return self.context.catalog

    def check_schema(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_schema"
        if product is None:
            return _fail(name, "product_required")
        if _text(_value(product, "status")) != "DRAFT":
            return _fail(name, "product_must_be_draft")
        spec = _value(product, "education_spec")
        if spec is None:
            return _fail(name, "education_spec_required")
        required = (
            "product_kind",
            "zone",
            "primary_contradiction",
            "pause_policy",
            "human_gate_policy",
        )
        if any(not _text(_value(spec, field_name)) for field_name in required):
            return _fail(name, "education_spec_fields_required")
        duration = _value(spec, "duration_days")
        if not isinstance(duration, int) or duration <= 0:
            return _fail(name, "education_spec_duration_invalid")
        for field_name in (
            "component_ids",
            "skill_ids",
            "success_metric_ids",
            "guardrail_ids",
            "stop_conditions",
        ):
            if not _refs(_value(spec, field_name)):
                return _fail(name, f"education_spec_{field_name}_required")
        if not _text(_value(product, "demand_ref")) or not _refs(
            _value(product, "market_insight_refs")
        ):
            return _fail(name, "market_traceability_required")
        return _ok(name, "schema_valid")

    def check_component(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_component"
        refs = _refs(_value(_value(product, "education_spec"), "component_ids"))
        if not refs:
            return _fail(name, "component_refs_missing")
        missing = [ref for ref in refs if _entry(self.catalog.components, ref) is None]
        if missing:
            return _fail(name, "component_catalog_missing:" + ",".join(missing))
        return _ok(name, "components_resolved")

    def check_compatibility(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_compatibility"
        spec = _value(product, "education_spec")
        components = _refs(_value(spec, "component_ids"))
        skills = set(_refs(_value(spec, "skill_ids")))
        if not components or not skills:
            return _fail(name, "component_skill_refs_missing")
        for component_id in components:
            component = _entry(self.catalog.components, component_id)
            if component is None:
                return _fail(name, f"component_not_catalogued:{component_id}")
            required = _refs(_entry_field(component, "required_skill_ids"))
            if required and not set(required).issubset(skills):
                return _fail(name, f"component_skill_incompatible:{component_id}")
            declared = _entry(self.catalog.compatibility, component_id, f"{component_id}:skills")
            if declared is not None and not set(_refs(declared)).issubset(skills):
                return _fail(name, f"compatibility_catalog_mismatch:{component_id}")
        return _ok(name, "component_skill_compatibility_valid")

    def check_workflow(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_workflow"
        keys = (
            _value(product, "id"),
            _value(product, "concept_id"),
            _value(product, "product_kind"),
        )
        workflow = _entry(self.catalog.workflows, *[key for key in keys if key])
        if workflow is None:
            workflow = _value(product, "workflow")
        if workflow is None:
            return _fail(name, "workflow_catalog_missing")
        stages = _entry_field(
            workflow,
            "stages",
            workflow if isinstance(workflow, (list, tuple)) else None,
        )
        stages = (
            tuple(stages)
            if isinstance(stages, Iterable)
            and not isinstance(stages, (str, bytes, Mapping))
            else ()
        )
        if not stages or len(set(stages)) != len(stages):
            return _fail(name, "workflow_stages_invalid")
        if _entry_field(workflow, "reachable", True) is False or _entry_field(
            workflow, "has_cycle", False
        ):
            return _fail(name, "workflow_unreachable_or_cyclic")
        return _ok(name, "workflow_reachable")

    def check_resource(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_resource"
        spec = _value(product, "education_spec")
        refs = (*_refs(_value(spec, "component_ids")), *_refs(_value(spec, "skill_ids")))
        if not refs:
            return _fail(name, "resource_refs_missing")
        missing = [ref for ref in refs if _entry(self.catalog.resources, ref) is None]
        if missing:
            return _fail(name, "resource_unavailable:" + ",".join(missing))
        unavailable = [
            ref
            for ref in refs
            if _entry_field(_entry(self.catalog.resources, ref), "available", True) is False
            or (
                _entry_field(_entry(self.catalog.resources, ref), "capacity", 1) or 0
            )
            <= 0
        ]
        if unavailable:
            return _fail(name, "resource_capacity_exhausted:" + ",".join(unavailable))
        return _ok(name, "resources_available")

    def check_ai_use_case(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_ai_use_case"
        spec = _value(product, "education_spec")
        refs = _refs(_value(product, "ai_use_case_refs")) or _refs(
            _value(spec, "skill_ids")
        )
        if not refs:
            return _fail(name, "ai_use_case_refs_missing")
        missing = [ref for ref in refs if _entry(self.catalog.ai_use_cases, ref) is None]
        if missing:
            return _fail(name, "ai_use_case_unregistered:" + ",".join(missing))
        invalid = [
            ref
            for ref in refs
            if str(
                _entry_field(_entry(self.catalog.ai_use_cases, ref), "status", "ACTIVE")
            ).upper()
            not in {"ACTIVE", "REGISTERED", "VALID"}
        ]
        if invalid:
            return _fail(name, "ai_use_case_invalid:" + ",".join(invalid))
        return _ok(name, "ai_use_cases_registered")

    def check_context_boundary(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_context_boundary"
        keys = (
            _value(product, "id"),
            _value(product, "concept_id"),
            _value(product, "product_kind"),
        )
        boundary = _entry(self.catalog.context_boundaries, *[key for key in keys if key])
        if boundary is None:
            return _fail(name, "context_boundary_missing")
        if _entry_field(boundary, "cross_tenant", False) or _entry_field(
            boundary, "cross_family", False
        ):
            return _fail(name, "context_cross_scope_forbidden")
        scopes = _entry_field(boundary, "allowed_scopes", None)
        if scopes is None:
            scopes = (
                _entry_field(boundary, "tenant_scope", None),
                _entry_field(boundary, "family_scope", None),
            )
        if not any(
            _text(scope) and _text(scope) != "*" for scope in scopes if scope is not None
        ):
            return _fail(name, "context_scope_not_bounded")
        return _ok(name, "context_boundary_bounded")

    def check_safety(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_safety"
        keys = (
            _value(product, "id"),
            _value(product, "concept_id"),
            _value(product, "product_kind"),
        )
        policy = _entry(self.catalog.safety_policies, *[key for key in keys if key])
        if policy is None:
            return _fail(name, "safety_policy_missing")
        if any(
            _entry_field(policy, field_name, False)
            for field_name in ("cross_family", "cross_tenant", "unbounded_child_data", "unsafe")
        ):
            return _fail(name, "safety_policy_forbidden")
        if isinstance(policy, Mapping) and not any(
            _text(policy.get(field_name))
            for field_name in ("policy_ref", "guardrail_ref", "data_class", "consent")
        ):
            return _fail(name, "safety_policy_evidence_missing")
        return _ok(name, "safety_policy_valid")

    def check_human_gate(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_human_gate"
        spec = _value(product, "education_spec")
        if not _text(_value(spec, "human_gate_policy")):
            return _fail(name, "human_gate_policy_missing")
        keys = (
            _value(product, "id"),
            _value(product, "concept_id"),
            _value(product, "product_kind"),
        )
        gate = _entry(self.catalog.human_gates, *[key for key in keys if key])
        if gate is None:
            return _fail(name, "human_gate_trigger_missing")
        actor_type = str(_entry_field(gate, "actor_type", "HUMAN")).upper()
        if _entry_field(gate, "required", True) is False or actor_type in {"AI", "SYSTEM"}:
            return _fail(name, "human_gate_human_required")
        return _ok(name, "human_gate_configured")

    def check_cost(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_cost"
        keys = (
            _value(product, "id"),
            _value(product, "concept_id"),
            _value(product, "product_kind"),
        )
        cost = _entry(self.catalog.costs, *[key for key in keys if key])
        if cost is None:
            return _fail(name, "cost_estimate_missing")
        estimated = _entry_field(
            cost,
            "estimated_microusd",
            _entry_field(
                cost,
                "estimate_microusd",
                cost if isinstance(cost, (int, float)) else None,
            ),
        )
        limit = _entry_field(cost, "max_microusd", self.context.max_cost_microusd)
        if not isinstance(estimated, (int, float)) or estimated < 0:
            return _fail(name, "cost_estimate_invalid")
        if not isinstance(limit, (int, float)) or estimated > limit:
            return _fail(name, "cost_limit_exceeded_or_missing")
        return _ok(name, "cost_within_limit")

    def check_evaluation(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_evaluation"
        keys = (
            _value(product, "id"),
            _value(product, "concept_id"),
            _value(product, "product_kind"),
        )
        suite = _entry(self.catalog.evaluations, *[key for key in keys if key])
        if suite is None:
            return _fail(name, "evaluation_suite_missing")
        refs = _refs(
            _entry_field(suite, "refs", suite if isinstance(suite, (list, tuple)) else ())
        )
        if not refs:
            return _fail(name, "evaluation_refs_missing")
        if str(_entry_field(suite, "status", "ACTIVE")).upper() not in {"ACTIVE", "VALID"}:
            return _fail(name, "evaluation_suite_invalid")
        return _ok(name, "evaluation_suite_configured")

    def check_sla(self, product: ProductDefinition) -> CompilerCheckResult:
        name = "check_sla"
        keys = (
            _value(product, "id"),
            _value(product, "concept_id"),
            _value(product, "product_kind"),
        )
        sla = _entry(self.catalog.slas, *[key for key in keys if key])
        if sla is None:
            return _fail(name, "sla_missing")
        for field_name in self.context.required_sla_fields:
            value = _entry_field(sla, field_name, None)
            if not isinstance(value, (int, float)) or value <= 0:
                return _fail(name, f"sla_{field_name}_invalid")
            if (
                field_name == "p95_ms"
                and self.context.max_latency_ms is not None
                and value > self.context.max_latency_ms
            ):
                return _fail(name, "sla_latency_limit_exceeded")
        return _ok(name, "sla_executable")

    def compile(self, product: ProductDefinition) -> CompilerReport:
        """Run and aggregate all checks in a stable order."""

        checks: dict[str, CompilerCheckResult] = {}
        for check_name in self.CHECKS:
            check = getattr(self, check_name)
            try:
                result = check(product)
            except Exception as exc:  # fail closed for malformed injected data
                result = _fail(check_name, f"check_error:{type(exc).__name__}")
            if not isinstance(result, CompilerCheckResult):
                result = _fail(check_name, "check_result_invalid")
            checks[check_name] = result
        return CompilerReport(checks=checks, passed=all(item.passed for item in checks.values()))


__all__ = [
    "CompilerCatalog",
    "CompilerCheckResult",
    "CompilerContext",
    "CompilerError",
    "CompilerReport",
    "CompilerResult",
    "ProductCompiler",
]
