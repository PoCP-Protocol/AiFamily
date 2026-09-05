"""Read-only health projection for one immutable evidence receipt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceNotFoundError,
    ProductIntelligenceValidationError,
)
from ..domain.evidence_verification import EvidenceVerificationReceipt
from .context import ActorContext
from .product_package_evidence_admission import (
    EVIDENCE_ADMISSION_POLICY_VERSION,
    ProductPackageEvidenceReader,
    preflight_loaded_product_package_receipt,
    product_package_receipt_lifecycle,
)
from .product_package_source_resolution import ProductPackageSourceResolutionError
from .product_package_submission import (
    ProductPackageSubmissionError,
    authorize_product_package_read,
)

ReceiptTraceabilityHealth = Literal["UNHEALTHY", "UNKNOWN"]
CurrentPolicyPrecheck = Literal["PASS", "FAIL"]
ReceiptLifecycleObservation = Literal["ACTIVE", "EXPIRED", "NOT_YET_EFFECTIVE"]
ReceiptHealthReason = Literal[
    "SUPERSESSION_STATE_UNKNOWN_NOT_IN_CONTRACT",
    "CLAIM_APPLICABILITY_NOT_EVALUATED",
    "AUTHORITATIVE_ADMISSION_NOT_PERFORMED",
    "PRODUCT_PACKAGE_RECEIPT_NOT_YET_EFFECTIVE",
    "PRODUCT_PACKAGE_RECEIPT_EXPIRED",
    "PRODUCT_PACKAGE_RECEIPT_POLICY_UNSUPPORTED",
    "PRODUCT_PACKAGE_RECEIPT_SUPERSESSION_UNSUPPORTED",
    "PRODUCT_PACKAGE_RECEIPT_METHODS_INSUFFICIENT",
    "PRODUCT_PACKAGE_EVIDENCE_SOURCE_NOT_ACTIVE",
    "PRODUCT_PACKAGE_EVIDENCE_SOURCE_NOT_FOUND",
    "PRODUCT_PACKAGE_EVIDENCE_VERSION_DRIFT",
    "PRODUCT_PACKAGE_EVIDENCE_REF_DRIFT",
    "PRODUCT_PACKAGE_EVIDENCE_RECORD_HASH_DRIFT",
]


class EvidenceReceiptHealthConflictError(ProductPackageSubmissionError):
    """Persisted receipt/source shape is not safe to expose as a snapshot."""


class EvidenceReceiptHealthUnavailableError(ProductPackageSubmissionError):
    """Trusted health dependencies or the server clock are unavailable."""


@dataclass(frozen=True, slots=True)
class EvidenceReceiptHealthProjection:
    schema_version: Literal["1.0"]
    receipt_id: str
    receipt_hash: str
    evidence_id: str
    evidence_version: int
    evaluated_at: datetime
    valid_until: datetime
    receipt_lifecycle: ReceiptLifecycleObservation
    precheck_policy_version: str
    diagnostic_scope: Literal["RECEIPT_SOURCE_INTEGRITY"]
    current_policy_precheck: CurrentPolicyPrecheck
    receipt_traceability_health: ReceiptTraceabilityHealth
    supersession_state: Literal["UNKNOWN_NOT_IN_CONTRACT"]
    reason_codes: tuple[ReceiptHealthReason, ...]
    claim_applicability_evaluated: Literal[False]
    authoritative_admission: Literal[False]
    final_revalidation_required: Literal[True]
    admission_state: Literal["NOT_EVALUATED"]
    human_gate_state: Literal["NOT_EVALUATED"]


def _receipt_id(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ProductPackageSubmissionError("EVIDENCE_RECEIPT_ID_REQUIRED")
    if len(normalized) > 160:
        raise ProductPackageSubmissionError("EVIDENCE_RECEIPT_ID_TOO_LONG")
    return normalized


def _projection(
    receipt: EvidenceVerificationReceipt,
    *,
    now: datetime,
    current_policy_precheck: CurrentPolicyPrecheck,
    receipt_traceability_health: ReceiptTraceabilityHealth,
    reason_codes: tuple[ReceiptHealthReason, ...],
) -> EvidenceReceiptHealthProjection:
    return EvidenceReceiptHealthProjection(
        schema_version="1.0",
        receipt_id=receipt.receipt_id,
        receipt_hash=receipt.receipt_hash,
        evidence_id=receipt.evidence_id,
        evidence_version=receipt.evidence_version,
        evaluated_at=now,
        valid_until=receipt.valid_until,
        receipt_lifecycle=product_package_receipt_lifecycle(receipt, now),
        precheck_policy_version=EVIDENCE_ADMISSION_POLICY_VERSION,
        diagnostic_scope="RECEIPT_SOURCE_INTEGRITY",
        current_policy_precheck=current_policy_precheck,
        receipt_traceability_health=receipt_traceability_health,
        supersession_state="UNKNOWN_NOT_IN_CONTRACT",
        reason_codes=reason_codes,
        claim_applicability_evaluated=False,
        authoritative_admission=False,
        final_revalidation_required=True,
        admission_state="NOT_EVALUATED",
        human_gate_state="NOT_EVALUATED",
    )


async def get_evidence_receipt_health(
    reader: ProductPackageEvidenceReader,
    context: ActorContext,
    *,
    receipt_id: str,
    now: datetime,
) -> EvidenceReceiptHealthProjection:
    """Observe current policy compatibility without creating an admission fact."""

    authorize_product_package_read(context)
    locator = _receipt_id(receipt_id)
    if now.tzinfo is None or now.utcoffset() is None:
        raise EvidenceReceiptHealthUnavailableError(
            "EVIDENCE_RECEIPT_HEALTH_CLOCK_INVALID"
        )
    try:
        receipt = await reader.load_receipt(locator, context.tenant_scope)
    except ProductIntelligenceNotFoundError:
        raise
    except (ProductIntelligenceConflictError, ProductIntelligenceValidationError) as exc:
        raise EvidenceReceiptHealthConflictError(
            "EVIDENCE_RECEIPT_PERSISTED_STATE_INVALID"
        ) from exc
    except Exception as exc:
        raise EvidenceReceiptHealthUnavailableError(
            "EVIDENCE_RECEIPT_HEALTH_REPOSITORY_UNAVAILABLE"
        ) from exc

    try:
        await preflight_loaded_product_package_receipt(
            reader,
            receipt=receipt,
            tenant_scope=context.tenant_scope,
            receipt_locator=locator,
            now=now,
        )
    except ProductIntelligenceNotFoundError:
        return _projection(
            receipt,
            now=now,
            current_policy_precheck="FAIL",
            receipt_traceability_health="UNHEALTHY",
            reason_codes=("PRODUCT_PACKAGE_EVIDENCE_SOURCE_NOT_FOUND",),
        )
    except ProductPackageSourceResolutionError as exc:
        if exc.code in {
            "PRODUCT_PACKAGE_RECEIPT_INVALID",
            "PRODUCT_PACKAGE_RECEIPT_LOCATOR_MISMATCH",
            "PRODUCT_PACKAGE_RECEIPT_TENANT_MISMATCH",
            "PRODUCT_PACKAGE_EVIDENCE_SOURCE_INVALID",
        }:
            raise EvidenceReceiptHealthConflictError(exc.code) from exc
        return _projection(
            receipt,
            now=now,
            current_policy_precheck="FAIL",
            receipt_traceability_health="UNHEALTHY",
            reason_codes=(exc.code,),
        )
    except Exception as exc:
        raise EvidenceReceiptHealthUnavailableError(
            "EVIDENCE_RECEIPT_HEALTH_SOURCE_UNAVAILABLE"
        ) from exc

    return _projection(
        receipt,
        now=now,
        current_policy_precheck="PASS",
        receipt_traceability_health="UNKNOWN",
        reason_codes=(
            "SUPERSESSION_STATE_UNKNOWN_NOT_IN_CONTRACT",
            "CLAIM_APPLICABILITY_NOT_EVALUATED",
            "AUTHORITATIVE_ADMISSION_NOT_PERFORMED",
        ),
    )


__all__ = [
    "CurrentPolicyPrecheck",
    "EvidenceReceiptHealthConflictError",
    "EvidenceReceiptHealthProjection",
    "EvidenceReceiptHealthUnavailableError",
    "ReceiptHealthReason",
    "ReceiptTraceabilityHealth",
    "ReceiptLifecycleObservation",
    "get_evidence_receipt_health",
]
