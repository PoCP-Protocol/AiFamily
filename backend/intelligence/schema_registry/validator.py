"""Fail-closed validation for registered AI output schemas."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import SchemaDefinition


class SchemaValidationError(ValueError):
    """Raised when output violates a schema or its AI safety boundary."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}{':' + detail if detail else ''}")


class SchemaValidator:
    """Validate structural and policy constraints without provider coupling."""

    def validate(self, definition: SchemaDefinition, output: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(output, Mapping):
            raise SchemaValidationError("OUTPUT_OBJECT_REQUIRED")
        result = dict(output)
        for field in definition.forbidden_fields:
            if _contains_field(result, field):
                raise SchemaValidationError("FORBIDDEN_FIELD", field)
        missing = [field for field in definition.required_fields if field not in result]
        if missing:
            raise SchemaValidationError("REQUIRED_FIELD_MISSING", ",".join(missing))
        if definition.allowed_fields:
            extras = set(result) - definition.allowed_fields
            if extras:
                raise SchemaValidationError("UNDECLARED_FIELD", sorted(extras)[0])
        if definition.evidence_refs_non_empty:
            refs = result.get(definition.evidence_refs_field)
            if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)) or not refs:
                raise SchemaValidationError(
                    "EVIDENCE_REFS_REQUIRED", definition.evidence_refs_field
                )
            if any(not isinstance(ref, str) or not ref.strip() for ref in refs):
                raise SchemaValidationError("EVIDENCE_REF_INVALID", definition.evidence_refs_field)
        for field, allowed in definition.enum_constraints.items():
            if field in result and result[field] not in allowed:
                raise SchemaValidationError("ENUM_VALUE_INVALID", field)
        if definition.json_schema:
            self._validate_json_schema(result, definition.json_schema)
        return result

    def _validate_json_schema(
        self, value: Any, schema: Mapping[str, Any], path: str = "$"
    ) -> None:
        # Keep this subset deliberately strict and deterministic.  Unknown
        # schema keywords are ignored, while unknown output fields are rejected
        # only when ``additionalProperties: false`` is explicitly declared.
        expected = schema.get("type")
        if expected is not None and not _matches_type(value, expected):
            raise SchemaValidationError("JSON_TYPE_INVALID", path.strip())
        if "enum" in schema and value not in schema["enum"]:
            raise SchemaValidationError("JSON_ENUM_INVALID", path.strip())
        if isinstance(value, Mapping):
            required = schema.get("required", ())
            missing = [name for name in required if name not in value]
            if missing:
                raise SchemaValidationError("JSON_REQUIRED_MISSING", f"{path}.{missing[0]}")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                extras = set(value) - set(properties)
                if extras:
                    raise SchemaValidationError(
                        "JSON_ADDITIONAL_PROPERTY", f"{path}.{sorted(extras)[0]}"
                    )
            for name, child_schema in properties.items():
                if name in value:
                    self._validate_json_schema(value[name], child_schema, f"{path}.{name}")
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            if "minItems" in schema and len(value) < schema["minItems"]:
                raise SchemaValidationError("JSON_MIN_ITEMS", path.strip())
            item_schema = schema.get("items")
            if isinstance(item_schema, Mapping):
                for index, item in enumerate(value):
                    self._validate_json_schema(item, item_schema, f"{path}[{index}]")


def _matches_type(value: Any, expected: str | Sequence[str]) -> bool:
    expected_types = (expected,) if isinstance(expected, str) else tuple(expected)
    checks = {
        "object": lambda item: isinstance(item, Mapping),
        "array": lambda item: isinstance(item, Sequence) and not isinstance(item, (str, bytes)),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    return any(type_name in checks and checks[type_name](value) for type_name in expected_types)


def _contains_field(value: Any, field: str) -> bool:
    """Find a forbidden key at any object depth, including dotted paths."""

    if "." in field:
        parts = tuple(part for part in field.split(".") if part)
        return _contains_path(value, parts)
    if isinstance(value, Mapping):
        if field in value:
            return True
        return any(_contains_field(child, field) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_field(child, field) for child in value)
    return False


def _contains_path(value: Any, path: tuple[str, ...]) -> bool:
    if not path:
        return True
    if isinstance(value, Mapping):
        if path[0] not in value:
            return False
        return _contains_path(value[path[0]], path[1:])
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_path(child, path) for child in value)
    return False
