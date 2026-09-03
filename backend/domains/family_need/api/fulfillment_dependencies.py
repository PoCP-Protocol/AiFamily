"""Dependency seam for the confirm-draft -> fulfilment HTTP route.

Same fail-closed shape as `dependencies.py`: the default implementation raises
503 so an unconfigured process cannot silently fabricate commerce/service
side effects. Only `backend/apps/family_api/dev_wiring.py` (dev/test) or a
future production composition root may override `get_fulfillment_deps`.

This module intentionally imports commerce/service/journey *application*
types only for typing the dataclass fields — it is still part of the
`family_need` API package, but the fields exist only to be handed, unopened,
to `backend/apps/family_api/orchestration/need_fulfillment_flow.py`, which is
the actual cross-domain composition root. `family_need`'s own domain/service
layer still never imports commerce or service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException

from backend.domains.commerce.application.ports import CommerceRepositoryPort
from backend.domains.family_need.application.ports import FamilyNeedRepositoryPort
from backend.domains.journey.application.outcome_loop import GrowthOutcomeLoop
from backend.domains.product_intelligence.application.course_publication import (
    CourseContentRepository,
)
from backend.domains.service.application.ports import ConsentQueryPort, ServiceRepositoryPort
from backend.domains.service.fgcn.admission import ProviderAdmissionQuery
from backend.platform.audit.recorder import AuditRecorder


class DraftFulfiller(Protocol):
    async def __call__(
        self,
        draft,
        *,
        commerce_service: CommerceRepositoryPort,
        service_booking_service: ServiceRepositoryPort,
        consent_query: ConsentQueryPort,
        audit_recorder: AuditRecorder,
        actor: str,
        actor_person_id: str,
        subject_person_id: str,
        correlation_id: str,
        idempotency_key: str,
        environment: str,
        family_need_repository: FamilyNeedRepositoryPort | None = None,
        fgcn_provider_admission: ProviderAdmissionQuery | None = None,
    ): ...


@dataclass(frozen=True)
class FulfillmentDeps:
    """Everything the confirm/complete-and-review routes need across domains."""

    commerce_repository: CommerceRepositoryPort
    service_repository: ServiceRepositoryPort
    consent_query: ConsentQueryPort
    audit_recorder: AuditRecorder
    outcome_loop: GrowthOutcomeLoop
    fulfil_confirmed_draft: DraftFulfiller
    # Read/load seam for the "mark course completed" route
    # (`complete_course_and_review`). Only `load_course_content` is used
    # today; the field carries the same `CourseContentRepository` protocol
    # `course_publication.py` already depends on, so this module still never
    # imports a concrete product_intelligence repository type.
    course_content_repository: CourseContentRepository
    # `CourseContent.tenant_scope` names the *publishing* tenant (the catalog
    # owner), not the family's own tenant — the same simplification
    # `CourseSupplyAdapter.resolve_component` already makes by dropping
    # `tenant_id` entirely (courses are a shared, cross-tenant catalog today,
    # same as commerce's product catalog). The composition root that wires
    # `FulfillmentDeps` is the only place that knows which tenant scope the
    # course catalog was actually published under, so it is carried here
    # rather than guessed from the acting family's `tenant_id`.
    course_catalog_tenant_scope: str
    # FGCN authorization gate wiring. `family_need_repository` lets the
    # fulfilment flow look up a real N6/N7 `DID_NOT_HELP` outcome for the need
    # being fulfilled; `fgcn_provider_admission` is the provider-admission
    # query FGCN's engine uses to verify the matched teacher is really
    # admitted before creating a `TaskAssignment`. Both are optional so a
    # caller that never wires them (e.g. an older test) keeps the pre-FGCN
    # direct-booking behaviour exactly as before.
    family_need_repository: FamilyNeedRepositoryPort | None = None
    fgcn_provider_admission: ProviderAdmissionQuery | None = None


def get_fulfillment_deps() -> FulfillmentDeps:
    """Require process wiring; never invent commerce/service/journey access."""

    raise HTTPException(status_code=503, detail="need_fulfillment_deps_not_wired")


__all__ = ["DraftFulfiller", "FulfillmentDeps", "get_fulfillment_deps"]
