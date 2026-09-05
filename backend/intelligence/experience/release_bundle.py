"""Immutable release manifest for the governed family-experience AI slice.

The generic evaluation catalog admits a provider/model/report candidate.  A
deployable family experience also needs an exact Prompt, Schema, safety policy
and signed human approval.  This module binds those existing artifacts into a
metadata-only manifest; it neither deploys a model nor writes a family fact.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.intelligence.evaluation.release_control import ReleaseControlEvent
from backend.intelligence.evaluation.release_gate import ReleaseDecision
from backend.intelligence.evaluation.release_persistence import decision_fingerprint
from backend.intelligence.model_gateway.contracts import DataClass
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.provider_registry import ProviderRegistry

from .asset_digest import family_experience_contract_asset_digest
from .standard_assets import FamilyExperienceAssetBundle

_VALID_DATA_CLASSES = frozenset(
    {"SYNTHETIC", "OPERATIONAL_TEXT", "FAMILY_PRIVATE_TEXT", "MINOR_PERSONAL_DATA"}
)


class FamilyExperienceReleaseBundleError(ValueError):
    """Raised when release artifacts cannot form one governed bundle."""


@dataclass(frozen=True, slots=True)
class FamilyExperienceReleaseBundle:
    """Metadata-only deployment input after evaluation and human approval."""

    bundle_id: str
    candidate_id: str
    environment: str
    use_case: str
    agent_id: str
    provider_id: str
    model: str
    model_version: str
    prompt_ref: str
    prompt_version: str
    schema_ref: str
    schema_version: str
    safety_policy_version: str
    routing_policy_version: str
    rate_card_version: str
    budget_policy_version: str
    knowledge_refs: tuple[str, ...]
    data_class: DataClass
    report_ref: str
    decision_id: str
    control_id: str
    approval_signature_ref: str
    approval_signature_algorithm: str
    approved_by: str
    approved_at: datetime
    asset_digest: str
    human_gate_rule: str
    draft_only: bool = True
    may_mutate_business_state: bool = False

    def __post_init__(self) -> None:
        required = (
            self.bundle_id,
            self.candidate_id,
            self.environment,
            self.use_case,
            self.agent_id,
            self.provider_id,
            self.model,
            self.model_version,
            self.prompt_ref,
            self.prompt_version,
            self.schema_ref,
            self.schema_version,
            self.safety_policy_version,
            self.routing_policy_version,
            self.rate_card_version,
            self.budget_policy_version,
            self.report_ref,
            self.decision_id,
            self.control_id,
            self.approval_signature_ref,
            self.approval_signature_algorithm,
            self.approved_by,
            self.asset_digest,
            self.human_gate_rule,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise FamilyExperienceReleaseBundleError("RELEASE_BUNDLE_FIELDS_REQUIRED")
        if not self.knowledge_refs or any(not ref for ref in self.knowledge_refs):
            raise FamilyExperienceReleaseBundleError("RELEASE_KNOWLEDGE_REFS_REQUIRED")
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise FamilyExperienceReleaseBundleError("RELEASE_APPROVAL_TIME_MUST_BE_AWARE")
        if self.approved_by.startswith("ai:"):
            raise FamilyExperienceReleaseBundleError("AI_RELEASE_APPROVER_NOT_ALLOWED")
        if self.data_class not in _VALID_DATA_CLASSES:
            raise FamilyExperienceReleaseBundleError("RELEASE_DATA_CLASS_INVALID")
        if self.human_gate_rule != "REVIEW_REQUIRED":
            raise FamilyExperienceReleaseBundleError("RELEASE_HUMAN_GATE_REQUIRED")
        if self.draft_only is not True or self.may_mutate_business_state is not False:
            raise FamilyExperienceReleaseBundleError("RELEASE_DRAFT_ONLY_BOUNDARY_REQUIRED")


def build_family_experience_release_bundle(
    *,
    assets: FamilyExperienceAssetBundle,
    decision: ReleaseDecision,
    approval: ReleaseControlEvent,
    provider_registry: ProviderRegistry,
    data_class: DataClass,
    routing_policy_version: str,
    rate_card_version: str,
    budget_policy_version: str,
) -> FamilyExperienceReleaseBundle:
    """Bind evaluated, published and human-approved artifacts or fail closed."""

    if not isinstance(assets, FamilyExperienceAssetBundle):
        raise FamilyExperienceReleaseBundleError("FAMILY_EXPERIENCE_ASSETS_REQUIRED")
    if assets.status != "PUBLISHED":
        raise FamilyExperienceReleaseBundleError("PUBLISHED_ASSETS_REQUIRED")
    if not isinstance(decision, ReleaseDecision):
        raise FamilyExperienceReleaseBundleError("RELEASE_DECISION_REQUIRED")
    if not decision.admitted or decision.failures:
        raise FamilyExperienceReleaseBundleError("ADMITTED_RELEASE_DECISION_REQUIRED")
    if not isinstance(approval, ReleaseControlEvent):
        raise FamilyExperienceReleaseBundleError("RELEASE_APPROVAL_REQUIRED")
    decision_id = decision_fingerprint(decision)
    if (
        approval.kind != "APPROVAL"
        or approval.target_candidate_id is not None
        or approval.decision_id != decision_id
        or approval.candidate_id != decision.candidate_id
        or approval.environment != decision.environment
    ):
        raise FamilyExperienceReleaseBundleError("RELEASE_APPROVAL_MISMATCH")
    if approval.actor_id.startswith("ai:"):
        raise FamilyExperienceReleaseBundleError("AI_RELEASE_APPROVER_NOT_ALLOWED")
    if not isinstance(provider_registry, ProviderRegistry):
        raise FamilyExperienceReleaseBundleError("PROVIDER_REGISTRY_REQUIRED")
    try:
        provider = provider_registry.admit(
            decision.provider_id,
            data_class=data_class,
            environment=decision.environment,
        )
    except ModelGatewayError as error:
        raise FamilyExperienceReleaseBundleError("RELEASE_PROVIDER_NOT_ADMITTED") from error
    if (
        provider.provider_id != decision.provider_id
        or provider.model != decision.model
        or provider.model_version != decision.model_version
    ):
        raise FamilyExperienceReleaseBundleError("RELEASE_PROVIDER_MODEL_MISMATCH")
    if assets.schema.human_gate_rule != "REVIEW_REQUIRED":
        raise FamilyExperienceReleaseBundleError("RELEASE_HUMAN_GATE_REQUIRED")
    runtime_versions = (
        routing_policy_version,
        rate_card_version,
        budget_policy_version,
    )
    if not all(isinstance(value, str) and value.strip() for value in runtime_versions):
        raise FamilyExperienceReleaseBundleError("RELEASE_RUNTIME_POLICY_VERSIONS_REQUIRED")

    asset_digest = family_experience_contract_asset_digest(
        prompt=assets.prompt,
        schema=assets.schema,
        system_policy=assets.system_policy,
        knowledge=assets.knowledge,
    )
    manifest = {
        "candidate_id": decision.candidate_id,
        "environment": decision.environment,
        "provider_id": decision.provider_id,
        "model": decision.model,
        "model_version": decision.model_version,
        "prompt_ref": assets.prompt.prompt_ref,
        "prompt_version": assets.prompt.version,
        "schema_ref": assets.schema.schema_ref,
        "schema_version": assets.schema.version,
        "safety_policy_version": assets.prompt.safety_policy_version,
        "routing_policy_version": routing_policy_version,
        "rate_card_version": rate_card_version,
        "budget_policy_version": budget_policy_version,
        "knowledge_refs": list(assets.prompt.knowledge_refs),
        "data_class": str(data_class),
        "report_ref": decision.report_ref,
        "decision_id": decision_id,
        "control_id": approval.control_id,
        "asset_digest": asset_digest,
    }
    return FamilyExperienceReleaseBundle(
        bundle_id=_digest(manifest),
        candidate_id=decision.candidate_id,
        environment=decision.environment,
        use_case=assets.prompt.use_case,
        agent_id=assets.prompt.agent_id,
        provider_id=decision.provider_id,
        model=decision.model,
        model_version=decision.model_version,
        prompt_ref=assets.prompt.prompt_ref,
        prompt_version=assets.prompt.version,
        schema_ref=assets.schema.schema_ref,
        schema_version=assets.schema.version,
        safety_policy_version=assets.prompt.safety_policy_version,
        routing_policy_version=routing_policy_version,
        rate_card_version=rate_card_version,
        budget_policy_version=budget_policy_version,
        knowledge_refs=assets.prompt.knowledge_refs,
        data_class=data_class,
        report_ref=decision.report_ref,
        decision_id=decision_id,
        control_id=approval.control_id,
        approval_signature_ref=approval.signature_ref,
        approval_signature_algorithm=approval.signature_algorithm,
        approved_by=approval.actor_id,
        approved_at=approval.created_at,
        asset_digest=asset_digest,
        human_gate_rule=assets.schema.human_gate_rule,
    )


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


__all__ = [
    "FamilyExperienceReleaseBundle",
    "FamilyExperienceReleaseBundleError",
    "build_family_experience_release_bundle",
    "family_experience_contract_asset_digest",
]
