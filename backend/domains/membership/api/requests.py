"""Request models.

Note what is absent from every model here: `tenant_id`, `family_id`,
`actor_person_id`, `environment`, price, payment, contact. Those are
server-derived into `application/context.ActionContext` — the same rule the TS
`family-commerce-intent.contract.ts` already enforces, so a client cannot
inject another family's id or ask for `PRODUCTION`.
"""

from __future__ import annotations

from pydantic import BaseModel

from ...membership.domain.value_objects import TierCode


class SubscribeMembershipRequest(BaseModel):
    plan_id: str
    subscription_ref: str
    consent_ref: str
    subject_person_id: str | None = None


# `decided_by` is deliberately NOT a request field on the four commands below.
#
# It used to be one, and that was a real privilege hole: the domain policy
# `assert_human_actor` only inspects whether the string starts with `ai:`, so an
# AI-authenticated caller could send `decided_by="guardian:001"` in the body and
# the domain layer would accept it — the check was on the *claim*, not on the
# *caller*. Deleting the field is the structural fix: there is no longer any
# wire format in which a client can nominate a decider. The route derives it
# from the authenticated context instead (Constitution R9; and R8, which names
# 会员升级 as an action that must pass a Human Gate).


class ActivateMembershipTierRequest(BaseModel):
    to_tier: TierCode
    activation_source_type: str
    activation_source_ref: str
    period_days: int | None = None
    membership_subscription_id: str | None = None
    decision_note: str | None = None


class RenewMembershipPeriodRequest(BaseModel):
    activation_source_ref: str
    period_days: int = 365
    decision_note: str | None = None


class ExpireMembershipPeriodRequest(BaseModel):
    activation_source_ref: str


class GrantMembershipBenefitRequest(BaseModel):
    membership_subscription_id: str
    benefit_definition_id: str
    grant_ref: str
    source_page_id: str
    subject_person_id: str | None = None
    units: int | None = None


class ReserveMembershipBenefitRequest(BaseModel):
    benefit_grant_id: str
    reservation_ref: str
    units: int


class ConsumeMembershipBenefitRequest(BaseModel):
    benefit_grant_id: str
    units: int
    source_page_id: str
    benefit_reservation_id: str | None = None
    subject_person_id: str | None = None


class RevokeMembershipBenefitRequest(BaseModel):
    benefit_grant_id: str
    source_page_id: str
