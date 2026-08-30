"""Human-gated adoption ACL for AI product-package drafts.

This module is deliberately a pure boundary adapter.  It validates an
``ProductPackageDraft`` and returns an immutable command that a product domain
may consume.  It does not persist, call a model, publish a product, or mutate
any business fact.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from backend.intelligence.model_gateway.contracts import AiProvenance
from backend.intelligence.product_management.ai_product_port import ProductPackageDraft


class ProductPackageAdoptionError(ValueError):
    """Raised when a draft cannot pass the human adoption ACL."""


def _freeze(value: Any) -> Any:
    """Recursively copy container values into immutable equivalents.

    Draft output is model-controlled data and may contain nested JSON-like
    containers.  A shallow ``MappingProxyType`` would leave lists and nested
    mappings mutable after the adoption command crossed the ACL boundary.
    """

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _required_text(value: str, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductPackageAdoptionError(code)
    return value.strip()


def _verified_refs(
    draft: ProductPackageDraft,
    evidence_statuses: Mapping[str, str],
) -> tuple[str, ...]:
    if not isinstance(evidence_statuses, Mapping):
        raise ProductPackageAdoptionError("EVIDENCE_STATUS_REQUIRED")
    refs = tuple(_required_text(ref, "EVIDENCE_REF_INVALID") for ref in draft.evidence_refs)
    if not refs:
        raise ProductPackageAdoptionError("EVIDENCE_REQUIRED")
    if len(set(refs)) != len(refs):
        raise ProductPackageAdoptionError("EVIDENCE_REFS_MUST_BE_UNIQUE")
    statuses = {
        _required_text(ref, "EVIDENCE_REF_INVALID"): _required_text(
            status, "EVIDENCE_STATUS_INVALID"
        )
        for ref, status in evidence_statuses.items()
    }
    missing = [ref for ref in refs if ref not in statuses]
    if missing:
        raise ProductPackageAdoptionError("EVIDENCE_STATUS_MISSING")
    extra = [ref for ref in statuses if ref not in refs]
    if extra:
        raise ProductPackageAdoptionError("EVIDENCE_STATUS_UNREFERENCED")
    unverified = [ref for ref in refs if statuses[ref].upper() != "VERIFIED"]
    if unverified:
        raise ProductPackageAdoptionError("EVIDENCE_NOT_VERIFIED")
    return refs


def _validate_human_actor(human_actor: str) -> str:
    actor = _required_text(human_actor, "HUMAN_ACTOR_REQUIRED")
    if actor.lower().startswith(("ai:", "agent:", "model:", "system:")):
        raise ProductPackageAdoptionError("HUMAN_ACTOR_REQUIRED")
    return actor


@dataclass(frozen=True, slots=True)
class ProductPackageAdoptionCommand:
    """Immutable command envelope for a human-approved draft adoption."""

    package_id: str
    product_id: str
    version: str
    output: Mapping[str, Any]
    evidence_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    next_validation: str
    owner: str
    expires_at: datetime
    model_attempt_ref: str
    ai_provenance: AiProvenance
    human_actor: str
    adoption_reason: str
    adopted_at: datetime
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        # Preserve the immutable command invariant even when a caller
        # constructs the dataclass directly instead of using the ACL function.
        object.__setattr__(self, "output", _freeze(self.output))

    @property
    def may_mutate_business_state(self) -> bool:
        """The command is a hand-off; the caller still owns the domain write."""

        return False

    @property
    def requires_human_confirmation(self) -> bool:
        """True records the gate that produced this command."""

        return True

    def to_domain_mapping(self) -> Mapping[str, Any]:
        """Return an immutable mapping suitable for a domain command adapter."""

        return MappingProxyType(
            {
                "package_id": self.package_id,
                "product_id": self.product_id,
                "version": self.version,
                "output": self.output,
                "evidence_refs": self.evidence_refs,
                "assumptions": self.assumptions,
                "next_validation": self.next_validation,
                "owner": self.owner,
                "expires_at": self.expires_at,
                "model_attempt_ref": self.model_attempt_ref,
                "provenance": self.ai_provenance,
                "human_actor": self.human_actor,
                "adoption_reason": self.adoption_reason,
                "adopted_at": self.adopted_at,
                "idempotency_key": self.idempotency_key,
            }
        )


def adopt_product_package_draft(
    draft: ProductPackageDraft,
    *,
    evidence_statuses: Mapping[str, str],
    human_actor: str,
    adoption_reason: str,
    idempotency_key: str | None = None,
    now: datetime | None = None,
) -> ProductPackageAdoptionCommand:
    """Validate a draft and produce a domain-consumable adoption command.

    ``now`` exists only for deterministic tests and replay; production callers
    should omit it.  No repository or provider is accepted by this function,
    making accidental persistence or model invocation impossible at the type
    boundary.
    """

    if not isinstance(draft, ProductPackageDraft):
        raise ProductPackageAdoptionError("PRODUCT_PACKAGE_DRAFT_REQUIRED")
    if draft.status != "DRAFT" or draft.may_mutate_business_state:
        raise ProductPackageAdoptionError("PRODUCT_PACKAGE_DRAFT_ONLY")
    if not isinstance(draft.provenance, AiProvenance):
        raise ProductPackageAdoptionError("AI_PROVENANCE_REQUIRED")
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ProductPackageAdoptionError("ADOPTION_TIME_MUST_BE_TIMEZONE_AWARE")
    current = current.astimezone(UTC)
    expiry = draft.expires_at
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ProductPackageAdoptionError("DRAFT_EXPIRY_MUST_BE_TIMEZONE_AWARE")
    if expiry.astimezone(UTC) <= current:
        raise ProductPackageAdoptionError("PRODUCT_PACKAGE_DRAFT_EXPIRED")
    evidence_refs = _verified_refs(draft, evidence_statuses)
    actor = _validate_human_actor(human_actor)
    reason = _required_text(adoption_reason, "ADOPTION_REASON_REQUIRED")
    key = (
        None
        if idempotency_key is None
        else _required_text(idempotency_key, "IDEMPOTENCY_KEY_INVALID")
    )
    return ProductPackageAdoptionCommand(
        package_id=_required_text(draft.package_id, "PACKAGE_ID_REQUIRED"),
        product_id=_required_text(draft.product_id, "PRODUCT_ID_REQUIRED"),
        version=_required_text(draft.version, "PACKAGE_VERSION_REQUIRED"),
        output=_freeze(draft.output),
        evidence_refs=evidence_refs,
        assumptions=tuple(draft.assumptions),
        next_validation=_required_text(draft.next_validation, "NEXT_VALIDATION_REQUIRED"),
        owner=_required_text(draft.owner, "OWNER_REQUIRED"),
        expires_at=expiry.astimezone(UTC),
        model_attempt_ref=_required_text(draft.model_attempt_ref, "MODEL_ATTEMPT_REF_REQUIRED"),
        ai_provenance=draft.provenance,
        human_actor=actor,
        adoption_reason=reason,
        adopted_at=current,
        idempotency_key=key,
    )


__all__ = [
    "ProductPackageAdoptionCommand",
    "ProductPackageAdoptionError",
    "adopt_product_package_draft",
]
