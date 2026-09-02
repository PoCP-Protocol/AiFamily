"""Strict browser-safe response contract for receipt health observation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..application.evidence_receipt_health import ReceiptHealthReason


class EvidenceReceiptHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    schema_version: Literal["1.0"]
    receipt_id: str
    receipt_hash: str
    evidence_id: str
    evidence_version: int
    evaluated_at: datetime
    valid_until: datetime
    receipt_lifecycle: Literal["ACTIVE", "EXPIRED", "NOT_YET_EFFECTIVE"]
    precheck_policy_version: str
    diagnostic_scope: Literal["RECEIPT_SOURCE_INTEGRITY"]
    current_policy_precheck: Literal["PASS", "FAIL"]
    receipt_traceability_health: Literal["UNHEALTHY", "UNKNOWN"]
    supersession_state: Literal["UNKNOWN_NOT_IN_CONTRACT"]
    reason_codes: tuple[ReceiptHealthReason, ...] = Field(min_length=1)
    claim_applicability_evaluated: Literal[False]
    authoritative_admission: Literal[False]
    final_revalidation_required: Literal[True]
    admission_state: Literal["NOT_EVALUATED"]
    human_gate_state: Literal["NOT_EVALUATED"]

    @model_validator(mode="after")
    def state_and_reasons_are_coherent(self) -> EvidenceReceiptHealthResponse:
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("reason_codes must be unique")
        if self.current_policy_precheck == "PASS":
            expected = (
                "SUPERSESSION_STATE_UNKNOWN_NOT_IN_CONTRACT",
                "CLAIM_APPLICABILITY_NOT_EVALUATED",
                "AUTHORITATIVE_ADMISSION_NOT_PERFORMED",
            )
            if self.receipt_traceability_health != "UNKNOWN" or self.reason_codes != expected:
                raise ValueError("PASS must retain the complete unknown boundary")
            if self.receipt_lifecycle != "ACTIVE":
                raise ValueError("PASS receipt lifecycle must be ACTIVE")
        else:
            boundary_reasons = {
                "SUPERSESSION_STATE_UNKNOWN_NOT_IN_CONTRACT",
                "CLAIM_APPLICABILITY_NOT_EVALUATED",
                "AUTHORITATIVE_ADMISSION_NOT_PERFORMED",
            }
            if self.receipt_traceability_health != "UNHEALTHY":
                raise ValueError("FAIL must be UNHEALTHY")
            if len(self.reason_codes) != 1 or boundary_reasons.intersection(
                self.reason_codes
            ):
                raise ValueError("FAIL must contain exactly one precheck failure reason")
            reason = self.reason_codes[0]
            if (self.receipt_lifecycle == "EXPIRED") != (
                reason == "PRODUCT_PACKAGE_RECEIPT_EXPIRED"
            ):
                raise ValueError("EXPIRED lifecycle and reason must agree")
            if (self.receipt_lifecycle == "NOT_YET_EFFECTIVE") != (
                reason == "PRODUCT_PACKAGE_RECEIPT_NOT_YET_EFFECTIVE"
            ):
                raise ValueError("NOT_YET_EFFECTIVE lifecycle and reason must agree")
        return self


__all__ = ["EvidenceReceiptHealthResponse"]
