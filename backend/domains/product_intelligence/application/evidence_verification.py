"""Materialize an immutable evidence receipt from an accepted Human Gate action."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from backend.intelligence.human_gate.contracts import (
    ActorType,
    DecisionOutcome,
    GateStatus,
    HumanTask,
    NamedActionRequest,
)
from backend.platform.audit import AuditEvent, AuditRecorder

from ..domain.entities import Evidence
from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceForbiddenError,
    ProductIntelligenceNotFoundError,
    ProductIntelligenceValidationError,
)
from ..domain.evidence_verification import (
    EvidenceVerificationReceipt,
    EvidenceVerificationReceiptContent,
    VerificationMethod,
    evidence_verification_receipt_hash,
)

VERIFY_PRODUCT_EVIDENCE_ACTION = "VERIFY_PRODUCT_EVIDENCE"
VERIFY_PRODUCT_EVIDENCE_PERMISSION = "product_intelligence.evidence.verify"
EVIDENCE_VERIFICATION_PURPOSE = "product_evidence_verification"
EVIDENCE_VERIFICATION_PROCESSING_BASIS = "processing-basis:product-research:v1"
EVIDENCE_VERIFICATION_POLICY_VERSION = "product-evidence-verification:v1"
EVIDENCE_VERIFICATION_MAX_VALIDITY = timedelta(days=30)
EVIDENCE_VERIFICATION_MAX_SCOPE_ITEMS = 32


def _text(value: str, field_name: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}_required")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{field_name}_too_long")
    return normalized


def _items(values: tuple[str, ...], field_name: str, maximum: int) -> tuple[str, ...]:
    normalized = tuple(_text(value, field_name, maximum) for value in values)
    if not normalized:
        raise ValueError(f"{field_name}_required")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name}_must_be_unique")
    return normalized


class EvidenceVerificationArguments(BaseModel):
    """Exact evidence snapshot and policy reviewed by the operator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1, max_length=160)
    evidence_version: int = Field(ge=1)
    evidence_record_hash: str = Field(min_length=64, max_length=64)
    evidence_ref: str = Field(min_length=1, max_length=512)
    claim_scope: tuple[str, ...]
    verification_methods: tuple[VerificationMethod, ...]
    applicability_scope: tuple[str, ...]
    criteria_refs: tuple[str, ...]
    verification_purpose: str = Field(min_length=1, max_length=96)
    verification_policy_version: str = Field(min_length=1, max_length=160)
    integrity_check: str = Field(pattern="^PASS$")
    relevance: str = Field(pattern="^RELEVANT$")
    valid_until: datetime

    @field_validator(
        "evidence_id",
        "evidence_record_hash",
        "evidence_ref",
        "verification_purpose",
        "verification_policy_version",
    )
    @classmethod
    def text_is_valid(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @field_validator("claim_scope", "applicability_scope")
    @classmethod
    def narrative_items_are_valid(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        normalized = _items(value, info.field_name, 2000)
        if len(normalized) > EVIDENCE_VERIFICATION_MAX_SCOPE_ITEMS:
            raise ValueError(f"{info.field_name}_too_many_items")
        return normalized

    @field_validator("criteria_refs")
    @classmethod
    def criteria_are_valid(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = _items(value, "criteria_refs", 512)
        if len(normalized) > EVIDENCE_VERIFICATION_MAX_SCOPE_ITEMS:
            raise ValueError("criteria_refs_too_many_items")
        return normalized

    @field_validator("verification_methods")
    @classmethod
    def methods_are_valid(
        cls, value: tuple[VerificationMethod, ...]
    ) -> tuple[VerificationMethod, ...]:
        if not value or len(set(value)) != len(value):
            raise ValueError("verification_methods_required_and_unique")
        required = {"SOURCE_OPENED", "EVIDENCE_RECORD_HASH_MATCHED"}
        if not required.issubset(set(value)):
            raise ValueError("verification_methods_missing_integrity_checks")
        return value

    @model_validator(mode="after")
    def valid_until_is_aware(self) -> EvidenceVerificationArguments:
        if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:
            raise ValueError("valid_until_must_be_aware")
        return self


class EvidenceVerificationReceiptRepository(Protocol):
    async def load_evidence(self, entity_id: str, tenant_scope: str) -> Evidence: ...

    async def load_human_task(self, task_id: str) -> HumanTask: ...

    async def load_receipt(
        self, receipt_id: str, tenant_scope: str
    ) -> EvidenceVerificationReceipt: ...

    async def create_receipt_if_absent(
        self, receipt: EvidenceVerificationReceipt
    ) -> tuple[EvidenceVerificationReceipt, bool]: ...

    async def flush_audit(self, recorder: AuditRecorder) -> int: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class EvidenceVerificationAuthorizer(Protocol):
    async def is_allowed(self, *, actor_id: str, tenant_scope: str, permission: str) -> bool: ...


def evidence_record_hash(evidence: Evidence) -> str:
    """Hash the immutable platform record snapshot, not external source bytes."""
    encoded = json.dumps(
        evidence.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _receipt_id(tenant_scope: str, idempotency_key: str) -> str:
    seed = json.dumps([tenant_scope, idempotency_key], ensure_ascii=False, separators=(",", ":"))
    return f"evidence-verification-receipt:{uuid5(NAMESPACE_URL, seed)}"


def _request_hash(request: NamedActionRequest, task: HumanTask) -> str:
    decision = task.decision
    if decision is None:
        raise ProductIntelligenceConflictError("evidence_verification_decision_missing")
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
        "decision_reason": decision.reason,
        "decided_at": decision.decided_at,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _validate_persistence_widths(request: NamedActionRequest) -> None:
    limits = {
        "tenant_scope": (request.scope.tenant_id, 128),
        "task_id": (request.task_id, 160),
        "proposal_id": (request.proposal_id, 160),
        "decision_id": (request.decision_id, 160),
        "request_id": (request.request_id, 160),
        "verifier_actor_id": (request.actor_id, 128),
    }
    for field_name, (value, maximum) in limits.items():
        try:
            _text(value, field_name, maximum)
        except ValueError as exc:
            raise ProductIntelligenceValidationError(
                f"evidence_verification_{field_name}_invalid"
            ) from exc


def _arguments(request: NamedActionRequest) -> EvidenceVerificationArguments:
    try:
        return EvidenceVerificationArguments.model_validate(dict(request.action_arguments))
    except ValidationError as exc:
        raise ProductIntelligenceValidationError(
            "evidence_verification_arguments_invalid"
        ) from exc


def _validate_task_lineage(
    task: HumanTask,
    request: NamedActionRequest,
    arguments: EvidenceVerificationArguments,
) -> None:
    decision = task.decision
    try:
        proposal_arguments = EvidenceVerificationArguments.model_validate(
            task.proposal.action_arguments
        )
    except ValidationError as exc:
        raise ProductIntelligenceConflictError(
            "evidence_verification_human_gate_lineage_mismatch"
        ) from exc
    if (
        task.task_id != request.task_id
        or task.status is not GateStatus.DECIDED
        or decision is None
        or decision.outcome is not DecisionOutcome.ACCEPT
        or task.action_request != request
        or task.proposal.proposal_id != request.proposal_id
        or task.proposal.action_name != VERIFY_PRODUCT_EVIDENCE_ACTION
        or proposal_arguments != arguments
        or task.proposal.allowed_actor_types != (ActorType.OPERATOR,)
        or decision.decision_id != request.decision_id
        or decision.actor_id != request.actor_id
        or decision.actor_type is not request.actor_type
        or not decision.reason
        or not decision.reason.strip()
        or decision.decided_at < task.proposal.created_at
    ):
        raise ProductIntelligenceConflictError(
            "evidence_verification_human_gate_lineage_mismatch"
        )


async def execute_evidence_verification_named_action(
    repo: EvidenceVerificationReceiptRepository,
    request: NamedActionRequest,
    *,
    human_actor_authorizer: EvidenceVerificationAuthorizer,
    recorder: AuditRecorder,
    now: datetime | None = None,
) -> tuple[EvidenceVerificationReceipt, bool]:
    """Create one receipt only from an exact accepted operator decision."""

    if not isinstance(request, NamedActionRequest):
        raise ProductIntelligenceValidationError(
            "evidence_verification_named_action_request_invalid"
        )
    if request.action_name != VERIFY_PRODUCT_EVIDENCE_ACTION:
        raise ProductIntelligenceValidationError("evidence_verification_named_action_not_supported")
    if request.actor_type is not ActorType.OPERATOR:
        raise ProductIntelligenceForbiddenError("evidence_verification_requires_operator")
    _validate_persistence_widths(request)
    arguments = _arguments(request)
    scope = request.scope
    if (
        scope.family_id is not None
        or scope.purpose != EVIDENCE_VERIFICATION_PURPOSE
        or scope.consent_version != EVIDENCE_VERIFICATION_PROCESSING_BASIS
        or scope.subject_ids != (arguments.evidence_id,)
        or arguments.verification_purpose != "product_package_admission"
        or arguments.verification_policy_version != EVIDENCE_VERIFICATION_POLICY_VERSION
    ):
        raise ProductIntelligenceForbiddenError("evidence_verification_scope_invalid")
    expected_provenance = (
        f"evidence-record-snapshot:{arguments.evidence_id}:{arguments.evidence_record_hash}"
    )
    if request.provenance_ref != expected_provenance:
        raise ProductIntelligenceForbiddenError("evidence_verification_provenance_invalid")

    task = await repo.load_human_task(request.task_id)
    _validate_task_lineage(task, request, arguments)
    decision = task.decision
    if decision is None:  # pragma: no cover - guarded by lineage validation
        raise ProductIntelligenceConflictError("evidence_verification_decision_missing")
    request_hash = _request_hash(request, task)
    receipt_id = _receipt_id(scope.tenant_id, request.idempotency_key)
    try:
        existing = await repo.load_receipt(receipt_id, scope.tenant_id)
    except ProductIntelligenceNotFoundError:
        existing = None
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ProductIntelligenceConflictError(
                "evidence_verification_receipt_replay_mismatch"
            )
        return existing, True

    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ProductIntelligenceValidationError("evidence_verification_now_must_be_aware")
    if arguments.valid_until <= current or arguments.valid_until <= decision.decided_at:
        raise ProductIntelligenceConflictError("evidence_verification_policy_window_expired")
    if arguments.valid_until > decision.decided_at + EVIDENCE_VERIFICATION_MAX_VALIDITY:
        raise ProductIntelligenceConflictError(
            "evidence_verification_policy_window_exceeds_maximum"
        )

    if not await human_actor_authorizer.is_allowed(
        actor_id=request.actor_id,
        tenant_scope=scope.tenant_id,
        permission=VERIFY_PRODUCT_EVIDENCE_PERMISSION,
    ):
        raise ProductIntelligenceForbiddenError("evidence_verification_permission_required")

    evidence = await repo.load_evidence(arguments.evidence_id, scope.tenant_id)
    if evidence.status != "ACTIVE":
        raise ProductIntelligenceConflictError("evidence_verification_source_not_active")
    if evidence.created_by.strip().casefold() == request.actor_id.strip().casefold():
        raise ProductIntelligenceForbiddenError("evidence_verification_four_eyes_required")
    if (
        evidence.version != arguments.evidence_version
        or evidence.evidence_ref != arguments.evidence_ref
        or evidence_record_hash(evidence) != arguments.evidence_record_hash
    ):
        raise ProductIntelligenceConflictError("evidence_verification_source_snapshot_changed")

    content = EvidenceVerificationReceiptContent(
        receipt_id=receipt_id,
        tenant_scope=scope.tenant_id,
        evidence_id=evidence.id,
        evidence_version=evidence.version,
        evidence_record_hash=arguments.evidence_record_hash,
        evidence_ref=evidence.evidence_ref,
        claim_scope=arguments.claim_scope,
        verification_methods=arguments.verification_methods,
        applicability_scope=arguments.applicability_scope,
        criteria_refs=arguments.criteria_refs,
        verification_purpose="product_package_admission",
        verification_policy_version=arguments.verification_policy_version,
        integrity_check=arguments.integrity_check,
        relevance=arguments.relevance,
        task_id=request.task_id,
        proposal_id=request.proposal_id,
        decision_id=request.decision_id,
        request_id=request.request_id,
        verifier_actor_id=request.actor_id,
        decision_reason=decision.reason.strip(),
        verified_at=decision.decided_at,
        valid_until=arguments.valid_until,
        recorded_at=current,
        supersedes_receipt_id=None,
        request_hash=request_hash,
    )
    receipt = EvidenceVerificationReceipt(
        **content.model_dump(mode="python"),
        receipt_hash=evidence_verification_receipt_hash(content),
    )
    try:
        persisted, created = await repo.create_receipt_if_absent(receipt)
        if not created:
            if persisted.request_hash != request_hash:
                raise ProductIntelligenceConflictError(
                    "evidence_verification_receipt_replay_mismatch"
                )
            return persisted, True
        recorder.record(
            AuditEvent(
                actor_id=request.actor_id,
                tenant_id=scope.tenant_id,
                action="CREATE_EVIDENCE_VERIFICATION_RECEIPT",
                resource_type="EvidenceVerificationReceipt",
                resource_id=receipt.receipt_id,
                reason=f"accepted Human Gate decision {request.decision_id}",
                correlation_id=scope.correlation_id,
                after={
                    "outcome": receipt.outcome,
                    "evidence_id": receipt.evidence_id,
                    "evidence_version": receipt.evidence_version,
                    "valid_until": receipt.valid_until.isoformat(),
                    "task_id": receipt.task_id,
                    "decision_id": receipt.decision_id,
                },
            )
        )
        await repo.flush_audit(recorder)
        await repo.commit()
    except BaseException:
        await repo.rollback()
        raise
    return receipt, False


__all__ = [
    "EVIDENCE_VERIFICATION_PROCESSING_BASIS",
    "EVIDENCE_VERIFICATION_MAX_VALIDITY",
    "EVIDENCE_VERIFICATION_POLICY_VERSION",
    "EVIDENCE_VERIFICATION_PURPOSE",
    "VERIFY_PRODUCT_EVIDENCE_ACTION",
    "VERIFY_PRODUCT_EVIDENCE_PERMISSION",
    "EvidenceVerificationArguments",
    "EvidenceVerificationAuthorizer",
    "EvidenceVerificationReceiptRepository",
    "evidence_record_hash",
    "execute_evidence_verification_named_action",
]
