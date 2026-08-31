"""Persist one immutable ProductPackage DRAFT and open its Human Gate proposal."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    ActorType,
    GateScope,
    HumanTask,
)

from ..domain.entities import ProductConcept
from ..domain.product_package_draft import (
    EvidenceAdmissionSnapshot,
    ProductPackageDraftContent,
    ProductPackageDraftVersion,
    ProductPackageEvidenceRequirement,
    product_package_content_hash,
)
from ..domain.zone_entities import ProductZoneAssessment
from .context import ActorContext
from .product_definition_adoption import (
    ADOPT_PRODUCT_DEFINITION_ACTION,
    ADOPTION_PURPOSE,
    ProductDefinitionAdoptionArguments,
)

PRODUCT_PACKAGE_SUBMIT_PERMISSION = "product_intelligence.product_package.submit"
PRODUCT_PACKAGE_READ_PERMISSION = "product_intelligence.product_package.read"
PRODUCT_PACKAGE_PROCESSING_BASIS = "processing-basis:internal-product-design:v1"


class ProductPackageSubmissionError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ProductPackageSubmissionForbiddenError(ProductPackageSubmissionError):
    pass


class ProductPackageSubmissionConflictError(ProductPackageSubmissionError):
    pass


@dataclass(frozen=True, slots=True)
class ProductPackageSubmissionInput:
    concept_id: str
    zone_assessment_id: str
    upstream_decision_draft_ref: str
    product_kind: str
    duration_days: int
    primary_contradiction: str
    demand_ref: str
    market_insight_refs: tuple[str, ...]
    competitor_evidence_refs: tuple[str, ...]
    component_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]
    success_metric_ids: tuple[str, ...]
    guardrail_ids: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    pause_policy: str
    human_gate_policy: str
    evidence_refs: tuple[str, ...]
    evidence_requirements: tuple[ProductPackageEvidenceRequirement, ...]
    evidence_admissions: tuple[EvidenceAdmissionSnapshot, ...]
    assumptions: tuple[str, ...]
    unknowns: tuple[str, ...]
    next_validation: str
    expires_at: datetime
    source_provenance_ref: str
    model_ref: str
    prompt_use_case_version: str
    confidence: float


@dataclass(frozen=True, slots=True)
class ProductPackageSubmissionResult:
    draft: ProductPackageDraftVersion
    task: HumanTask
    replayed: bool = False


class ProductPackageSubmissionRepository(Protocol):
    async def find_intent_replay(
        self,
        *,
        tenant_scope: str,
        actor_id: str,
        idempotency_key: str,
        intent_hash: str,
    ) -> ProductPackageSubmissionResult | None: ...

    async def find_exact_replay(
        self,
        *,
        tenant_scope: str,
        actor_id: str,
        idempotency_key: str,
        intent_hash: str,
        request_hash: str,
    ) -> ProductPackageSubmissionResult | None: ...

    async def load_product_concept(self, entity_id: str, tenant_scope: str) -> ProductConcept: ...

    async def load_zone_assessment(
        self, entity_id: str, tenant_scope: str
    ) -> ProductZoneAssessment: ...

    async def get(
        self, *, draft_id: str, tenant_scope: str
    ) -> ProductPackageSubmissionResult: ...

    async def persist_submission(
        self,
        *,
        draft: ProductPackageDraftVersion,
        proposal: ActionProposal,
        task_id: str,
        actor_id: str,
        idempotency_key: str,
        request_hash: str,
        intent_hash: str,
        source_draft_locator: str,
    ) -> ProductPackageSubmissionResult: ...


def _required_text(value: str, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductPackageSubmissionError(code)
    return value.strip()


def _bounded_text(value: str, code: str, maximum: int) -> str:
    normalized = _required_text(value, code)
    if len(normalized) > maximum:
        raise ProductPackageSubmissionError(f"{code}_TOO_LONG")
    return normalized


def _refs(values: tuple[str, ...], code: str, maximum: int = 512) -> tuple[str, ...]:
    normalized = tuple(_bounded_text(value, code, maximum) for value in values)
    if not normalized:
        raise ProductPackageSubmissionError(code)
    if len(set(normalized)) != len(normalized):
        raise ProductPackageSubmissionError(f"{code}_MUST_BE_UNIQUE")
    return normalized


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _request_payload(source: ProductPackageSubmissionInput) -> dict[str, object]:
    admission_payloads: list[dict[str, object]] = []
    for admission in source.evidence_admissions:
        payload = admission.model_dump(mode="json")
        # Evaluation time is operational metadata, not part of resolved intent identity.
        payload.pop("admitted_at", None)
        admission_payloads.append(payload)
    return {
        "concept_id": source.concept_id,
        "zone_assessment_id": source.zone_assessment_id,
        "upstream_decision_draft_ref": source.upstream_decision_draft_ref,
        "product_kind": source.product_kind,
        "duration_days": source.duration_days,
        "primary_contradiction": source.primary_contradiction,
        "demand_ref": source.demand_ref,
        "market_insight_refs": source.market_insight_refs,
        "competitor_evidence_refs": source.competitor_evidence_refs,
        "component_ids": source.component_ids,
        "skill_ids": source.skill_ids,
        "success_metric_ids": source.success_metric_ids,
        "guardrail_ids": source.guardrail_ids,
        "stop_conditions": source.stop_conditions,
        "pause_policy": source.pause_policy,
        "human_gate_policy": source.human_gate_policy,
        "evidence_refs": source.evidence_refs,
        "evidence_requirements": tuple(
            item.model_dump(mode="json") for item in source.evidence_requirements
        ),
        "evidence_admissions": tuple(admission_payloads),
        "assumptions": source.assumptions,
        "unknowns": source.unknowns,
        "next_validation": source.next_validation,
        "expires_at": source.expires_at,
        "source_provenance_ref": source.source_provenance_ref,
        "model_ref": source.model_ref,
        "prompt_use_case_version": source.prompt_use_case_version,
        "confidence": source.confidence,
    }


def _stable_id(kind: str, tenant_scope: str, actor_id: str, idempotency_key: str) -> str:
    seed = json.dumps(
        [tenant_scope, actor_id, idempotency_key],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"{kind}:{uuid5(NAMESPACE_URL, seed)}"


def _authorize(context: ActorContext) -> None:
    if (
        context.actor_type != "HUMAN"
        or PRODUCT_PACKAGE_SUBMIT_PERMISSION not in context.permissions
    ):
        raise ProductPackageSubmissionForbiddenError(
            "product_package_human_submit_permission_required"
        )


def authorize_product_package_submission(context: ActorContext) -> None:
    """Fail before any trusted-source lookup for an unauthorized caller."""

    _authorize(context)
    _bounded_text(context.tenant_scope, "TENANT_SCOPE_REQUIRED", 128)
    _bounded_text(context.actor_id, "ACTOR_ID_REQUIRED", 128)


def authorize_product_package_read(context: ActorContext) -> None:
    """Reject untrusted reads before opening a repository session."""

    if PRODUCT_PACKAGE_READ_PERMISSION not in context.permissions:
        raise ProductPackageSubmissionForbiddenError("PRODUCT_PACKAGE_READ_FORBIDDEN")
    _bounded_text(context.tenant_scope, "TENANT_SCOPE_REQUIRED", 128)
    _bounded_text(context.actor_id, "ACTOR_ID_REQUIRED", 128)


async def submit_product_package_draft(
    repo: ProductPackageSubmissionRepository,
    context: ActorContext,
    source: ProductPackageSubmissionInput,
    *,
    idempotency_key: str,
    intent_hash: str | None = None,
    source_draft_locator: str | None = None,
    now: datetime | None = None,
) -> ProductPackageSubmissionResult:
    """Freeze the server-resolved design and atomically open an OPEN proposal."""

    authorize_product_package_submission(context)
    tenant_scope = _bounded_text(context.tenant_scope, "TENANT_SCOPE_REQUIRED", 128)
    actor_id = _bounded_text(context.actor_id, "ACTOR_ID_REQUIRED", 128)
    key = _bounded_text(idempotency_key, "IDEMPOTENCY_KEY_REQUIRED", 256)
    request_hash = _canonical_hash(_request_payload(source))
    frozen_intent_hash = _bounded_text(
        intent_hash or request_hash,
        "PRODUCT_PACKAGE_INTENT_HASH_REQUIRED",
        64,
    )
    if len(frozen_intent_hash) != 64:
        raise ProductPackageSubmissionError("PRODUCT_PACKAGE_INTENT_HASH_INVALID")
    frozen_source_locator = _bounded_text(
        source_draft_locator or source.source_provenance_ref,
        "PRODUCT_PACKAGE_SOURCE_DRAFT_LOCATOR_REQUIRED",
        256,
    )
    replay = await repo.find_exact_replay(
        tenant_scope=tenant_scope,
        actor_id=actor_id,
        idempotency_key=key,
        intent_hash=frozen_intent_hash,
        request_hash=request_hash,
    )
    if replay is not None:
        return replace(replay, replayed=True)

    created_at = now or datetime.now(UTC)
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ProductPackageSubmissionError("CREATED_AT_MUST_BE_TIMEZONE_AWARE")
    if source.expires_at.tzinfo is None or source.expires_at.utcoffset() is None:
        raise ProductPackageSubmissionError("EXPIRES_AT_MUST_BE_TIMEZONE_AWARE")
    if source.expires_at <= created_at:
        raise ProductPackageSubmissionError("PRODUCT_PACKAGE_DRAFT_EXPIRED")

    concept = await repo.load_product_concept(source.concept_id, tenant_scope)
    assessment = await repo.load_zone_assessment(source.zone_assessment_id, tenant_scope)
    if assessment.status != "APPROVED" or assessment.approved_zone is None:
        raise ProductPackageSubmissionError("APPROVED_ZONE_ASSESSMENT_REQUIRED")
    if assessment.subject_ref != concept.id:
        raise ProductPackageSubmissionError("ZONE_ASSESSMENT_CONCEPT_MISMATCH")

    evidence_refs = _refs(source.evidence_refs, "EVIDENCE_REFS_REQUIRED")
    evidence_admissions = tuple(source.evidence_admissions)
    evidence_requirements = tuple(source.evidence_requirements)
    requirement_refs = tuple(item.receipt_locator for item in evidence_requirements)
    admission_refs = tuple(item.receipt_id for item in evidence_admissions)
    if len(set(requirement_refs)) != len(requirement_refs):
        raise ProductPackageSubmissionError("EVIDENCE_REQUIREMENTS_MUST_BE_UNIQUE")
    if set(requirement_refs) != set(evidence_refs):
        raise ProductPackageSubmissionError("EVIDENCE_REQUIREMENTS_MUST_MATCH_REFS")
    if len(set(admission_refs)) != len(admission_refs):
        raise ProductPackageSubmissionError("EVIDENCE_ADMISSIONS_MUST_BE_UNIQUE")
    if set(admission_refs) != set(evidence_refs):
        raise ProductPackageSubmissionError("EVIDENCE_ADMISSIONS_MUST_MATCH_REFS")
    requirements_by_receipt = {item.receipt_locator: item for item in evidence_requirements}
    if any(
        admission.claim_type != requirements_by_receipt[admission.receipt_id].claim_type
        or admission.required_claim_refs
        != requirements_by_receipt[admission.receipt_id].required_claim_refs
        or admission.required_applicability_refs
        != requirements_by_receipt[admission.receipt_id].required_applicability_refs
        for admission in evidence_admissions
    ):
        raise ProductPackageSubmissionError("EVIDENCE_ADMISSIONS_MUST_MATCH_REQUIREMENTS")

    draft_id = _stable_id("product-package-draft", tenant_scope, actor_id, key)
    version_id = _stable_id("product-package-version", tenant_scope, actor_id, key)
    proposal_id = _stable_id("proposal", tenant_scope, actor_id, key)
    task_id = _stable_id("human-task", tenant_scope, actor_id, key)
    content = ProductPackageDraftContent(
        draft_id=draft_id,
        version_id=version_id,
        tenant_scope=tenant_scope,
        authored_by=actor_id,
        author_type=context.actor_type,
        created_at=created_at,
        expires_at=source.expires_at,
        concept_id=concept.id,
        zone_assessment_id=assessment.id,
        zone_assessment_version=assessment.version,
        zone_policy_version_id=assessment.zone_policy_version_id,
        approved_zone=assessment.approved_zone,
        upstream_decision_draft_ref=_required_text(
            source.upstream_decision_draft_ref, "UPSTREAM_DECISION_DRAFT_REF_REQUIRED"
        ),
        product_kind=source.product_kind,
        duration_days=source.duration_days,
        primary_contradiction=source.primary_contradiction,
        demand_ref=source.demand_ref,
        market_insight_refs=_refs(source.market_insight_refs, "MARKET_INSIGHT_REFS_REQUIRED"),
        competitor_evidence_refs=_refs(
            source.competitor_evidence_refs, "COMPETITOR_EVIDENCE_REFS_REQUIRED"
        ),
        component_ids=_refs(source.component_ids, "COMPONENT_IDS_REQUIRED"),
        skill_ids=_refs(source.skill_ids, "SKILL_IDS_REQUIRED"),
        success_metric_ids=_refs(source.success_metric_ids, "SUCCESS_METRIC_IDS_REQUIRED"),
        guardrail_ids=_refs(source.guardrail_ids, "GUARDRAIL_IDS_REQUIRED"),
        stop_conditions=_refs(source.stop_conditions, "STOP_CONDITIONS_REQUIRED", 2000),
        pause_policy=source.pause_policy,
        human_gate_policy=source.human_gate_policy,
        evidence_refs=evidence_refs,
        evidence_admissions=tuple(
            sorted(evidence_admissions, key=lambda item: item.receipt_id)
        ),
        assumptions=_refs(source.assumptions, "ASSUMPTIONS_REQUIRED", 2000),
        unknowns=_refs(source.unknowns, "UNKNOWNS_REQUIRED", 2000),
        next_validation=source.next_validation,
        source_draft_locator=frozen_source_locator,
        intent_hash=frozen_intent_hash,
        resolved_request_hash=request_hash,
        source_provenance_ref=source.source_provenance_ref,
        model_ref=source.model_ref,
        prompt_use_case_version=source.prompt_use_case_version,
        confidence=source.confidence,
    )
    draft = ProductPackageDraftVersion(
        **content.model_dump(mode="python"),
        content_hash=product_package_content_hash(content),
    )
    action_arguments = ProductDefinitionAdoptionArguments.model_validate(
        {
            "concept_id": draft.concept_id,
            "zone_assessment_id": draft.zone_assessment_id,
            "source_decision_draft_ref": draft.draft_id,
            "product_kind": draft.product_kind,
            "duration_days": draft.duration_days,
            "primary_contradiction": draft.primary_contradiction,
            "demand_ref": draft.demand_ref,
            "market_insight_refs": draft.market_insight_refs,
            "component_ids": draft.component_ids,
            "skill_ids": draft.skill_ids,
            "success_metric_ids": draft.success_metric_ids,
            "guardrail_ids": draft.guardrail_ids,
            "stop_conditions": draft.stop_conditions,
            "pause_policy": draft.pause_policy,
            "human_gate_policy": draft.human_gate_policy,
        }
    )
    proposal = ActionProposal(
        proposal_id=proposal_id,
        draft_id=draft.draft_id,
        draft_status="DRAFT",
        action_name=ADOPT_PRODUCT_DEFINITION_ACTION,
        action_arguments={
            key: tuple(value) if isinstance(value, list) else value
            for key, value in action_arguments.model_dump(mode="python").items()
        },
        scope=GateScope(
            tenant_id=tenant_scope,
            family_id=None,
            subject_ids=(draft.concept_id, draft.zone_assessment_id),
            purpose=ADOPTION_PURPOSE,
            consent_version=PRODUCT_PACKAGE_PROCESSING_BASIS,
            correlation_id=context.trace_id or f"trace:{draft.draft_id}",
        ),
        allowed_actor_types=(ActorType.OPERATOR,),
        risk_level="MEDIUM",
        provenance_ref=f"product-package-draft:{draft.draft_id}:{draft.content_hash}",
        created_at=draft.created_at,
        expires_at=draft.expires_at,
    )
    result = await repo.persist_submission(
        draft=draft,
        proposal=proposal,
        task_id=task_id,
        actor_id=actor_id,
        idempotency_key=key,
        request_hash=request_hash,
        intent_hash=frozen_intent_hash,
        source_draft_locator=frozen_source_locator,
    )
    return result


async def find_product_package_intent_replay(
    repo: ProductPackageSubmissionRepository,
    context: ActorContext,
    *,
    idempotency_key: str,
    intent_hash: str,
) -> ProductPackageSubmissionResult | None:
    """Return a frozen HTTP replay before mutable trusted sources are resolved."""

    authorize_product_package_submission(context)
    tenant_scope = _bounded_text(context.tenant_scope, "TENANT_SCOPE_REQUIRED", 128)
    actor_id = _bounded_text(context.actor_id, "ACTOR_ID_REQUIRED", 128)
    key = _bounded_text(idempotency_key, "IDEMPOTENCY_KEY_REQUIRED", 256)
    canonical_intent_hash = _bounded_text(
        intent_hash,
        "PRODUCT_PACKAGE_INTENT_HASH_REQUIRED",
        64,
    )
    if len(canonical_intent_hash) != 64:
        raise ProductPackageSubmissionError("PRODUCT_PACKAGE_INTENT_HASH_INVALID")
    replay = await repo.find_intent_replay(
        tenant_scope=tenant_scope,
        actor_id=actor_id,
        idempotency_key=key,
        intent_hash=canonical_intent_hash,
    )
    return replace(replay, replayed=True) if replay is not None else None


async def get_product_package_submission(
    repo: ProductPackageSubmissionRepository,
    context: ActorContext,
    *,
    draft_id: str,
) -> ProductPackageSubmissionResult:
    """Read one tenant-scoped immutable draft and its current review receipt."""

    authorize_product_package_read(context)
    tenant_scope = _bounded_text(context.tenant_scope, "TENANT_SCOPE_REQUIRED", 128)
    normalized_draft_id = _bounded_text(draft_id, "DRAFT_ID_REQUIRED", 160)
    return await repo.get(draft_id=normalized_draft_id, tenant_scope=tenant_scope)


__all__ = [
    "PRODUCT_PACKAGE_PROCESSING_BASIS",
    "PRODUCT_PACKAGE_READ_PERMISSION",
    "PRODUCT_PACKAGE_SUBMIT_PERMISSION",
    "ProductPackageSubmissionConflictError",
    "ProductPackageSubmissionError",
    "ProductPackageSubmissionForbiddenError",
    "ProductPackageSubmissionInput",
    "ProductPackageSubmissionRepository",
    "ProductPackageSubmissionResult",
    "authorize_product_package_read",
    "authorize_product_package_submission",
    "find_product_package_intent_replay",
    "get_product_package_submission",
    "submit_product_package_draft",
]
