"""Fail-closed loader/validator for `governance/WORLD_MODEL_PREDICATE_REGISTRY.yaml`.

Validation happens at the persistence boundary (see
`postgres_world_state_repository.py`), not inside `WorldStateAtom.__post_init__`
— the kernel dataclass stays I/O-free and unit-testable without a filesystem
dependency, while every atom that actually reaches durable storage is checked
against the governed vocabulary first.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "governance" / "WORLD_MODEL_PREDICATE_REGISTRY.yaml"
)


class PredicateRegistryError(ValueError):
    """Raised when the predicate registry is missing, malformed, or violated."""


class PredicateRegistry:
    """Immutable-by-convention set of governed World Model predicates."""

    def __init__(self, predicates: Mapping[str, str]) -> None:
        """`predicates` maps a fully-qualified predicate string to its owner."""

        if not predicates:
            raise PredicateRegistryError("PREDICATE_REGISTRY_EMPTY")
        self._owners: dict[str, str] = dict(predicates)

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> PredicateRegistry:
        registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
        try:
            raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise PredicateRegistryError("PREDICATE_REGISTRY_LOAD_FAILED") from exc
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: Any) -> PredicateRegistry:
        if not isinstance(raw, Mapping):
            raise PredicateRegistryError("PREDICATE_REGISTRY_MALFORMED")
        predicates: dict[str, str] = {}
        core = raw.get("core")
        if not isinstance(core, Mapping):
            raise PredicateRegistryError("PREDICATE_REGISTRY_MISSING_CORE")
        for predicate, entry in core.items():
            owner = _require_owner(entry)
            predicates[predicate] = owner
        verticals = raw.get("verticals") or {}
        if not isinstance(verticals, Mapping):
            raise PredicateRegistryError("PREDICATE_REGISTRY_MALFORMED_VERTICALS")
        for _pack_name, pack in verticals.items():
            if not isinstance(pack, Mapping):
                raise PredicateRegistryError("PREDICATE_REGISTRY_MALFORMED_VERTICAL_PACK")
            pack_owner = pack.get("owner")
            entries = pack.get("predicates") or {}
            if not isinstance(entries, Mapping):
                raise PredicateRegistryError("PREDICATE_REGISTRY_MALFORMED_VERTICAL_PACK")
            for predicate, entry in entries.items():
                owner = _require_owner(entry, default_owner=pack_owner)
                if predicate in predicates:
                    raise PredicateRegistryError(f"PREDICATE_REGISTRY_DUPLICATE:{predicate}")
                predicates[predicate] = owner
        return cls(predicates)

    def validate(self, predicate: str) -> None:
        """Raise if `predicate` is not a registered World Model predicate."""

        if predicate not in self._owners:
            raise PredicateRegistryError(f"PREDICATE_NOT_REGISTERED:{predicate}")

    def owner_of(self, predicate: str) -> str:
        self.validate(predicate)
        return self._owners[predicate]

    def __contains__(self, predicate: str) -> bool:
        return predicate in self._owners

    def __len__(self) -> int:
        return len(self._owners)


def _require_owner(entry: Any, *, default_owner: Any = None) -> str:
    if not isinstance(entry, Mapping):
        raise PredicateRegistryError("PREDICATE_REGISTRY_MALFORMED_ENTRY")
    owner = entry.get("owner", default_owner)
    if not isinstance(owner, str) or not owner.strip():
        raise PredicateRegistryError("PREDICATE_REGISTRY_MISSING_OWNER")
    return owner


__all__ = [
    "DEFAULT_REGISTRY_PATH",
    "PredicateRegistry",
    "PredicateRegistryError",
]
