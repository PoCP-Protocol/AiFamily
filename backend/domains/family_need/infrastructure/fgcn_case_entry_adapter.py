"""Bridge from a family's own self-help failure fact to FGCN case entry.

FGCN (`backend/domains/service/fgcn`) requires, before it will open a
`ServiceCase`, real evidence that the family already tried and failed at
self-help (`CaseEntryDependencySnapshot.self_help_actions` /
`self_help_observations`).  This module is the only place that translates one
already-recorded `FamilyConfirmedOutcome` (N6/N7:
`FamilyOutcomeDecision.DID_NOT_HELP`) into that evidence shape.

It invents nothing: every field on the two `ActionRecordRef` observations
below is either copied from the real `FamilyConfirmedOutcome` the caller
supplies, or a fixed literal the FGCN entry boundary itself requires
(`action_type="SELF_HELP"`, `outcome="FAILED"`, `kind="SELF_HELP_OUTCOME"`,
`value="FAILED"` — see `backend/domains/service/fgcn/entry.py`'s
`assert_case_entry_dependencies`, which pins those exact literals). The entry
boundary requires at least two self-help actions/observations; a course
completion follow-up review is treated as the family's own confirmation
review, so this adapter surfaces both the underlying course-completion signal
and the family's own `DID_NOT_HELP` verdict as the two required action facts.
"""

from __future__ import annotations

from backend.domains.family_need.domain.entities import FamilyConfirmedOutcome
from backend.domains.family_need.domain.value_objects import FamilyOutcomeDecision
from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.domains.service.fgcn.entry import (
    ActionRecordRef,
    CaseEntryDependencySnapshot,
    FamilyRequestRef,
    ObservationRef,
)

_FAMILY_REQUEST_STATUS = "ACTIVE"
_GROWTH_INTENT_STATUS = "CONFIRMED"
_CONSENT_STATUS = "ACTIVE"
_BINDING_STATUS = "ACTIVE"
_ACTION_TYPE = "SELF_HELP"
_ACTION_OUTCOME = "FAILED"
_OBSERVATION_KIND = "SELF_HELP_OUTCOME"
_OBSERVATION_VALUE = "FAILED"
_DEFAULT_FAMILY_NOTE = "家庭反馈：此前的自助方式未能真正解决问题"


def build_case_entry_snapshot_from_outcome(
    outcome: FamilyConfirmedOutcome,
    *,
    scope: GateServiceScope,
    intent_ref: str,
    locale: str = "zh",
) -> CaseEntryDependencySnapshot:
    """Translate one recorded self-help-failed outcome into FGCN entry evidence.

    Raises the same `ServiceValidationError`/`ServiceForbiddenError` the FGCN
    contracts already raise if the outcome does not actually carry a
    `DID_NOT_HELP` decision — this function must never be called to fabricate
    evidence for an outcome that does not say self-help failed.
    """

    if outcome.decision is not FamilyOutcomeDecision.DID_NOT_HELP:
        raise ValueError("fgcn_case_entry_requires_did_not_help_outcome")

    request = FamilyRequestRef(
        ref=f"family-request:{outcome.need_id}",
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        intent_ref=intent_ref,
        status=_FAMILY_REQUEST_STATUS,
        version=1,
        locale=locale,
    )
    # Fact 1: the delivered self-help fulfilment itself (the completed course
    # or booking) — `fulfillment_ref` is the real N5 delivery record this
    # family actually completed, per `FamilyConfirmedOutcome.fulfillment_ref`.
    delivery_action = ActionRecordRef(
        ref=f"action-record:self-help-delivery:{outcome.fulfillment_ref}",
        family_request_ref=request.ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        intent_ref=intent_ref,
        action_type=_ACTION_TYPE,
        outcome=_ACTION_OUTCOME,
        status="COMPLETED",
        version=request.version,
        locale=locale,
        observation_refs=(f"observation:self-help-delivery:{outcome.fulfillment_ref}",),
        occurred_at=outcome.confirmed_at,
    )
    # Fact 2: the family's own confirmed verdict on that delivery
    # (`outcome_id`) — the second, distinct self-help fact the entry boundary
    # requires (`len(actions) < 2` is rejected).
    verdict_action = ActionRecordRef(
        ref=f"action-record:self-help-verdict:{outcome.outcome_id}",
        family_request_ref=request.ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        intent_ref=intent_ref,
        action_type=_ACTION_TYPE,
        outcome=_ACTION_OUTCOME,
        status="COMPLETED",
        version=request.version,
        locale=locale,
        observation_refs=(f"observation:self-help-verdict:{outcome.outcome_id}",),
        occurred_at=outcome.confirmed_at,
    )
    delivery_observation = ObservationRef(
        ref=f"observation:self-help-delivery:{outcome.fulfillment_ref}",
        action_ref=delivery_action.ref,
        family_request_ref=request.ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        intent_ref=intent_ref,
        kind=_OBSERVATION_KIND,
        value=_OBSERVATION_VALUE,
        status="RECORDED",
        version=request.version,
        locale=locale,
        observed_at=outcome.confirmed_at,
    )
    verdict_observation = ObservationRef(
        ref=f"observation:self-help-verdict:{outcome.outcome_id}",
        action_ref=verdict_action.ref,
        family_request_ref=request.ref,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        intent_ref=intent_ref,
        kind=_OBSERVATION_KIND,
        value=_OBSERVATION_VALUE,
        status="RECORDED",
        version=request.version,
        locale=locale,
        observed_at=outcome.confirmed_at,
    )
    return CaseEntryDependencySnapshot(
        intent_ref=intent_ref,
        growth_intent_status=_GROWTH_INTENT_STATUS,
        consent_subject_person_id=scope.subject_person_id,
        consent_purpose=scope.purpose,
        consent_version=scope.consent_version,
        consent_status=_CONSENT_STATUS,
        binding_tenant_id=scope.tenant_id,
        binding_family_id=scope.family_id,
        binding_status=_BINDING_STATUS,
        family_request=request,
        self_help_actions=(delivery_action, verdict_action),
        self_help_observations=(delivery_observation, verdict_observation),
        locale=locale,
    )


class FamilyNeedCaseEntryDependencyStub:
    """Synchronous `CaseEntryDependencyQuery` backed by one real N6/N7 outcome.

    This is not a general-purpose FGCN entry adapter: it always answers with
    the single `FamilyConfirmedOutcome` (already established to be
    `DID_NOT_HELP`) it was constructed with, so a caller cannot use it to open
    a case for any need other than the one that outcome belongs to.
    """

    def __init__(
        self,
        outcome: FamilyConfirmedOutcome,
        *,
        locale: str = "zh",
    ) -> None:
        self._outcome = outcome
        self._locale = locale

    def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> CaseEntryDependencySnapshot | None:
        return build_case_entry_snapshot_from_outcome(
            self._outcome,
            scope=scope,
            intent_ref=intent_ref,
            locale=self._locale,
        )


class AsyncFamilyNeedCaseEntryDependencyStub:
    """Async `AsyncCaseEntryDependencyQuery` counterpart of the sync stub above.

    `build_case_entry_snapshot_from_outcome` is a pure function that touches
    no repository, so this adapter simply wraps it to satisfy the durable
    application command's async protocol — there is no separate I/O path to
    keep in sync with the synchronous stub.
    """

    def __init__(
        self,
        outcome: FamilyConfirmedOutcome,
        *,
        locale: str = "zh",
    ) -> None:
        self._outcome = outcome
        self._locale = locale

    async def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> CaseEntryDependencySnapshot | None:
        return build_case_entry_snapshot_from_outcome(
            self._outcome,
            scope=scope,
            intent_ref=intent_ref,
            locale=self._locale,
        )


__all__ = [
    "AsyncFamilyNeedCaseEntryDependencyStub",
    "FamilyNeedCaseEntryDependencyStub",
    "build_case_entry_snapshot_from_outcome",
]
