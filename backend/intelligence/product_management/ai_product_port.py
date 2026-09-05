"""Provider-neutral bridge from a model draft to an IPD product package draft.

The product factory consumes AI output as a proposal only.  This module owns no
product or family repository and deliberately does not import a business domain;
an approved package must be written by the product-management application after
its own human gate and named action.  Keeping the bridge as a small value-object
adapter makes the Model Gateway boundary explicit while the IPD contracts evolve
independently.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft

ProductPackageStatus = Literal["DRAFT"]


class ProductPackageDraftError(ValueError):
    """Raised when an AI product package draft is not auditable or bounded."""


@dataclass(frozen=True, slots=True)
class ProductPackageDraft:
    """An evidence-bound product package proposal, never a canonical product.

    ``model_attempt_ref`` is kept separate from ``AiProvenance`` because an
    attempt is an operational ledger reference while provenance describes the
    model invocation itself.  Both are required to make a package reviewable.
    ``status`` has one legal value and the two policy properties intentionally
    cannot be overridden by callers.
    """

    package_id: str
    product_id: str
    version: str
    output: dict[str, Any]
    evidence_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    next_validation: str
    owner: str
    expires_at: datetime
    model_attempt_ref: str
    provenance: AiProvenance
    status: ProductPackageStatus = "DRAFT"

    def __post_init__(self) -> None:
        if not all(
            (
                self.package_id,
                self.product_id,
                self.version,
                self.next_validation,
                self.owner,
                self.model_attempt_ref,
            )
        ):
            raise ProductPackageDraftError("PRODUCT_PACKAGE_DRAFT_FIELDS_REQUIRED")
        if not isinstance(self.provenance, AiProvenance):
            raise ProductPackageDraftError("PRODUCT_PACKAGE_PROVENANCE_REQUIRED")
        if self.status != "DRAFT":
            raise ProductPackageDraftError("PRODUCT_PACKAGE_DRAFT_ONLY")
        if not self.evidence_refs or any(not ref for ref in self.evidence_refs):
            raise ProductPackageDraftError("PRODUCT_PACKAGE_EVIDENCE_REQUIRED")
        if not self.assumptions or any(not item for item in self.assumptions):
            raise ProductPackageDraftError("PRODUCT_PACKAGE_ASSUMPTIONS_REQUIRED")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ProductPackageDraftError("PRODUCT_PACKAGE_EXPIRY_MUST_BE_TIMEZONE_AWARE")
        if self.expires_at <= self.provenance.generated_at:
            raise ProductPackageDraftError("PRODUCT_PACKAGE_EXPIRY_MUST_FOLLOW_PROVENANCE")

    @property
    def requires_human_confirmation(self) -> bool:
        """Product package adoption is a human decision, not an AI transition."""

        return True

    @property
    def may_mutate_business_state(self) -> bool:
        """The adapter can only return a draft and cannot write a product fact."""

        return False


class ModelDraftProductPackageAdapter:
    """Convert a validated :class:`ModelDraft` into an IPD draft envelope.

    The adapter performs no persistence and has no method that accepts a
    repository.  Product creation, charter advancement, and release remain
    outside AI Runtime behind the product-management application's named action.
    """

    def adapt(
        self,
        draft: ModelDraft,
        *,
        package_id: str,
        product_id: str,
        version: str,
        model_attempt_ref: str,
        evidence_refs: Iterable[str],
        assumptions: Iterable[str],
        next_validation: str,
        owner: str,
        expires_at: datetime,
    ) -> ProductPackageDraft:
        if not isinstance(draft, ModelDraft):
            raise ProductPackageDraftError("MODEL_DRAFT_REQUIRED")
        if draft.status != "DRAFT" or draft.may_mutate_business_state:
            raise ProductPackageDraftError("MODEL_DRAFT_MUST_REMAIN_DRAFT_ONLY")
        evidence = _normalise_refs(evidence_refs, "PRODUCT_PACKAGE_EVIDENCE_REQUIRED")
        assumptions_tuple = _normalise_refs(assumptions, "PRODUCT_PACKAGE_ASSUMPTIONS_REQUIRED")
        return ProductPackageDraft(
            package_id=package_id,
            product_id=product_id,
            version=version,
            output=dict(draft.output),
            evidence_refs=evidence,
            assumptions=assumptions_tuple,
            next_validation=next_validation,
            owner=owner,
            expires_at=expires_at,
            model_attempt_ref=model_attempt_ref,
            provenance=draft.provenance,
        )


def _normalise_refs(values: Iterable[str], error_code: str) -> tuple[str, ...]:
    try:
        refs = tuple(values)
    except TypeError as exc:
        raise ProductPackageDraftError(error_code) from exc
    if not refs or any(not isinstance(value, str) or not value.strip() for value in refs):
        raise ProductPackageDraftError(error_code)
    return tuple(value.strip() for value in refs)


__all__ = [
    "ModelDraftProductPackageAdapter",
    "ProductPackageDraft",
    "ProductPackageDraftError",
    "ProductPackageStatus",
]
