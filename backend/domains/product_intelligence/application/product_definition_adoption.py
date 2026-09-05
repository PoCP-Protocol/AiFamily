"""Execute an accepted Human Gate action as a ProductDefinition DRAFT."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.intelligence.human_gate.contracts import ActorType, NamedActionRequest
from backend.platform.audit import AuditEvent, AuditRecorder

from ..domain.entities import GrowthProductKind, ProductConcept, ProductDefinition
from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceForbiddenError,
    ProductIntelligenceNotFoundError,
    ProductIntelligenceValidationError,
)
from ..domain.zone_entities import ProductZoneAssessment

ADOPT_PRODUCT_DEFINITION_ACTION = "ADOPT_PRODUCT_CONCEPT_AS_DEFINITION"
ADOPT_PRODUCT_DEFINITION_PERMISSION = "product_intelligence.product_definition.adopt"
ADOPTION_PURPOSE = "service_product_definition_adoption"

_ZONE_MAP = {
    "COMMODITY": "HOMOGENEOUS",
    "ADVANTAGE": "ADVANTAGE",
    "UNIQUE": "UNIQUE_CANDIDATE",
}


def _refs(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values)
    if not normalized or any(not value for value in normalized):
        raise ValueError(f"{field_name}_must_not_be_empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name}_must_be_unique")
    return normalized


class ProductDefinitionAdoptionArguments(BaseModel):
    """Strict snapshot copied from a reviewed ActionProposal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    concept_id: str = Field(min_length=1)
    zone_assessment_id: str = Field(min_length=1)
    source_decision_draft_ref: str = Field(min_length=1)
    product_kind: GrowthProductKind
    duration_days: int = Field(gt=0, le=180)
    primary_contradiction: str = Field(min_length=1)
    demand_ref: str = Field(min_length=1)
    market_insight_refs: tuple[str, ...]
    component_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]
    success_metric_ids: tuple[str, ...]
    guardrail_ids: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...]
    pause_policy: str = Field(min_length=1)
    human_gate_policy: str = Field(min_length=1)

    @field_validator(
        "market_insight_refs",
        "component_ids",
        "skill_ids",
        "success_metric_ids",
        "stop_conditions",
    )
    @classmethod
    def _required_refs(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _refs(value, info.field_name)

    @field_validator("guardrail_ids")
    @classmethod
    def _optional_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _refs(value, "guardrail_ids") if value else value

    @field_validator(
        "concept_id",
        "zone_assessment_id",
        "source_decision_draft_ref",
        "product_kind",
        "primary_contradiction",
        "demand_ref",
        "pause_policy",
        "human_gate_policy",
    )
    @classmethod
    def _trim_text(cls, value: str) -> str:
        return value.strip()


class ProductDefinitionAdoptionRepository(Protocol):
    async def load_product_concept(self, entity_id: str, tenant_scope: str) -> ProductConcept: ...

    async def load_zone_assessment(
        self, entity_id: str, tenant_scope: str
    ) -> ProductZoneAssessment: ...

    async def load_product_definition(
        self, entity_id: str, tenant_scope: str
    ) -> ProductDefinition: ...

    async def create_product_definition_if_absent(
        self, entity: ProductDefinition
    ) -> tuple[ProductDefinition, bool]: ...

    async def flush_audit(self, recorder: AuditRecorder) -> int: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class ProductDefinitionAdoptionAuthorizer(Protocol):
    async def is_allowed(self, *, actor_id: str, tenant_scope: str, permission: str) -> bool: ...


def _definition_id(tenant_scope: str, idempotency_key: str) -> str:
    identity = f"{len(tenant_scope)}:{tenant_scope}:{idempotency_key}"
    return f"product-definition:{uuid5(NAMESPACE_URL, identity)}"


def _request_hash(request: NamedActionRequest) -> str:
    payload = {
        "request_id": request.request_id,
        "action_name": request.action_name,
        "action_arguments": dict(request.action_arguments),
        "task_id": request.task_id,
        "proposal_id": request.proposal_id,
        "decision_id": request.decision_id,
        "actor_id": request.actor_id,
        "actor_type": request.actor_type.value,
        "scope": {
            "tenant_id": request.scope.tenant_id,
            "family_id": request.scope.family_id,
            "subject_ids": request.scope.subject_ids,
            "purpose": request.scope.purpose,
            "consent_version": request.scope.consent_version,
            "correlation_id": request.scope.correlation_id,
        },
        "provenance_ref": request.provenance_ref,
        "idempotency_key": request.idempotency_key,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256(canonical.encode()).hexdigest()


def _snapshot_hash(definition: ProductDefinition) -> str:
    spec = definition.education_spec
    if spec is None or spec.adoption is None:
        raise ProductIntelligenceConflictError("product_definition_replay_shape_mismatch")
    return spec.adoption.request_hash


def _parse_arguments(request: NamedActionRequest) -> ProductDefinitionAdoptionArguments:
    try:
        return ProductDefinitionAdoptionArguments.model_validate(dict(request.action_arguments))
    except ValidationError as exc:
        raise ProductIntelligenceValidationError(
            "product_definition_adoption_arguments_invalid"
        ) from exc


async def execute_product_definition_named_action(
    repo: ProductDefinitionAdoptionRepository,
    request: NamedActionRequest,
    *,
    human_actor_authorizer: ProductDefinitionAdoptionAuthorizer,
    recorder: AuditRecorder,
) -> tuple[ProductDefinition, bool]:
    """Create one DRAFT from an already accepted, authorized Named Action."""

    if not isinstance(request, NamedActionRequest):
        raise ProductIntelligenceValidationError("product_definition_named_action_request_invalid")
    if request.action_name != ADOPT_PRODUCT_DEFINITION_ACTION:
        raise ProductIntelligenceValidationError("product_definition_named_action_not_supported")
    if request.actor_type is not ActorType.OPERATOR:
        raise ProductIntelligenceForbiddenError("product_definition_adoption_requires_operator")
    arguments = _parse_arguments(request)
    scope = request.scope
    if scope.family_id is not None or scope.purpose != ADOPTION_PURPOSE:
        raise ProductIntelligenceForbiddenError("product_definition_adoption_scope_invalid")
    if scope.subject_ids != (arguments.concept_id, arguments.zone_assessment_id):
        raise ProductIntelligenceForbiddenError("product_definition_adoption_subject_scope_invalid")
    if scope.consent_version.strip().upper() in {"N/A", "NA", "NONE", "NOT_APPLICABLE"}:
        raise ProductIntelligenceForbiddenError(
            "product_definition_adoption_processing_basis_invalid"
        )
    request_hash = _request_hash(request)
    definition_id = _definition_id(scope.tenant_id, request.idempotency_key)
    try:
        existing = await repo.load_product_definition(definition_id, scope.tenant_id)
    except ProductIntelligenceNotFoundError:
        existing = None
    if existing is not None:
        if _snapshot_hash(existing) != request_hash:
            raise ProductIntelligenceConflictError("product_definition_idempotency_replay_mismatch")
        return existing, True

    if not await human_actor_authorizer.is_allowed(
        actor_id=request.actor_id,
        tenant_scope=scope.tenant_id,
        permission=ADOPT_PRODUCT_DEFINITION_PERMISSION,
    ):
        raise ProductIntelligenceForbiddenError("product_definition_adoption_permission_required")

    concept = await repo.load_product_concept(arguments.concept_id, scope.tenant_id)
    if concept.status == "RETIRED":
        raise ProductIntelligenceConflictError("retired_product_concept_cannot_be_adopted")
    assessment = await repo.load_zone_assessment(arguments.zone_assessment_id, scope.tenant_id)
    if assessment.status != "APPROVED" or assessment.approved_zone is None:
        raise ProductIntelligenceValidationError(
            "approved_zone_assessment_required_for_product_definition"
        )
    if assessment.subject_ref != concept.id:
        raise ProductIntelligenceValidationError("zone_assessment_product_concept_mismatch")
    zone = _ZONE_MAP[assessment.approved_zone]
    now = datetime.now(UTC)
    definition = ProductDefinition(
        id=definition_id,
        created_at=now,
        updated_at=now,
        created_by=request.actor_id,
        tenant_scope=scope.tenant_id,
        concept_id=concept.id,
        product_kind=arguments.product_kind,
        duration_days=arguments.duration_days,
        zone=zone,
        primary_contradiction=arguments.primary_contradiction,
        demand_ref=arguments.demand_ref,
        market_insight_refs=list(arguments.market_insight_refs),
        component_ids=list(arguments.component_ids),
        education_spec={
            "product_kind": arguments.product_kind,
            "duration_days": arguments.duration_days,
            "zone": zone,
            "primary_contradiction": arguments.primary_contradiction,
            "component_ids": list(arguments.component_ids),
            "skill_ids": list(arguments.skill_ids),
            "success_metric_ids": list(arguments.success_metric_ids),
            "guardrail_ids": list(arguments.guardrail_ids),
            "stop_conditions": list(arguments.stop_conditions),
            "pause_policy": arguments.pause_policy,
            "human_gate_policy": arguments.human_gate_policy,
            "adoption": {
                "action_name": request.action_name,
                "request_id": request.request_id,
                "request_hash": request_hash,
                "task_id": request.task_id,
                "proposal_id": request.proposal_id,
                "decision_id": request.decision_id,
                "reviewer_actor_id": request.actor_id,
                "reviewer_actor_type": request.actor_type.value,
                "tenant_scope": scope.tenant_id,
                "purpose": scope.purpose,
                "processing_basis_ref": scope.consent_version,
                "provenance_ref": request.provenance_ref,
                "source_decision_draft_ref": arguments.source_decision_draft_ref,
                "zone_assessment_ref": assessment.id,
                "zone_assessment_version": assessment.version,
                "zone_policy_version_id": assessment.zone_policy_version_id,
                "approved_zone": assessment.approved_zone,
            },
        },
    )
    try:
        persisted, created = await repo.create_product_definition_if_absent(definition)
        if not created:
            if _snapshot_hash(persisted) != request_hash:
                raise ProductIntelligenceConflictError(
                    "product_definition_idempotency_replay_mismatch"
                )
            return persisted, True

        recorder.record(
            AuditEvent(
                actor_id=request.actor_id,
                tenant_id=scope.tenant_id,
                action=ADOPT_PRODUCT_DEFINITION_ACTION,
                resource_type="ProductDefinition",
                resource_id=definition.id,
                reason=f"accepted Human Gate decision {request.decision_id}",
                correlation_id=scope.correlation_id,
                after={
                    "status": definition.status,
                    "concept_id": concept.id,
                    "zone_assessment_ref": assessment.id,
                    "zone_assessment_version": assessment.version,
                    "approved_zone": assessment.approved_zone,
                    "zone": definition.zone,
                    "request_id": request.request_id,
                    "decision_id": request.decision_id,
                },
            )
        )
        await repo.flush_audit(recorder)
        await repo.commit()
    except Exception:
        await repo.rollback()
        raise
    return definition, False


__all__ = [
    "ADOPTION_PURPOSE",
    "ADOPT_PRODUCT_DEFINITION_ACTION",
    "ADOPT_PRODUCT_DEFINITION_PERMISSION",
    "ProductDefinitionAdoptionArguments",
    "ProductDefinitionAdoptionAuthorizer",
    "ProductDefinitionAdoptionRepository",
    "execute_product_definition_named_action",
]
