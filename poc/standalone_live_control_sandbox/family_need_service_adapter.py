"""Synthetic adapter for the Live -> FamilyNeed -> Service feedback boundary.

This is deliberately not a second FamilyNeed, Consent, Audit, or ServiceRecord
implementation.  It proves the standalone Live product can consume an already
confirmed need and pass a guardian's explicit choice to platform-owned ports.
All durable facts and mutations remain behind those ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"
LIVE_SERVICE_PURPOSE = "live_service_follow_up"


class LiveNeedBridgeRejected(RuntimeError):
    """The bridge refuses an untrusted, stale, or out-of-scope operation."""


@dataclass(frozen=True, slots=True)
class AdultContext:
    tenant_id: str
    family_id: str
    guardian_id: str
    actor_type: str = "FAMILY_GUARDIAN"


@dataclass(frozen=True, slots=True)
class ConfirmedNeedProjection:
    """Read-only, minimized projection supplied by the canonical FamilyNeed owner."""

    need_id: str
    tenant_id: str
    family_id: str
    status: str
    growth_theme: str
    consent_version: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AdultServiceChoice:
    session_ref: str
    need_id: str
    offering_ref: str
    choice_ref: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if self.source != SANDBOX_SOURCE or not self.fixture_only:
            raise LiveNeedBridgeRejected("only explicit synthetic fixtures are allowed")
        if not all((self.session_ref, self.need_id, self.offering_ref, self.choice_ref)):
            raise LiveNeedBridgeRejected("choice references are required")


@dataclass(frozen=True, slots=True)
class ServiceRecordReceipt:
    service_record_ref: str
    need_id: str
    tenant_id: str
    family_id: str
    status: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


class FamilyNeedReadPort(Protocol):
    def get_confirmed_need(
        self, *, need_id: str, tenant_id: str, family_id: str, now: datetime
    ) -> ConfirmedNeedProjection | None: ...


class CanonicalConsentReadPort(Protocol):
    def require_grant(
        self, *, tenant_id: str, family_id: str, guardian_id: str, purpose: str, now: datetime
    ) -> str: ...


class ServiceRecordPort(Protocol):
    def create_from_live_choice(
        self, *, choice: AdultServiceChoice, guardian: AdultContext, consent_ref: str
    ) -> ServiceRecordReceipt: ...

    def append_live_feedback(
        self, *, service_record_ref: str, need_id: str, guardian: AdultContext, feedback_ref: str
    ) -> str: ...


class LiveNeedServiceAdapter:
    """Small orchestration seam; platform ports retain all business facts."""

    def __init__(
        self,
        *,
        family_needs: FamilyNeedReadPort,
        consent: CanonicalConsentReadPort,
        service_records: ServiceRecordPort,
    ) -> None:
        self._family_needs = family_needs
        self._consent = consent
        self._service_records = service_records

    def choose_service(
        self, *, choice: AdultServiceChoice, guardian: AdultContext, now: datetime
    ) -> ServiceRecordReceipt:
        self._require_adult(guardian)
        need = self._confirmed_need(choice, guardian, now)
        if need.consent_version == "":
            raise LiveNeedBridgeRejected("need lacks a current consent version")
        consent_ref = self._consent.require_grant(
            tenant_id=guardian.tenant_id,
            family_id=guardian.family_id,
            guardian_id=guardian.guardian_id,
            purpose=LIVE_SERVICE_PURPOSE,
            now=now,
        )
        if not consent_ref:
            raise LiveNeedBridgeRejected("canonical consent is required")
        receipt = self._service_records.create_from_live_choice(
            choice=choice, guardian=guardian, consent_ref=consent_ref
        )
        if (
            receipt.source != SANDBOX_SOURCE
            or not receipt.fixture_only
            or receipt.need_id != need.need_id
            or receipt.tenant_id != guardian.tenant_id
            or receipt.family_id != guardian.family_id
        ):
            raise LiveNeedBridgeRejected("service record receipt is not in the verified scope")
        return receipt

    def record_feedback(
        self,
        *,
        service_record: ServiceRecordReceipt,
        guardian: AdultContext,
        feedback_ref: str,
        now: datetime,
    ) -> str:
        self._require_adult(guardian)
        if not feedback_ref or service_record.status != "COMPLETED":
            raise LiveNeedBridgeRejected("completed service and feedback reference are required")
        if service_record.source != SANDBOX_SOURCE or not service_record.fixture_only:
            raise LiveNeedBridgeRejected("service feedback receipt is outside the sandbox boundary")
        self._confirmed_need_id(service_record.need_id, guardian, now)
        if (
            service_record.tenant_id != guardian.tenant_id
            or service_record.family_id != guardian.family_id
        ):
            raise LiveNeedBridgeRejected("service record crosses the authenticated family scope")
        return self._service_records.append_live_feedback(
            service_record_ref=service_record.service_record_ref,
            need_id=service_record.need_id,
            guardian=guardian,
            feedback_ref=feedback_ref,
        )

    def _confirmed_need(
        self, choice: AdultServiceChoice, guardian: AdultContext, now: datetime
    ) -> ConfirmedNeedProjection:
        return self._confirmed_need_id(choice.need_id, guardian, now)

    def _confirmed_need_id(
        self, need_id: str, guardian: AdultContext, now: datetime
    ) -> ConfirmedNeedProjection:
        need = self._family_needs.get_confirmed_need(
            need_id=need_id, tenant_id=guardian.tenant_id, family_id=guardian.family_id, now=now
        )
        if need is None or need.status not in {"CONFIRMED", "PROFILED", "SOLUTIONING"}:
            raise LiveNeedBridgeRejected("confirmed FamilyNeed is required")
        if not need.growth_theme:
            raise LiveNeedBridgeRejected("FamilyNeed must provide a growth theme")
        if need.expires_at.astimezone(UTC) <= now.astimezone(UTC):
            raise LiveNeedBridgeRejected("FamilyNeed projection has expired")
        if need.tenant_id != guardian.tenant_id or need.family_id != guardian.family_id:
            raise LiveNeedBridgeRejected("FamilyNeed crosses the authenticated scope")
        return need

    @staticmethod
    def _require_adult(guardian: AdultContext) -> None:
        if guardian.actor_type != "FAMILY_GUARDIAN":
            raise LiveNeedBridgeRejected("only an authenticated guardian may choose a service")
