"""Canonical content digest shared by release and runtime contract binding."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def family_experience_contract_asset_digest(
    *,
    prompt: Any,
    schema: Any,
    system_policy: Any | None = None,
    knowledge: tuple[Any, ...] = (),
) -> str:
    value = {
        "prompt_ref": prompt.prompt_ref,
        "prompt_version": prompt.version,
        "prompt_template": prompt.template,
        "system_policy_ref": prompt.system_policy_ref,
        "safety_policy_version": prompt.safety_policy_version,
        "knowledge_refs": list(prompt.knowledge_refs),
        "schema_ref": schema.schema_ref,
        "schema_version": schema.version,
        "json_schema": _jsonable(schema.json_schema),
        "forbidden_fields": sorted(schema.forbidden_fields),
        "human_gate_rule": schema.human_gate_rule,
        "system_policy_digest": (
            system_policy.content_digest if system_policy is not None else None
        ),
        "knowledge_material_digests": [item.content_digest for item in knowledge],
    }
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


__all__ = ["family_experience_contract_asset_digest"]
