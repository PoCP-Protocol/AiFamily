"""Immutable atomic release set for one governed multimodal runtime."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from backend.intelligence.model_gateway.budget import ModelBudgetRuntime
from backend.intelligence.model_gateway.contracts import DataClass
from backend.intelligence.safety.runtime import SafetyRuntime

from .multimodal_routing import MultimodalRouter
from .release_bundle import FamilyExperienceReleaseBundle


class FamilyExperienceReleaseSetError(ValueError):
    """Bundles and runtime configuration cannot form one atomic release set."""


@dataclass(frozen=True, slots=True)
class FamilyExperienceReleaseSet:
    release_set_id: str
    environment: str
    use_case: str
    data_class: DataClass
    provider_ids: tuple[str, ...]
    bundle_ids: tuple[str, ...]
    routing_policy_version: str
    route_config_digest: str
    rate_card_version: str
    rate_card_digest: str
    budget_policy_version: str
    budget_policy_digest: str
    agent_id: str
    prompt_ref: str
    prompt_version: str
    schema_ref: str
    schema_version: str
    safety_policy_version: str
    safety_policy_digest: str
    knowledge_refs: tuple[str, ...]
    asset_digest: str
    runtime_config_digest: str
    draft_only: bool = True
    may_mutate_business_state: bool = False

    def __post_init__(self) -> None:
        required = (
            self.release_set_id,
            self.environment,
            self.use_case,
            self.routing_policy_version,
            self.route_config_digest,
            self.rate_card_version,
            self.rate_card_digest,
            self.budget_policy_version,
            self.budget_policy_digest,
            self.agent_id,
            self.prompt_ref,
            self.prompt_version,
            self.schema_ref,
            self.schema_version,
            self.safety_policy_version,
            self.safety_policy_digest,
            self.asset_digest,
            self.runtime_config_digest,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise FamilyExperienceReleaseSetError("RELEASE_SET_FIELDS_REQUIRED")
        if not self.provider_ids or len(self.provider_ids) != len(self.bundle_ids):
            raise FamilyExperienceReleaseSetError("RELEASE_SET_PROVIDER_BINDING_INVALID")
        if len(set(self.provider_ids)) != len(self.provider_ids):
            raise FamilyExperienceReleaseSetError("RELEASE_SET_PROVIDER_DUPLICATE")
        if len(set(self.bundle_ids)) != len(self.bundle_ids):
            raise FamilyExperienceReleaseSetError("RELEASE_SET_BUNDLE_DUPLICATE")
        if not self.knowledge_refs or any(not ref for ref in self.knowledge_refs):
            raise FamilyExperienceReleaseSetError("RELEASE_SET_KNOWLEDGE_REQUIRED")
        if self.draft_only is not True or self.may_mutate_business_state is not False:
            raise FamilyExperienceReleaseSetError("RELEASE_SET_DRAFT_BOUNDARY_REQUIRED")


def build_family_experience_release_set(
    *,
    bundles: tuple[FamilyExperienceReleaseBundle, ...],
    router: MultimodalRouter,
    budget_runtime: ModelBudgetRuntime,
    safety_runtime: SafetyRuntime,
) -> FamilyExperienceReleaseSet:
    """Bind separately approved provider bundles into one content-addressed set."""

    if not bundles:
        raise FamilyExperienceReleaseSetError("RELEASE_SET_BUNDLES_REQUIRED")
    by_provider = {bundle.provider_id: bundle for bundle in bundles}
    if len(by_provider) != len(bundles):
        raise FamilyExperienceReleaseSetError("RELEASE_SET_PROVIDER_DUPLICATE")
    if set(by_provider) != set(router.provider_ids):
        raise FamilyExperienceReleaseSetError("RELEASE_SET_ROUTE_CATALOG_MISMATCH")
    ordered = tuple(by_provider[provider_id] for provider_id in router.provider_ids)
    first = ordered[0]
    common_fields = (
        "environment",
        "use_case",
        "data_class",
        "agent_id",
        "prompt_ref",
        "prompt_version",
        "schema_ref",
        "schema_version",
        "safety_policy_version",
        "knowledge_refs",
        "asset_digest",
        "routing_policy_version",
        "rate_card_version",
        "budget_policy_version",
        "draft_only",
        "may_mutate_business_state",
    )
    for bundle in ordered[1:]:
        if any(getattr(bundle, name) != getattr(first, name) for name in common_fields):
            raise FamilyExperienceReleaseSetError("RELEASE_SET_BUNDLE_CONTRACT_MISMATCH")
    for provider_id, bundle in zip(router.provider_ids, ordered, strict=True):
        profile = router.profile(provider_id)
        if (bundle.model, bundle.model_version) != (profile.model, profile.model_version):
            raise FamilyExperienceReleaseSetError("RELEASE_SET_MODEL_MISMATCH")
    if first.environment != budget_runtime.environment:
        raise FamilyExperienceReleaseSetError("RELEASE_SET_ENVIRONMENT_MISMATCH")
    if first.routing_policy_version != router.policy_version:
        raise FamilyExperienceReleaseSetError("RELEASE_SET_ROUTING_POLICY_MISMATCH")
    if first.rate_card_version != budget_runtime.rate_card.version:
        raise FamilyExperienceReleaseSetError("RELEASE_SET_RATE_CARD_MISMATCH")
    if first.budget_policy_version != budget_runtime.policy.version:
        raise FamilyExperienceReleaseSetError("RELEASE_SET_BUDGET_POLICY_MISMATCH")
    if first.safety_policy_version != safety_runtime.policy_version:
        raise FamilyExperienceReleaseSetError("RELEASE_SET_SAFETY_POLICY_MISMATCH")

    runtime_manifest = {
        "routing_policy_version": router.policy_version,
        "route_config_digest": router.configuration_digest,
        "rate_card_version": budget_runtime.rate_card.version,
        "rate_card_digest": budget_runtime.rate_card.configuration_digest,
        "budget_policy_version": budget_runtime.policy.version,
        "budget_policy_digest": budget_runtime.policy.configuration_digest,
        "safety_policy_version": safety_runtime.policy_version,
        "safety_policy_digest": safety_runtime.configuration_digest,
    }
    runtime_config_digest = _digest(runtime_manifest)
    manifest = {
        "environment": first.environment,
        "use_case": first.use_case,
        "data_class": first.data_class,
        "provider_ids": list(router.provider_ids),
        "bundle_ids": [bundle.bundle_id for bundle in ordered],
        "agent_id": first.agent_id,
        "prompt_ref": first.prompt_ref,
        "prompt_version": first.prompt_version,
        "schema_ref": first.schema_ref,
        "schema_version": first.schema_version,
        "safety_policy_version": first.safety_policy_version,
        "knowledge_refs": list(first.knowledge_refs),
        "asset_digest": first.asset_digest,
        "runtime": runtime_manifest,
        "runtime_config_digest": runtime_config_digest,
        "draft_only": True,
        "may_mutate_business_state": False,
    }
    return FamilyExperienceReleaseSet(
        release_set_id=_digest(manifest),
        environment=first.environment,
        use_case=first.use_case,
        data_class=first.data_class,
        provider_ids=router.provider_ids,
        bundle_ids=tuple(bundle.bundle_id for bundle in ordered),
        routing_policy_version=router.policy_version,
        route_config_digest=router.configuration_digest,
        rate_card_version=budget_runtime.rate_card.version,
        rate_card_digest=budget_runtime.rate_card.configuration_digest,
        budget_policy_version=budget_runtime.policy.version,
        budget_policy_digest=budget_runtime.policy.configuration_digest,
        agent_id=first.agent_id,
        prompt_ref=first.prompt_ref,
        prompt_version=first.prompt_version,
        schema_ref=first.schema_ref,
        schema_version=first.schema_version,
        safety_policy_version=first.safety_policy_version,
        safety_policy_digest=safety_runtime.configuration_digest,
        knowledge_refs=first.knowledge_refs,
        asset_digest=first.asset_digest,
        runtime_config_digest=runtime_config_digest,
    )


def validate_release_set_runtime(
    release_set: FamilyExperienceReleaseSet,
    *,
    router: MultimodalRouter,
    budget_runtime: ModelBudgetRuntime,
    safety_runtime: SafetyRuntime,
) -> None:
    """Detect same-version runtime drift using content digests."""

    if release_set.provider_ids != router.provider_ids:
        raise FamilyExperienceReleaseSetError("RELEASE_SET_ROUTE_CATALOG_MISMATCH")
    checks = (
        release_set.routing_policy_version == router.policy_version,
        release_set.route_config_digest == router.configuration_digest,
        release_set.rate_card_version == budget_runtime.rate_card.version,
        release_set.rate_card_digest == budget_runtime.rate_card.configuration_digest,
        release_set.budget_policy_version == budget_runtime.policy.version,
        release_set.budget_policy_digest == budget_runtime.policy.configuration_digest,
        release_set.safety_policy_version == safety_runtime.policy_version,
        release_set.safety_policy_digest == safety_runtime.configuration_digest,
    )
    if not all(checks):
        raise FamilyExperienceReleaseSetError("RELEASE_SET_RUNTIME_CONFIG_DRIFT")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "FamilyExperienceReleaseSet",
    "FamilyExperienceReleaseSetError",
    "build_family_experience_release_set",
    "validate_release_set_runtime",
]
