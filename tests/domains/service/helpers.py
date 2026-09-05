"""Shared constants, context builder and supply seeder for service tests.

Kept separate from `conftest.py` for the same reason membership does it:
`conftest.py` holds pytest fixtures, this module holds plain importable helpers,
and importing a conftest by module path works by accident rather than by
contract.
"""

from __future__ import annotations

from datetime import timedelta

from backend.domains.service.application import commands
from backend.domains.service.application.context import ActionContext
from backend.domains.service.domain.entities import (
    AvailabilitySlot,
    ServiceOffering,
    ServiceProvider,
    utcnow,
)
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.consent.models import (
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)

TENANT = "tenant-001"
FAMILY = "family-001"
OTHER_FAMILY = "family-999"
GUARDIAN = "person-guardian-001"
CHILD = "person-child-001"
CONSENT_REF = "consent-service-001"


def make_ctx(
    *,
    idempotency_key: str | None = None,
    actor: str = "guardian:001",
    family_id: str = FAMILY,
) -> ActionContext:
    """A human-actor context.

    `actor` defaults to a `guardian:` prefix, not `ai:` — `assert_human_actor`
    rejects `ai:`-prefixed actors, so a test proving that rejection must pass
    `actor` explicitly rather than relying on this default.
    """
    return ActionContext(
        tenant_id=TENANT,
        family_id=family_id,
        actor_person_id=GUARDIAN,
        actor=actor,
        correlation_id="corr-svc-001",
        environment="TEST",
        idempotency_key=idempotency_key,
    )


def granted(subject_person_id: str = CHILD, consent_id: str = CONSENT_REF) -> ConsentGrant:
    """An active SERVICE-purpose grant for one subject."""
    return ConsentGrant(
        consent_id=consent_id,
        subject_person_id=subject_person_id,
        guardian_person_id=GUARDIAN,
        purpose=ConsentPurpose.SERVICE,
        status=ConsentStatus.GRANTED,
        granted_at=utcnow(),
        # CHILD is a minor under 14, so PIPL art. 31 requires a distinct
        # guardian — `ConsentGrant` refuses any other combination.
        subject_age=SubjectAge(years=9),
        guardian_relation=GuardianRelation.GUARDIAN,
    )


async def seed_supply(
    repo, *, capacity: int = 1, recorder: AuditRecorder | None = None
) -> tuple[ServiceProvider, ServiceOffering, AvailabilitySlot]:
    """Provider → offering → one open slot, all through the real commands.

    Going through the commands rather than constructing rows directly means the
    seed itself exercises the supply-side admission checks; a seed that bypassed
    them could set up a state the commands would never produce.
    """
    recorder = recorder or AuditRecorder()
    ctx = make_ctx()
    provider = await commands.register_service_provider(
        repo,
        ctx,
        recorder,
        provider_ref="TEACHER_LI",
        display_name="李老师",
        provider_kind="TEACHER",
        qualification_status="ACTIVE",
        admission_status="ADMITTED",
        source_ref="supply:seed",
        qualification_ref="cert-001",
    )
    offering = await commands.publish_service_offering(
        repo,
        ctx,
        recorder,
        provider_id=provider.provider_id,
        service_offering_ref="PARENT_COACHING_60",
        title="家长一对一辅导 60 分钟",
        admission_status="ADMITTED",
        source_ref="supply:seed",
    )
    starts = utcnow() + timedelta(days=3)
    slot = await commands.open_availability_slot(
        repo,
        ctx,
        recorder,
        service_offering_id=offering.service_offering_id,
        availability_slot_ref="SLOT-2026-09-01-1000",
        starts_at=starts,
        ends_at=starts + timedelta(hours=1),
        channel="VIDEO",
        capacity=capacity,
    )
    return provider, offering, slot
