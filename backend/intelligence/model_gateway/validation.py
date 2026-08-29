"""Minimal structural validation of model output.

Scope is deliberately narrow: `type`, `required`, `properties` (recursively),
`items`, and `enum`. That covers what output schemas in this platform actually
need — "the required fields are present and are the right shape" — and it adds no
dependency.

Why not a full JSON Schema library: adding one is an R11 dependency decision that
belongs in an ADR, not smuggled in with an infrastructure task. The extension
point is `SchemaValidator`, so swapping in `jsonschema` later is a one-class
change; until then the honest statement is that this validator implements a
*subset*, recorded here rather than implied by the name.

What matters more than coverage is the failure mode. Any validation failure raises
`SCHEMA_INVALID` and the raw model text is discarded — never returned, never
logged, never partially salvaged. A validator that "fixed up" a near-miss response
would be manufacturing content and attributing it to the model.
"""

from __future__ import annotations

from typing import Any

from backend.intelligence.model_gateway.errors import ModelGatewayError

_JSON_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
}


class SchemaValidator:
    """Validates a decoded model response against a schema subset."""

    def validate(
        self,
        value: Any,
        schema: dict[str, Any],
        *,
        provider_id: str,
    ) -> dict[str, Any]:
        problems: list[str] = []
        self._check(value, schema, path="$", problems=problems)
        if problems:
            raise ModelGatewayError(
                "SCHEMA_INVALID",
                "model output failed schema validation: " + "; ".join(problems[:10]),
                provider_id=provider_id,
            )
        if not isinstance(value, dict):
            # The gateway's contract is a `dict` output. A schema permitting a
            # bare array or scalar at the top level is a caller error, and
            # returning it anyway would break `ModelDraft.output`'s type.
            raise ModelGatewayError(
                "SCHEMA_INVALID",
                f"model output must be a JSON object at the top level, got {type(value).__name__}",
                provider_id=provider_id,
            )
        return value

    def _check(
        self,
        value: Any,
        schema: dict[str, Any],
        *,
        path: str,
        problems: list[str],
    ) -> None:
        expected = schema.get("type")
        if isinstance(expected, str):
            allowed = _JSON_TYPE_MAP.get(expected)
            if allowed is not None:
                # bool is a subclass of int in Python; a schema asking for a
                # number must not accept True.
                is_bool_mismatch = expected in {"number", "integer"} and isinstance(value, bool)
                if is_bool_mismatch or not isinstance(value, allowed):
                    problems.append(f"{path}: expected {expected}, got {type(value).__name__}")
                    return

        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            problems.append(f"{path}: {value!r} is not one of {enum}")

        if isinstance(value, dict):
            for name in schema.get("required") or []:
                if name not in value:
                    problems.append(f"{path}: missing required property {name!r}")
            properties = schema.get("properties")
            if isinstance(properties, dict):
                for name, sub_schema in properties.items():
                    if name in value and isinstance(sub_schema, dict):
                        self._check(
                            value[name], sub_schema, path=f"{path}.{name}", problems=problems
                        )

        if isinstance(value, list):
            items = schema.get("items")
            if isinstance(items, dict):
                for index, element in enumerate(value):
                    self._check(element, items, path=f"{path}[{index}]", problems=problems)
