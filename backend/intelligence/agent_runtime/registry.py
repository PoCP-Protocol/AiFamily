"""Fail-closed loader for the governed Agent Definition registry.

The canonical registry lives in ``governance/AI_USE_CASE_REGISTRY.yaml``.
This adapter turns only the static Agent declarations into
``AgentDefinition`` values; dynamic family authorization remains a separate
lease and is still required by ``AgentRuntime`` before execution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from .contracts import AgentDefinition


class AgentRegistryError(ValueError):
    """Raised when the canonical Agent registry is missing or malformed."""


class AgentDefinitionRegistry:
    """Immutable-by-convention collection of reviewed Agent definitions."""

    def __init__(self, definitions: Sequence[AgentDefinition] = ()) -> None:
        self._definitions: dict[str, AgentDefinition] = {}
        for definition in definitions:
            if not isinstance(definition, AgentDefinition):
                raise AgentRegistryError("AGENT_DEFINITION_REQUIRED")
            if definition.agent_id in self._definitions:
                raise AgentRegistryError("AGENT_DEFINITION_DUPLICATE")
            self._definitions[definition.agent_id] = definition

    @classmethod
    def from_yaml(
        cls,
        path: str | Path,
        *,
        runnable_only: bool = False,
    ) -> AgentDefinitionRegistry:
        """Load Agent declarations from an explicit governance file path."""

        registry_path = Path(path)
        try:
            raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise AgentRegistryError("AGENT_REGISTRY_LOAD_FAILED") from exc
        return cls.from_mapping(raw, runnable_only=runnable_only)

    @classmethod
    def from_mapping(
        cls,
        raw: object,
        *,
        runnable_only: bool = False,
    ) -> AgentDefinitionRegistry:
        if not isinstance(raw, Mapping):
            raise AgentRegistryError("AGENT_REGISTRY_ROOT_INVALID")
        entries = raw.get("agents")
        if not isinstance(entries, list) or not entries:
            raise AgentRegistryError("AGENT_REGISTRY_AGENTS_REQUIRED")
        runnable_use_cases = _runnable_ids(raw.get("use_cases"), "USE_CASE")
        runnable_tools = _runnable_ids(raw.get("tools"), "TOOL")
        definitions: list[AgentDefinition] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                raise AgentRegistryError(f"AGENT_REGISTRY_ENTRY_INVALID:{index}")
            if runnable_only and not _is_runnable(entry, "AGENT", index):
                continue
            definition = _definition(
                entry,
                index=index,
                runnable_use_cases=runnable_use_cases if runnable_only else None,
                runnable_tools=runnable_tools if runnable_only else None,
            )
            if runnable_only and not definition.allowed_use_cases:
                continue
            definitions.append(definition)
        return cls(definitions)

    def get(self, agent_id: str) -> AgentDefinition | None:
        return self._definitions.get(agent_id)

    def require(self, agent_id: str) -> AgentDefinition:
        definition = self.get(agent_id)
        if definition is None:
            raise AgentRegistryError("AGENT_DEFINITION_NOT_FOUND")
        return definition

    def all(self) -> tuple[AgentDefinition, ...]:
        return tuple(self._definitions.values())


def _definition(
    entry: Mapping[str, Any],
    *,
    index: int,
    runnable_use_cases: frozenset[str] | None = None,
    runnable_tools: frozenset[str] | None = None,
) -> AgentDefinition:
    required_text = (
        "id",
        "name",
        "context_policy",
        "safety_policy",
        "human_handoff_policy",
    )
    if any(not isinstance(entry.get(key), str) or not entry[key].strip() for key in required_text):
        raise AgentRegistryError(f"AGENT_REGISTRY_ENTRY_REQUIRED:{index}")

    allowed_use_cases = _text_set(entry.get("allowed_use_cases"), "allowed_use_cases", index)
    allowed_tools = _text_set(entry.get("allowed_tools"), "allowed_tools", index)
    if runnable_use_cases is not None:
        allowed_use_cases &= runnable_use_cases
    if runnable_tools is not None:
        allowed_tools &= runnable_tools
    allowed_skills = _text_set(entry.get("allowed_skills", ()), "allowed_skills", index)
    if entry.get("may_mutate_business_state") is not False:
        raise AgentRegistryError(f"AGENT_REGISTRY_MUTATION_FORBIDDEN:{index}")
    return AgentDefinition(
        agent_id=entry["id"].strip(),
        name=entry["name"].strip(),
        allowed_skills=allowed_skills,
        allowed_tools=allowed_tools,
        allowed_use_cases=allowed_use_cases,
        context_policy=entry["context_policy"].strip(),
        safety_policy=entry["safety_policy"].strip(),
        human_handoff_policy=entry["human_handoff_policy"].strip(),
        budget_policy=str(entry.get("budget_policy") or "registry_default"),
    )


def _text_set(value: object, field_name: str, index: int) -> frozenset[str]:
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise AgentRegistryError(f"AGENT_REGISTRY_{field_name.upper()}_INVALID:{index}")
    return frozenset(item.strip() for item in value)


_RUNNABLE_STATUSES = frozenset({"EXPERIMENT", "PILOT", "PRODUCTION"})


def _is_runnable(entry: Mapping[str, Any], kind: str, index: int) -> bool:
    status = entry.get("status")
    if not isinstance(status, str) or not status.strip():
        raise AgentRegistryError(f"{kind}_REGISTRY_STATUS_REQUIRED:{index}")
    return status.strip().upper() in _RUNNABLE_STATUSES


def _runnable_ids(value: object, kind: str) -> frozenset[str]:
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        raise AgentRegistryError(f"{kind}_REGISTRY_ENTRIES_INVALID")
    identifiers: set[str] = set()
    for index, entry in enumerate(value):
        if not isinstance(entry, Mapping):
            raise AgentRegistryError(f"{kind}_REGISTRY_ENTRY_INVALID:{index}")
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise AgentRegistryError(f"{kind}_REGISTRY_ID_REQUIRED:{index}")
        if _is_runnable(entry, kind, index):
            identifiers.add(identifier.strip())
    return frozenset(identifiers)


__all__ = ["AgentDefinitionRegistry", "AgentRegistryError"]
