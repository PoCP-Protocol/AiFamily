"""Receipt-backed evidence admission for ProductPackage review submission."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, NoReturn, Protocol

from ..domain.entities import Evidence
from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceValidationError,
)
from ..domain.evidence_verification import EvidenceVerificationReceipt
from ..domain.product_package_draft import (
    EvidenceAdmissionSnapshot,
    ProductPackageEvidenceRequirement,
)
from .context import ActorContext
from .evidence_verification import (
    EVIDENCE_VERIFICATION_POLICY_VERSION,
    evidence_record_hash,
)
from .product_package_source_resolution import (
    ProductPackageDesignIntent,
    ProductPackageSourceResolutionError,
    ProductPackageSourceResolver,
    ResolvedProductPackageSource,
)

EVIDENCE_ADMISSION_POLICY_VERSION = "family-education-evidence-admission:v1"
_REQUIRED_METHODS = frozenset({"SOURCE_OPENED", "EVIDENCE_RECORD_HASH_MATCHED"})


class ProductPackageEvidenceReader(Protocol):
    async def load_receipt(
        self,
        receipt_id: str,
        tenant_scope: str,
    ) -> EvidenceVerificationReceipt: ...

    async def load_evidence(self, entity_id: str, tenant_scope: str) -> Evidence: ...


@dataclass(frozen=True, slots=True)
class ProductPackageReceiptPreflight:
    """Current-policy intrinsic receipt/source checks without an admission fact."""

    receipt: EvidenceVerificationReceipt
    evidence: Evidence
    receipt_lifecycle: Literal["ACTIVE", "EXPIRED", "NOT_YET_EFFECTIVE"]


def _reject(code: str) -> NoReturn:
    raise ProductPackageSourceResolutionError(code)


def product_package_receipt_lifecycle(
    receipt: EvidenceVerificationReceipt,
    now: datetime,
) -> Literal["ACTIVE", "EXPIRED", "NOT_YET_EFFECTIVE"]:
    if now.tzinfo is None or now.utcoffset() is None:
        _reject("PRODUCT_PACKAGE_EVIDENCE_ADMISSION_NOW_MUST_BE_AWARE")
    if receipt.verified_at > now or receipt.recorded_at > now:
        return "NOT_YET_EFFECTIVE"
    return receipt.lifecycle_at(now)


async def preflight_loaded_product_package_receipt(
    reader: ProductPackageEvidenceReader,
    *,
    receipt: EvidenceVerificationReceipt,
    tenant_scope: str,
    receipt_locator: str,
    now: datetime,
    requirement: ProductPackageEvidenceRequirement | None = None,
) -> ProductPackageReceiptPreflight:
    """Apply the same receipt policy used by admission, without creating a snapshot.

    ``requirement`` is server-owned application input. Generic health callers omit it,
    so claim/applicability coverage remains explicitly unevaluated.
    """

    if now.tzinfo is None or now.utcoffset() is None:
        _reject("PRODUCT_PACKAGE_EVIDENCE_ADMISSION_NOW_MUST_BE_AWARE")
    if receipt.receipt_id != receipt_locator:
        _reject("PRODUCT_PACKAGE_RECEIPT_LOCATOR_MISMATCH")
    if receipt.tenant_scope != tenant_scope:
        _reject("PRODUCT_PACKAGE_RECEIPT_TENANT_MISMATCH")
    lifecycle = product_package_receipt_lifecycle(receipt, now)
    if lifecycle == "NOT_YET_EFFECTIVE":
        _reject("PRODUCT_PACKAGE_RECEIPT_NOT_YET_EFFECTIVE")
    if lifecycle != "ACTIVE":
        _reject("PRODUCT_PACKAGE_RECEIPT_EXPIRED")
    if receipt.verification_policy_version != EVIDENCE_VERIFICATION_POLICY_VERSION:
        _reject("PRODUCT_PACKAGE_RECEIPT_POLICY_UNSUPPORTED")
    if receipt.supersedes_receipt_id is not None:
        _reject("PRODUCT_PACKAGE_RECEIPT_SUPERSESSION_UNSUPPORTED")
    if not _REQUIRED_METHODS.issubset(receipt.verification_methods):
        _reject("PRODUCT_PACKAGE_RECEIPT_METHODS_INSUFFICIENT")
    if requirement is not None:
        if not set(requirement.required_claim_refs).issubset(receipt.claim_scope):
            _reject("PRODUCT_PACKAGE_CLAIM_SCOPE_NOT_COVERED")
        if not set(requirement.required_applicability_refs).issubset(
            receipt.applicability_scope
        ):
            _reject("PRODUCT_PACKAGE_APPLICABILITY_SCOPE_NOT_COVERED")

    try:
        evidence = await reader.load_evidence(receipt.evidence_id, tenant_scope)
    except (ProductIntelligenceConflictError, ProductIntelligenceValidationError) as exc:
        raise ProductPackageSourceResolutionError(
            "PRODUCT_PACKAGE_EVIDENCE_SOURCE_INVALID"
        ) from exc
    if evidence.status != "ACTIVE":
        _reject("PRODUCT_PACKAGE_EVIDENCE_SOURCE_NOT_ACTIVE")
    if evidence.version != receipt.evidence_version:
        _reject("PRODUCT_PACKAGE_EVIDENCE_VERSION_DRIFT")
    if evidence.evidence_ref != receipt.evidence_ref:
        _reject("PRODUCT_PACKAGE_EVIDENCE_REF_DRIFT")
    if evidence_record_hash(evidence) != receipt.evidence_record_hash:
        _reject("PRODUCT_PACKAGE_EVIDENCE_RECORD_HASH_DRIFT")
    return ProductPackageReceiptPreflight(
        receipt=receipt,
        evidence=evidence,
        receipt_lifecycle=lifecycle,
    )


async def preflight_product_package_receipt(
    reader: ProductPackageEvidenceReader,
    *,
    tenant_scope: str,
    receipt_locator: str,
    now: datetime,
    requirement: ProductPackageEvidenceRequirement | None = None,
) -> ProductPackageReceiptPreflight:
    """Load once, validate persisted receipt integrity, then apply policy checks."""

    try:
        receipt = await reader.load_receipt(receipt_locator, tenant_scope)
    except (ProductIntelligenceConflictError, ProductIntelligenceValidationError) as exc:
        raise ProductPackageSourceResolutionError(
            "PRODUCT_PACKAGE_RECEIPT_INVALID"
        ) from exc
    return await preflight_loaded_product_package_receipt(
        reader,
        receipt=receipt,
        tenant_scope=tenant_scope,
        receipt_locator=receipt_locator,
        now=now,
        requirement=requirement,
    )


async def _admit_requirement(
    reader: ProductPackageEvidenceReader,
    *,
    tenant_scope: str,
    requirement: ProductPackageEvidenceRequirement,
    now: datetime,
    admitted_at: datetime | None = None,
) -> EvidenceAdmissionSnapshot:
    preflight = await preflight_product_package_receipt(
        reader,
        tenant_scope=tenant_scope,
        receipt_locator=requirement.receipt_locator,
        now=now,
        requirement=requirement,
    )
    receipt = preflight.receipt

    return EvidenceAdmissionSnapshot(
        claim_type=requirement.claim_type,
        required_claim_refs=requirement.required_claim_refs,
        required_applicability_refs=requirement.required_applicability_refs,
        receipt_id=receipt.receipt_id,
        receipt_hash=receipt.receipt_hash,
        evidence_id=receipt.evidence_id,
        evidence_version=receipt.evidence_version,
        evidence_record_hash=receipt.evidence_record_hash,
        evidence_ref=receipt.evidence_ref,
        claim_scope=receipt.claim_scope,
        applicability_scope=receipt.applicability_scope,
        criteria_refs=receipt.criteria_refs,
        verification_methods=receipt.verification_methods,
        verification_purpose=receipt.verification_purpose,
        verification_policy_version=receipt.verification_policy_version,
        receipt_outcome=receipt.outcome,
        integrity_check=receipt.integrity_check,
        relevance=receipt.relevance,
        task_id=receipt.task_id,
        proposal_id=receipt.proposal_id,
        decision_id=receipt.decision_id,
        verified_at=receipt.verified_at,
        valid_until=receipt.valid_until,
        admission_policy_version=EVIDENCE_ADMISSION_POLICY_VERSION,
        admitted_at=admitted_at or now,
    )


async def admit_product_package_evidence(
    reader: ProductPackageEvidenceReader,
    *,
    tenant_scope: str,
    requirements: tuple[ProductPackageEvidenceRequirement, ...],
    now: datetime,
) -> tuple[EvidenceAdmissionSnapshot, ...]:
    if now.tzinfo is None or now.utcoffset() is None:
        _reject("PRODUCT_PACKAGE_EVIDENCE_ADMISSION_NOW_MUST_BE_AWARE")
    locators = tuple(item.receipt_locator for item in requirements)
    if not locators or len(set(locators)) != len(locators):
        _reject("PRODUCT_PACKAGE_RECEIPT_LOCATORS_REQUIRED_AND_UNIQUE")
    admissions = tuple(
        [
            await _admit_requirement(
                reader,
                tenant_scope=tenant_scope,
                requirement=requirement,
                now=now,
            )
            for requirement in requirements
        ]
    )
    evidence_versions = tuple(
        (item.evidence_id, item.evidence_version, item.evidence_record_hash)
        for item in admissions
    )
    if len(set(evidence_versions)) != len(evidence_versions):
        _reject("PRODUCT_PACKAGE_DUPLICATE_UNDERLYING_EVIDENCE")
    return admissions


async def revalidate_product_package_evidence(
    reader: ProductPackageEvidenceReader,
    *,
    tenant_scope: str,
    admissions: tuple[EvidenceAdmissionSnapshot, ...],
    package_expires_at: datetime,
    now: datetime,
) -> None:
    requirements = tuple(
        ProductPackageEvidenceRequirement(
            receipt_locator=item.receipt_id,
            claim_type=item.claim_type,
            required_claim_refs=item.required_claim_refs,
            required_applicability_refs=item.required_applicability_refs,
        )
        for item in admissions
    )
    current = tuple(
        [
            await _admit_requirement(
                reader,
                tenant_scope=tenant_scope,
                requirement=requirement,
                now=now,
                admitted_at=admission.admitted_at,
            )
            for requirement, admission in zip(requirements, admissions, strict=True)
        ]
    )
    if current != admissions:
        _reject("PRODUCT_PACKAGE_EVIDENCE_ADMISSION_CHANGED")
    if any(item.valid_until < package_expires_at for item in current):
        _reject("PRODUCT_PACKAGE_EVIDENCE_EXPIRES_BEFORE_PACKAGE")


@dataclass(frozen=True, slots=True)
class ReceiptBackedProductPackageSourceResolver:
    inner: ProductPackageSourceResolver
    reader: ProductPackageEvidenceReader

    async def resolve(
        self,
        *,
        context: ActorContext,
        intent: ProductPackageDesignIntent,
        now: datetime,
    ) -> ResolvedProductPackageSource:
        resolved = await self.inner.resolve(context=context, intent=intent, now=now)
        source = resolved.submission
        if tuple(source.evidence_refs) != intent.evidence_locators:
            _reject("PRODUCT_PACKAGE_EVIDENCE_LOCATOR_MISMATCH")
        requirement_locators = tuple(
            item.receipt_locator for item in source.evidence_requirements
        )
        if requirement_locators != intent.evidence_locators:
            _reject("PRODUCT_PACKAGE_TRUSTED_EVIDENCE_REQUIREMENTS_MISMATCH")
        if source.evidence_admissions:
            _reject("PRODUCT_PACKAGE_SOURCE_SELF_REPORTED_EVIDENCE_ADMISSION")
        admissions = await admit_product_package_evidence(
            self.reader,
            tenant_scope=context.tenant_scope,
            requirements=source.evidence_requirements,
            now=now,
        )
        expires_at = min(
            source.expires_at,
            *(item.valid_until for item in admissions),
        )
        return ResolvedProductPackageSource(
            source_draft_locator=resolved.source_draft_locator,
            submission=replace(
                source,
                evidence_refs=tuple(item.receipt_id for item in admissions),
                evidence_admissions=admissions,
                expires_at=expires_at,
            ),
        )


__all__ = [
    "EVIDENCE_ADMISSION_POLICY_VERSION",
    "ProductPackageEvidenceReader",
    "ProductPackageReceiptPreflight",
    "ReceiptBackedProductPackageSourceResolver",
    "admit_product_package_evidence",
    "preflight_loaded_product_package_receipt",
    "preflight_product_package_receipt",
    "product_package_receipt_lifecycle",
    "revalidate_product_package_evidence",
]
