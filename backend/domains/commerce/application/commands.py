"""Named commerce commands for the no-op DEV/TEST intent flow."""

import re
from datetime import UTC, datetime

from ..domain.errors import CommerceConflictError, CommerceNotFoundError, CommerceValidationError
from ..domain.facts import Entitlement, OrderIntent, RefundRequest
from .ports import CommerceRepositoryPort


async def submit_order_intent(
    repo: CommerceRepositoryPort,
    *,
    tenant_id: str,
    family_id: str,
    actor_person_id: str,
    product_ref: str,
    product_version: int,
    page_id: str,
    idempotency_key: str | None,
    correlation_id: str,
    attributes: dict[str, object] | None = None,
) -> tuple[OrderIntent, Entitlement]:
    if page_id not in {"UI-14", "UI-17"}:
        raise CommerceValidationError("unsupported_commerce_source_page")
    if not idempotency_key:
        raise CommerceValidationError("idempotency-key header is required")
    existing = await repo.find_order_intent_by_idempotency(
        tenant_id=tenant_id, family_id=family_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        entitlement = next(
            (
                e
                for e in await repo.list_entitlements(
                    tenant_id=tenant_id, family_id=family_id
                )
                if e.source_order_intent_id == existing.order_intent_id
            ),
            None,
        )
        if entitlement is None:
            raise CommerceConflictError("commerce_intent_entitlement_incomplete")
        return existing, entitlement

    product = next(
        (
            item
            for item in await repo.list_products(tenant_id=tenant_id)
            if (
                item.product_ref == product_ref
                and item.version_no == product_version
                and item.is_bookable
            )
        ),
        None,
    )
    if product is None:
        raise CommerceNotFoundError("product_offering_not_found_or_not_admitted")

    now = datetime.now(UTC).replace(tzinfo=None)
    intent_id = f"commerce-intent-{family_id}-{product_ref.lower()}-v{product_version}"
    intent = OrderIntent(
        order_intent_id=intent_id,
        tenant_id=tenant_id,
        family_id=family_id,
        actor_person_id=actor_person_id,
        intent_ref=f"INTENT_{product_ref}_V{product_version}",
        product_id=product.product_id,
        product_ref=product.product_ref,
        product_version=product.version_no,
        source_page_id=page_id,  # type: ignore[arg-type]
        idempotency_key=idempotency_key,
        created_at=now,
        updated_at=now,
        attributes=attributes or {},
    )
    entitlement = Entitlement(
        entitlement_id=f"commerce-entitlement-{family_id}-{product_ref.lower()}-v{product_version}",
        tenant_id=tenant_id,
        family_id=family_id,
        source_order_intent_id=intent_id,
        entitlement_ref=f"ENTITLEMENT_{product_ref}_V{product_version}",
        created_at=now,
        updated_at=now,
    )
    await repo.save_order_intent(intent)
    await repo.save_entitlement(entitlement)
    await repo.commit()
    return intent, entitlement


async def request_refund(
    repo: CommerceRepositoryPort,
    *,
    tenant_id: str,
    family_id: str,
    source_order_intent_id: str,
    idempotency_key: str | None,
    reason: str,
    evidence_receipt_ref: str | None = None,
) -> tuple[RefundRequest, Entitlement]:
    """Process a local refund recovery transition idempotently.

    The adapter only revokes the local entitlement; payment settlement remains
    an explicit external integration and is never implied by this command.
    """
    if not idempotency_key:
        raise CommerceValidationError("idempotency-key header is required")
    if not reason.strip():
        raise CommerceValidationError("refund_reason_is_required")
    if evidence_receipt_ref is not None and not re.search(
        r"@v[1-9][0-9]*$", evidence_receipt_ref.strip()
    ):
        raise CommerceValidationError("refund_evidence_receipt_invalid")
    existing = await repo.find_refund_by_idempotency(
        tenant_id=tenant_id, family_id=family_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        entitlement = next(
            (item for item in await repo.list_entitlements(tenant_id=tenant_id, family_id=family_id)
             if item.entitlement_id == existing.entitlement_id), None
        )
        if entitlement is None:
            raise CommerceConflictError("refund_entitlement_missing")
        return existing, entitlement
    intent = next(
        (item for item in await repo.list_order_intents(tenant_id=tenant_id, family_id=family_id)
         if item.order_intent_id == source_order_intent_id), None
    )
    if intent is None:
        raise CommerceNotFoundError("order_intent_not_found")
    entitlement = next(
        (item for item in await repo.list_entitlements(tenant_id=tenant_id, family_id=family_id)
         if item.source_order_intent_id == source_order_intent_id), None
    )
    if entitlement is None:
        raise CommerceConflictError("refund_entitlement_missing")
    now = datetime.now(UTC).replace(tzinfo=None)
    refund = RefundRequest(
        refund_id=f"commerce-refund-{source_order_intent_id}",
        tenant_id=tenant_id, family_id=family_id,
        source_order_intent_id=source_order_intent_id,
        entitlement_id=entitlement.entitlement_id, status="PROCESSED",
        reason=reason.strip(), idempotency_key=idempotency_key,
        created_at=now, updated_at=now,
    )
    attributes = dict(entitlement.attributes)
    if evidence_receipt_ref:
        refs = list(attributes.get("evidence_refs", ()))
        if evidence_receipt_ref.strip() not in refs:
            refs.append(evidence_receipt_ref.strip())
        attributes["evidence_refs"] = refs
    revoked = entitlement.model_copy(
        update={"status": "REVOKED", "updated_at": now, "attributes": attributes}
    )
    await repo.save_refund(refund)
    await repo.save_entitlement(revoked)
    await repo.commit()
    return refund, revoked
