"""Versioned Prompt/Schema binding for multimodal experience generation.

The HTTP body carries version selectors, never executable prompt policy.  This
adapter resolves those selectors against the reviewed Prompt and Schema
registries before a request can reach Model Gateway.  It accepts synchronous
and asynchronous registry implementations so dev/test and production SQL
composition share one contract.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backend.intelligence.model_gateway.contracts import (
    KnowledgeExecutionPayload,
    PromptExecutionPlan,
)
from backend.intelligence.prompt_registry.registry import PromptRegistryError
from backend.intelligence.schema_registry.registry import SchemaRegistryError

from .asset_digest import family_experience_contract_asset_digest
from .execution_materials import ExecutionMaterialError


class MultimodalContractBindingError(ValueError):
    """Raised when a prompt/schema pair is missing, stale, or mismatched."""


@dataclass(frozen=True, slots=True)
class ResolvedMultimodalContracts:
    """Immutable registry result used to build one generation command."""

    prompt_ref: str
    prompt_version: str
    schema_ref: str
    schema_version: str
    agent_id: str
    output_schema: dict[str, Any]
    safety_policy_version: str
    knowledge_refs: tuple[str, ...]
    asset_digest: str
    prompt_execution_plan: PromptExecutionPlan


@dataclass(frozen=True, slots=True)
class ReleaseContractExpectation:
    agent_id: str
    prompt_ref: str
    prompt_version: str
    schema_ref: str
    schema_version: str
    safety_policy_version: str
    knowledge_refs: tuple[str, ...]
    asset_digest: str


@dataclass(frozen=True, slots=True)
class MultimodalContractRegistryBinding:
    """Resolve one use-case's reviewed prompt and output schema together."""

    prompt_registry: object
    schema_registry: object
    agent_id: str
    prompt_ref: str
    schema_ref: str
    release_expectation: ReleaseContractExpectation | None = None
    material_resolver: object | None = None

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.agent_id,
                self.prompt_ref,
                self.schema_ref,
            )
        ):
            raise MultimodalContractBindingError("contract binding identity is required")
        if not callable(getattr(self.prompt_registry, "resolve", None)):
            raise MultimodalContractBindingError("prompt registry resolve is required")
        if not callable(getattr(self.schema_registry, "resolve", None)):
            raise MultimodalContractBindingError("schema registry resolve is required")
        if self.material_resolver is not None and not callable(
            getattr(self.material_resolver, "resolve", None)
        ):
            raise MultimodalContractBindingError("execution material resolver is invalid")
        if self.release_expectation is not None and self.material_resolver is None:
            raise MultimodalContractBindingError(
                "active release requires an execution material resolver"
            )

    async def resolve(
        self,
        *,
        use_case: str,
        prompt_version: str,
        schema_version: str,
        output_schema: Mapping[str, Any],
    ) -> ResolvedMultimodalContracts:
        if not use_case or not prompt_version or not schema_version:
            raise MultimodalContractBindingError("use_case and contract versions are required")
        try:
            prompt = await _resolve(
                self.prompt_registry,
                use_case=use_case,
                agent_id=self.agent_id,
                prompt_ref=self.prompt_ref,
                version=prompt_version,
            )
            schema = await _resolve(
                self.schema_registry,
                use_case=use_case,
                agent_id=self.agent_id,
                schema_ref=self.schema_ref,
                version=schema_version,
            )
        except (PromptRegistryError, SchemaRegistryError) as error:
            raise MultimodalContractBindingError("PROMPT_OR_SCHEMA_NOT_FOUND") from error
        if prompt is None or schema is None:
            raise MultimodalContractBindingError("PROMPT_OR_SCHEMA_NOT_FOUND")
        if (
            getattr(prompt, "prompt_ref", None) != self.prompt_ref
            or getattr(prompt, "version", None) != prompt_version
            or getattr(prompt, "use_case", None) != use_case
            or getattr(prompt, "agent_id", None) != self.agent_id
            or getattr(prompt, "output_schema_ref", None) != self.schema_ref
        ):
            raise MultimodalContractBindingError("PROMPT_BINDING_MISMATCH")
        if (
            getattr(schema, "schema_ref", None) != self.schema_ref
            or getattr(schema, "version", None) != schema_version
            or getattr(schema, "use_case", None) != use_case
            or getattr(schema, "agent_id", None) != self.agent_id
        ):
            raise MultimodalContractBindingError("SCHEMA_BINDING_MISMATCH")
        registry_schema = getattr(schema, "json_schema", None)
        if not isinstance(registry_schema, Mapping) or not registry_schema:
            raise MultimodalContractBindingError("SCHEMA_JSON_CONTRACT_MISSING")
        if _canonical(output_schema) != _canonical(registry_schema):
            raise MultimodalContractBindingError("CLIENT_SCHEMA_DOES_NOT_MATCH_REGISTRY")
        safety_policy_version = getattr(prompt, "safety_policy_version", None)
        knowledge_refs = getattr(prompt, "knowledge_refs", None)
        if not isinstance(safety_policy_version, str) or not isinstance(
            knowledge_refs, tuple
        ):
            raise MultimodalContractBindingError("PROMPT_POLICY_METADATA_MISSING")
        materials = None
        if self.material_resolver is not None:
            try:
                materials = await _resolve(
                    self.material_resolver,
                    system_policy_ref=prompt.system_policy_ref,
                    knowledge_refs=knowledge_refs,
                    use_case=use_case,
                    agent_id=self.agent_id,
                )
            except ExecutionMaterialError as error:
                raise MultimodalContractBindingError(
                    "EXECUTION_MATERIAL_NOT_ELIGIBLE"
                ) from error
        asset_digest = family_experience_contract_asset_digest(
            prompt=prompt,
            schema=schema,
            system_policy=(materials.system_policy if materials is not None else None),
            knowledge=(materials.knowledge if materials is not None else ()),
        )
        if self.release_expectation is not None:
            expected = self.release_expectation
            observed = (
                self.agent_id,
                self.prompt_ref,
                prompt_version,
                self.schema_ref,
                schema_version,
                safety_policy_version,
                knowledge_refs,
                asset_digest,
            )
            approved = (
                expected.agent_id,
                expected.prompt_ref,
                expected.prompt_version,
                expected.schema_ref,
                expected.schema_version,
                expected.safety_policy_version,
                expected.knowledge_refs,
                expected.asset_digest,
            )
            if observed != approved:
                raise MultimodalContractBindingError("ACTIVE_RELEASE_CONTRACT_MISMATCH")
        return ResolvedMultimodalContracts(
            prompt_ref=self.prompt_ref,
            prompt_version=prompt_version,
            schema_ref=self.schema_ref,
            schema_version=schema_version,
            agent_id=self.agent_id,
            output_schema=_canonical(registry_schema),
            safety_policy_version=safety_policy_version,
            knowledge_refs=knowledge_refs,
            asset_digest=asset_digest,
            prompt_execution_plan=PromptExecutionPlan(
                prompt_ref=self.prompt_ref,
                prompt_version=prompt_version,
                template=prompt.template,
                system_policy_ref=prompt.system_policy_ref,
                safety_policy_version=safety_policy_version,
                knowledge_refs=knowledge_refs,
                asset_digest=asset_digest,
                system_policy=(
                    materials.system_policy.content if materials is not None else ""
                ),
                system_policy_digest=(
                    materials.system_policy.content_digest
                    if materials is not None
                    else ""
                ),
                knowledge_materials=(
                    tuple(
                        KnowledgeExecutionPayload(
                            knowledge_ref=item.knowledge_ref,
                            content=item.content,
                            source_ref=item.source_ref,
                            license_ref=item.license_ref,
                            evidence_level=item.evidence_level,
                            content_digest=item.content_digest,
                        )
                        for item in materials.knowledge
                    )
                    if materials is not None
                    else ()
                ),
                material_digest=(
                    materials.material_digest if materials is not None else ""
                ),
            ),
        )


async def _resolve(registry: object, **kwargs: Any) -> Any:
    result = registry.resolve(**kwargs)  # type: ignore[attr-defined]
    return await result if inspect.isawaitable(result) else result


def _canonical(value: Any) -> Any:
    """Compare frozen registry JSON with ordinary client JSON structurally."""

    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


__all__ = [
    "MultimodalContractBindingError",
    "MultimodalContractRegistryBinding",
    "ReleaseContractExpectation",
    "ResolvedMultimodalContracts",
]
