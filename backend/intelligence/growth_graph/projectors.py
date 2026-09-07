"""Growth Graph projectors fed directly from real domain write paths.

Each function here is called *in-process*, inside the same database
transaction as the domain write it observes.  No new event bus, queue, or
outbox is introduced: these projectors read the same ``AuditEvent``/outbox
payload the domain already produces at its one real write point and turn it
into an immutable, evidence-bound ``GrowthGraphEdge``.  If the projector call
raises, the caller's own transaction rolls back with it -- a Growth Graph
edge and its originating business fact are written atomically or not at all.

Only two projections exist today, matching the two vertical slices that are
actually wired into the running composition root:

* ``project_growth_hypothesis_confirmation`` -- called from
  ``backend.domains.growth.infrastructure.sqlalchemy_growth_intent_confirmation
  .SqlAlchemyGrowthIntentConfirmationAdapter.confirm_growth_intent`` right
  after its own ``AuditEvent``/outbox write, on the same ``AsyncSession``.
* ``project_daily_action_completion`` -- called from
  ``backend.domains.action.infrastructure.postgres.SqlAlchemyDailyActionApplication
  .check_in`` right after its own ``audit_logs``/``outbox_events`` insert, on
  the same ``AsyncConnection``.

Both accept the projection port directly (``GrowthGraphProjectionPort``) so
callers can pass ``SqlAlchemyGrowthGraphProjection`` bound to their own
session/connection, or a fake in tests, without this module knowing which.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)

from .store import GrowthGraphEdge

# No region concept exists yet anywhere in the Assessment/Growth/Action write
# paths this module observes (see ``growth_intent_handoff.py``,
# ``daily_action.py`` -- there is a per-request ``region_id`` on
# ``ActionEventScope`` already, but Assessment/Growth confirmation carries
# none). Growth Graph's ``ExperienceScope`` requires one; this is the single
# platform-wide default until a real per-family region is introduced.
DEFAULT_REGION_ID = "CN"

HYPOTHESIS_CONFIRMED_RELATION = "growth_hypothesis.confirmed"
DAILY_ACTION_COMPLETED_RELATION = "growth_action.completed"


class GrowthGraphProjectionPort(Protocol):
    async def project(self, edge: GrowthGraphEdge) -> GrowthGraphEdge: ...


def project_growth_hypothesis_confirmation(
    *,
    tenant_id: str,
    family_id: str,
    subject_person_id: str,
    actor_id: str,
    intent_id: str,
    signal_ref: str,
    receipt_ref: str,
    evidence_refs: tuple[str, ...],
    provenance_ref: str,
    correlation_id: str,
    causation_id: str,
    consent_version: str,
    occurred_at: datetime | None = None,
) -> GrowthGraphEdge:
    """Build the edge for a guardian-confirmed growth hypothesis.

    Called from ``SqlAlchemyGrowthIntentConfirmationAdapter.confirm_growth_intent``
    with the same ``binding``/``receipt`` values already validated and about
    to be written to ``AuditEvent`` and the canonical outbox -- this function
    only shapes those already-trusted values into a
    :class:`GrowthGraphEdge`; it re-validates nothing and re-authorizes
    nothing on its own.
    """

    observed_at = (occurred_at or datetime.now(UTC)).astimezone(UTC)
    scope = ExperienceScope(
        global_id=f"family://{tenant_id}/{family_id}",
        tenant_id=tenant_id,
        region_id=DEFAULT_REGION_ID,
        family_id=family_id,
        subject_ids=(subject_person_id,),
        purpose="growth_support",
        consent_version=consent_version,
        consent_granted=True,
        data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef(
            deletion_id=f"growth-intent:{intent_id}",
            retention_policy="growth_graph.default_v1",
        ),
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    provenance = ExperienceProvenance(
        provenance_ref=provenance_ref,
        source_refs=evidence_refs,
        kind=ProvenanceKind.HUMAN,
        policy_version="growth_hypothesis_confirmation.v1",
    )
    return GrowthGraphEdge(
        edge_id=f"graph:growth-intent-confirmed:{intent_id}",
        scope=scope,
        source_node=f"hypothesis:{signal_ref}",
        target_node=f"growth_intent:{intent_id}",
        relation=HYPOTHESIS_CONFIRMED_RELATION,
        event_ref=receipt_ref,
        evidence_refs=evidence_refs,
        provenance=provenance,
        observed_at=observed_at,
    )


def project_daily_action_completion(
    *,
    tenant_id: str,
    region_id: str,
    family_id: str,
    subject_person_id: str,
    actor_id: str,
    task_id: str,
    journey_plan_id: str,
    completion_status: str,
    purpose: str,
    consent_version: str,
    deletion_id: str,
    retention_policy: str,
    locale: str,
    correlation_id: str,
    causation_id: str,
    occurred_at: datetime,
) -> GrowthGraphEdge:
    """Build the edge for a guardian-recorded ``GrowthAction`` check-in.

    Called from ``SqlAlchemyDailyActionApplication.check_in`` with the same
    ``event_scope``/updated ``DailyActionProjection`` already written to
    ``audit_logs`` and ``outbox_events`` -- this function only shapes those
    already-trusted values; it does not re-run the completion-state
    transition or re-check the caller's family-manage permission.
    """

    observed_at = occurred_at.astimezone(UTC)
    scope = ExperienceScope(
        global_id=f"family://{tenant_id}/{family_id}",
        tenant_id=tenant_id,
        region_id=region_id,
        family_id=family_id,
        subject_ids=(subject_person_id,),
        purpose=purpose,
        consent_version=consent_version,
        consent_granted=True,
        data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
        locale=locale,
        content_locale=locale,
        model_locale=locale,
        policy_locale=locale,
        deletion_ref=DeletionRef(
            deletion_id=deletion_id,
            retention_policy=retention_policy,
        ),
        correlation_id=correlation_id,
        causation_id=causation_id,
    )
    provenance = ExperienceProvenance(
        provenance_ref=f"daily-action-checkin:{task_id}",
        source_refs=(f"growth_action:{task_id}",),
        kind=ProvenanceKind.HUMAN,
        policy_version="daily_action_checkin.v1",
    )
    return GrowthGraphEdge(
        edge_id=f"graph:growth-action-checkin:{task_id}:{completion_status}",
        scope=scope,
        source_node=f"journey_plan:{journey_plan_id}",
        target_node=f"growth_action:{task_id}",
        relation=DAILY_ACTION_COMPLETED_RELATION,
        event_ref=f"growth_action_checkin:{task_id}",
        evidence_refs=(f"growth_action:{task_id}",),
        provenance=provenance,
        observed_at=observed_at,
    )


__all__ = [
    "DAILY_ACTION_COMPLETED_RELATION",
    "DEFAULT_REGION_ID",
    "HYPOTHESIS_CONFIRMED_RELATION",
    "GrowthGraphProjectionPort",
    "project_daily_action_completion",
    "project_growth_hypothesis_confirmation",
]
