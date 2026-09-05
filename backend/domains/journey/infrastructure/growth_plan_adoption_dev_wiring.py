"""Dev/test-only composition for the growth-plan adoption vertical slice.

No production adapter exists yet for either
`GrowthPlanDraftReader` (a durable store of AI-generated, human-validated
growth-plan drafts) or `AdoptedGrowthPlanRepository` (durable, idempotent
adoption records). This module exists so the route is actually callable in
dev/test — matching the posture used elsewhere in this composition root
(e.g. `family_need`, `course_content`): the same route, errors and Named
Action gate as production, with a synthetic identity/storage seam that must
never be reachable outside dev/test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.platform.audit import AuditEvent, AuditRecorder

from ..api.growth_plan_adoption_routes import GrowthPlanAuthenticationError
from ..application.growth_plan_adoption import (
    AdoptedGrowthPlan,
    AdoptedGrowthPlanRepository,
    GrowthPlanActor,
    GrowthPlanAdoptionService,
    GrowthPlanDraftReader,
    GuardianGrowthPlanPolicy,
    ValidatedGrowthPlanDraft,
)
from ..domain.errors import JourneyConflictError


@dataclass
class InMemoryGrowthPlanDraftStore(GrowthPlanDraftReader):
    """Holds validated drafts keyed by (tenant, family); dev/test seeds it."""

    drafts: dict[tuple[str, str], ValidatedGrowthPlanDraft]

    def __init__(self) -> None:
        self.drafts = {}

    def put(self, draft: ValidatedGrowthPlanDraft) -> None:
        self.drafts[(draft.tenant_id, draft.family_id)] = draft

    async def load_validated_draft(
        self, *, tenant_id: str, family_id: str, draft_ref: str, version: int
    ) -> ValidatedGrowthPlanDraft | None:
        draft = self.drafts.get((tenant_id, family_id))
        if draft is None or draft.draft_ref != draft_ref or draft.version != version:
            return None
        return draft

    async def load_latest_validated_draft(
        self, *, tenant_id: str, family_id: str
    ) -> ValidatedGrowthPlanDraft | None:
        return self.drafts.get((tenant_id, family_id))


@dataclass
class InMemoryAdoptedGrowthPlanRepository(AdoptedGrowthPlanRepository):
    """Idempotent, family-scoped, process-local adoption store.

    R6 requires the AuditEvent produced by the same write path that changes
    authoritative state to actually be recorded, not merely constructed. This
    adapter has no database transaction to piggy-back on, so it keeps its own
    `AuditRecorder` buffer and appends to it inside `adopt_once` -- the single
    write path -- so "plan stored" and "audit event recorded" cannot diverge.
    A replayed (idempotent) call intentionally does NOT record a second event:
    no new state was written, so R6 has nothing new to attest to.
    """

    current: dict[tuple[str, str], AdoptedGrowthPlan]
    receipts: dict[str, tuple[str, AdoptedGrowthPlan]]
    audit_recorder: AuditRecorder

    def __init__(self, audit_recorder: AuditRecorder | None = None) -> None:
        self.current = {}
        self.receipts = {}
        self.audit_recorder = audit_recorder if audit_recorder is not None else AuditRecorder()

    async def get_current(self, *, tenant_id: str, family_id: str) -> AdoptedGrowthPlan | None:
        return self.current.get((tenant_id, family_id))

    async def adopt_once(
        self,
        *,
        plan: AdoptedGrowthPlan,
        idempotency_key: str,
        request_fingerprint: str,
        audit_event: AuditEvent,
    ) -> tuple[AdoptedGrowthPlan, bool, bool]:
        receipt = self.receipts.get(idempotency_key)
        if receipt is not None:
            stored_fingerprint, stored_plan = receipt
            if stored_fingerprint != request_fingerprint:
                raise JourneyConflictError("idempotency_conflict")
            return stored_plan, False, True
        key = (plan.tenant_id, plan.family_id)
        existing = self.current.get(key)
        if existing is not None and existing.draft_ref != plan.draft_ref:
            raise JourneyConflictError("active_growth_plan_already_exists")
        stored = existing or plan
        self.current[key] = stored
        self.receipts[idempotency_key] = (request_fingerprint, stored)
        if existing is None:
            self.audit_recorder.record(audit_event)
        return stored, existing is None, False


def build_dev_growth_plan_adoption_service(
    draft_store: InMemoryGrowthPlanDraftStore,
    repository: InMemoryAdoptedGrowthPlanRepository,
) -> GrowthPlanAdoptionService:
    return GrowthPlanAdoptionService(
        draft_reader=draft_store,
        repository=repository,
        policy=GuardianGrowthPlanPolicy(),
    )


def build_dev_actor_resolver(
    identity_lookup: Any,
) -> Any:
    """Build a `resolve_actor` callable from the shared dev bearer-token identity.

    `identity_lookup` is `dev_wiring._identity`: it turns a bearer token into
    `{account_id, family_id}` using the same synthetic session state every
    other dev-wired domain uses, so a token minted by `dev_auth` resolves to
    the same family here as it does for Assessment/Journey/FamilyNeed.
    """

    async def resolve_actor(authorization: str | None, family_id: str) -> GrowthPlanActor:
        try:
            identity = identity_lookup(authorization)
        except Exception as error:  # noqa: BLE001 - re-raised as the router's own auth error
            raise GrowthPlanAuthenticationError() from error
        account_id = identity["account_id"]
        resolved_family_id = identity["family_id"]
        return GrowthPlanActor(
            actor_id=account_id,
            tenant_id=resolved_family_id,
            family_id=resolved_family_id,
            membership_ref=f"dev-membership:{account_id}",
            consent_ref=f"dev-consent:{account_id}",
            actor_type="GUARDIAN",
        )

    return resolve_actor


__all__ = [
    "InMemoryAdoptedGrowthPlanRepository",
    "InMemoryGrowthPlanDraftStore",
    "build_dev_actor_resolver",
    "build_dev_growth_plan_adoption_service",
]
