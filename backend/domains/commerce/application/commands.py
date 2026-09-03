"""Named commerce commands for the no-op DEV/TEST intent flow."""

from datetime import UTC, datetime

from ..domain.errors import CommerceConflictError, CommerceNotFoundError, CommerceValidationError
from ..domain.facts import Entitlement, OrderIntent
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
