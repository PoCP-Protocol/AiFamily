"""Immutable output-schema contracts and boundary metadata."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal

SchemaStatus = Literal["DRAFT", "REVIEW", "PUBLISHED", "RETIRED"]
HumanGateRule = Literal["NOT_REQUIRED", "REVIEW_REQUIRED", "EXPLICIT_CONFIRMATION"]


@dataclass(frozen=True, slots=True)
class SchemaDefinition:
    """A versioned, use-case/agent-bound JSON output contract.

    ``required_fields`` and ``forbidden_fields`` are first-class policy rather
    than comments in a JSON document.  This allows the runtime to enforce R9
    even when a model returns a syntactically valid object with a dangerous
    field.  ``json_schema`` is an intentionally small JSON-Schema subset used
    for type/enum checks; a future adapter may delegate to a standards-compliant
    validator without changing this boundary.
    """

    schema_ref: str
    version: str
    use_case: str
    agent_id: str
    object_type: str
    required_fields: tuple[str, ...] = ()
    evidence_refs_non_empty: bool = False
    forbidden_fields: frozenset[str] = frozenset()
    allowed_fields: frozenset[str] = frozenset()
    enum_constraints: Mapping[str, tuple[str, ...]] = MappingProxyType({})
    boundary_labels: tuple[str, ...] = ()
    human_gate_rule: HumanGateRule = "REVIEW_REQUIRED"
    json_schema: Mapping[str, Any] = MappingProxyType({})
    status: SchemaStatus = "DRAFT"
    effective_at: datetime | None = None
    retired_at: datetime | None = None
    author: str = ""
    reviewer: str | None = None
    change_reason: str = ""
    evidence_refs_field: str = "evidence_refs"
    visibility: str = "FAMILY_PRIVATE"
    write_back_target: str = "DERIVED_ARTIFACT"
    validator_ref: str = "schema_registry.default"
    text_equivalent_required: bool = True

    def __post_init__(self) -> None:
        if not all((self.schema_ref, self.version, self.use_case, self.agent_id, self.object_type)):
            raise ValueError("SchemaDefinition identity and object_type are required")
        if self.status not in {"DRAFT", "REVIEW", "PUBLISHED", "RETIRED"}:
            raise ValueError(f"unknown schema status: {self.status}")
        if self.human_gate_rule not in {
            "NOT_REQUIRED",
            "REVIEW_REQUIRED",
            "EXPLICIT_CONFIRMATION",
        }:
            raise ValueError(f"unknown human_gate_rule: {self.human_gate_rule}")
        required = tuple(self.required_fields)
        if len(set(required)) != len(required) or any(not name for name in required):
            raise ValueError("required_fields must contain unique non-empty names")
        forbidden = frozenset(self.forbidden_fields)
        if any(not name for name in forbidden):
            raise ValueError("forbidden_fields cannot contain blank names")
        allowed = frozenset(self.allowed_fields)
        if any(not name for name in allowed):
            raise ValueError("allowed_fields cannot contain blank names")
        if allowed and forbidden & allowed:
            raise ValueError("a field cannot be both allowed and forbidden")
        if set(required) & forbidden:
            raise ValueError("a field cannot be both required and forbidden")
        enum_constraints = {
            str(name): tuple(values) for name, values in dict(self.enum_constraints).items()
        }
        if any(not name or not values for name, values in enum_constraints.items()):
            raise ValueError("enum_constraints require a field and at least one allowed value")
        if any(not label for label in self.boundary_labels):
            raise ValueError("boundary_labels cannot contain blank values")
        if not self.evidence_refs_field:
            raise ValueError("evidence_refs_field is required")
        if (
            self.retired_at is not None
            and self.effective_at is not None
            and self.retired_at <= self.effective_at
        ):
            raise ValueError("retired_at must be after effective_at")
        if self.status == "PUBLISHED":
            if self.effective_at is None:
                raise ValueError("a published schema requires effective_at")
            if not self.reviewer:
                raise ValueError("a published schema requires reviewer")
        if self.status in {"REVIEW", "RETIRED"} and not self.change_reason:
            raise ValueError(f"{self.status.lower()} schema requires change_reason")
        object.__setattr__(self, "required_fields", required)
        object.__setattr__(self, "forbidden_fields", forbidden)
        object.__setattr__(self, "allowed_fields", allowed)
        object.__setattr__(self, "boundary_labels", tuple(self.boundary_labels))
        object.__setattr__(self, "enum_constraints", MappingProxyType(enum_constraints))
        object.__setattr__(self, "json_schema", _freeze_json(self.json_schema))

    @property
    def requires_human_gate(self) -> bool:
        return self.human_gate_rule != "NOT_REQUIRED"

    def effective_at_time(self, at: datetime) -> bool:
        if at.tzinfo is None or self.effective_at is None or self.effective_at.tzinfo is None:
            return False
        if self.status != "PUBLISHED" or at < self.effective_at:
            return False
        return self.retired_at is None or at < self.retired_at


def _freeze_json(value: Any) -> Any:
    """Recursively freeze schema metadata so callers cannot mutate a version."""

    if isinstance(value, dict):
        return MappingProxyType({str(k): _freeze_json(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_json(item) for item in value)
    return value


# ``SchemaVersion`` is the vocabulary used by the data architecture catalog;
# it intentionally aliases the immutable runtime definition.
SchemaVersion = SchemaDefinition
