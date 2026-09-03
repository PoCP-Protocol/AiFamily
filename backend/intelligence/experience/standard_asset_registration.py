"""Explicit registration seam for standard family-experience assets.

The registries own persistence and transaction boundaries.  This module only
coordinates the two immutable records, preflights duplicate identities, and
requires a published pair for runtime installation.  SQL callers must invoke
it inside their startup transaction; no implicit commit or provider call is
performed here.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from .standard_assets import FamilyExperienceAssetBundle


class FamilyExperienceAssetRegistrationError(ValueError):
    """Raised when a standard asset pair cannot be installed safely."""


@dataclass(frozen=True, slots=True)
class RegisteredFamilyExperienceAssets:
    """Stable identity returned after both records are accepted by a Registry."""

    prompt_ref: str
    prompt_version: str
    schema_ref: str
    schema_version: str
    system_policy_ref: str
    knowledge_refs: tuple[str, ...]


async def register_family_experience_assets(
    *,
    assets: FamilyExperienceAssetBundle,
    prompt_registry: object,
    schema_registry: object,
    material_registry: object,
    require_published: bool = True,
) -> RegisteredFamilyExperienceAssets:
    """Register a pair into sync or async registries without committing them.

    ``get`` is required in addition to ``register`` so duplicate identities
    are rejected before either side is mutated.  A SQL caller still owns the
    surrounding transaction and can roll back if a concurrent write races the
    preflight check.
    """

    if not isinstance(assets, FamilyExperienceAssetBundle):
        raise FamilyExperienceAssetRegistrationError("family experience assets are required")
    if require_published and assets.status != "PUBLISHED":
        raise FamilyExperienceAssetRegistrationError(
            "published family experience assets are required"
        )
    for registry, label in (
        (prompt_registry, "prompt"),
        (schema_registry, "schema"),
    ):
        if not callable(getattr(registry, "get", None)):
            raise FamilyExperienceAssetRegistrationError(f"{label} registry get is required")
        if not callable(getattr(registry, "register", None)):
            raise FamilyExperienceAssetRegistrationError(
                f"{label} registry register is required"
            )
    for method_name in (
        "get_policy",
        "get_knowledge",
        "register_policy",
        "register_knowledge",
    ):
        if not callable(getattr(material_registry, method_name, None)):
            raise FamilyExperienceAssetRegistrationError(
                f"material registry {method_name} is required"
            )

    existing_prompt = await _call(
        prompt_registry,
        "get",
        assets.prompt.prompt_ref,
        assets.prompt.version,
    )
    existing_schema = await _call(
        schema_registry,
        "get",
        assets.schema.schema_ref,
        assets.schema.version,
    )
    existing_policy = await _call(
        material_registry,
        "get_policy",
        assets.system_policy.policy_ref,
    )
    existing_knowledge = []
    for item in assets.knowledge:
        existing_knowledge.append(
            await _call(material_registry, "get_knowledge", item.knowledge_ref)
        )
    if (
        existing_prompt is not None
        or existing_schema is not None
        or existing_policy is not None
        or any(item is not None for item in existing_knowledge)
    ):
        raise FamilyExperienceAssetRegistrationError(
            "family experience asset identity is already registered"
        )

    await _call(prompt_registry, "register", assets.prompt)
    await _call(schema_registry, "register", assets.schema)
    await _call(material_registry, "register_policy", assets.system_policy)
    for material in assets.knowledge:
        await _call(material_registry, "register_knowledge", material)
    return RegisteredFamilyExperienceAssets(
        prompt_ref=assets.prompt.prompt_ref,
        prompt_version=assets.prompt.version,
        schema_ref=assets.schema.schema_ref,
        schema_version=assets.schema.version,
        system_policy_ref=assets.system_policy.policy_ref,
        knowledge_refs=tuple(item.knowledge_ref for item in assets.knowledge),
    )


async def _call(registry: object, method_name: str, *args: Any) -> Any:
    result = getattr(registry, method_name)(*args)
    return await result if inspect.isawaitable(result) else result


__all__ = [
    "FamilyExperienceAssetRegistrationError",
    "RegisteredFamilyExperienceAssets",
    "register_family_experience_assets",
]
