"""Scene C: result-page next-step choice.

This module is an application boundary, not a second FamilyNeed or
GrowthIntent aggregate.  ``FamilyNeedReader`` and ``SceneCIntentStore`` are
ports to the canonical owners.  The Journey adapter only orchestrates the
family action:

    confirmed FamilyNeed -> adult chooses one non-commercial next step
    -> canonical intent is created -> the intent can be read back or withdrawn.

The store port is deliberately transactional: a real adapter must persist the
intent mutation, canonical AuditEvent, and outbox event in the same unit of
work.  The test fake may replace that external persistence, but it must retain
the same state, scope, idempotency, and failure semantics.

Consent is checked afresh for every read/write through the canonical
``ConsentGate``.  Withdrawal is a safety exit and remains available after
consent withdrawal; it does not expose the withdrawn subject data.  Data
deletion is not silently performed by this business action.  A production
composition must connect the returned deletion reference to the canonical
``SubjectDeletionCommand``/worker when a separate deletion request exists.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from backend.domains.family_need.domain.entities import FamilyNeed
from backend.domains.family_need.domain.value_objects import NeedStatus
from backend.platform.audit import AuditActionKind, AuditEvent
from backend.platform.consent import ConsentGate, ConsentGrant, ConsentPurpose
from backend.platform.identity import ActorContext

SCENE_C_BOUNDARY = "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
_ALLOWED_NEXT_STEPS = frozenset({"HOME_ACTION", "ASK_FOR_HELP", "REVIEW_LATER"})


class SceneCStatus(StrEnum):
    OPEN = "OPEN"
    WITHDRAWN = "WITHDRAWN"


class SceneCError(Exception):
    """Base error mapped by the standalone HTTP adapter."""

    code = "scene_c_error"


class SceneCValidationError(SceneCError):
    code = "scene_c_validation_error"


class SceneCForbiddenError(SceneCError):
    code = "scene_c_forbidden"


class SceneCNotFoundError(SceneCError):
    code = "scene_c_not_found"


class SceneCConflictError(SceneCError):
    code = "scene_c_conflict"


@dataclass(frozen=True, slots=True)
class SceneCIntentView:
    """Read model returned by the canonical Intent store.

    This is an adapter DTO, not a replacement domain aggregate.  The
    ``intent_id`` and lifecycle state belong to the store's canonical owner.
    """

    intent_id: str
    tenant_id: str
    family_id: str
    need_id: str
    subject_person_id: str
    next_step: str
    status: str
    requested_by: str
    boundary: str = SCENE_C_BOUNDARY
    commercial_intent: bool = False
    deletion_ref: str | None = None
    withdrawn_by: str | None = None
    withdrawn_reason: str | None = None
    created_at: datetime | None = None
    withdrawn_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in (
            "intent_id",
            "tenant_id",
            "family_id",
            "need_id",
            "subject_person_id",
            "next_step",
            "status",
            "requested_by",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")
        if self.status not in {status.value for status in SceneCStatus}:
            raise ValueError("scene_c_intent_status_invalid")
        if self.next_step not in _ALLOWED_NEXT_STEPS:
            raise ValueError("scene_c_next_step_invalid")
        if self.boundary != SCENE_C_BOUNDARY:
            raise ValueError("scene_c_intent_boundary_invalid")
        if self.commercial_intent:
            raise ValueError("scene_c_next_step_must_not_create_commercial_intent")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> SceneCIntentView:
        def text(name: str) -> str:
            raw = value.get(name)
            if not isinstance(raw, str):
                raise SceneCValidationError(f"intent_{name}_invalid")
            return raw

        def optional_text(name: str) -> str | None:
            raw = value.get(name)
            if raw is None:
                return None
            if not isinstance(raw, str):
                raise SceneCValidationError(f"intent_{name}_invalid")
            return raw

        return cls(
            intent_id=text("intent_id"),
            tenant_id=text("tenant_id"),
            family_id=text("family_id"),
            need_id=text("need_id"),
            subject_person_id=text("subject_person_id"),
            next_step=text("next_step"),
            status=text("status"),
            requested_by=text("requested_by"),
            boundary=text("boundary"),
            commercial_intent=bool(value.get("commercial_intent", False)),
            deletion_ref=optional_text("deletion_ref"),
            withdrawn_by=optional_text("withdrawn_by"),
            withdrawn_reason=optional_text("withdrawn_reason"),
            created_at=value.get("created_at")
            if isinstance(value.get("created_at"), datetime)
            else None,
            withdrawn_at=value.get("withdrawn_at")
            if isinstance(value.get("withdrawn_at"), datetime)
            else None,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "intent_id": self.intent_id,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "need_id": self.need_id,
            "subject_person_id": self.subject_person_id,
            "next_step": self.next_step,
            "status": self.status,
            "requested_by": self.requested_by,
            "boundary": self.boundary,
            "commercial_intent": self.commercial_intent,
            "deletion_ref": self.deletion_ref,
            "withdrawn_by": self.withdrawn_by,
            "withdrawn_reason": self.withdrawn_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "withdrawn_at": self.withdrawn_at.isoformat() if self.withdrawn_at else None,
        }


@dataclass(frozen=True, slots=True)
class SceneCStoreResult:
    intent: SceneCIntentView
    replayed: bool = False


class FamilyNeedReader(Protocol):
    """Read the canonical FamilyNeed aggregate in tenant/family scope."""

    async def load(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> FamilyNeed | None: ...


class SceneCScopePort(Protocol):
    """Identity integration backed by the canonical trusted-scope resolver."""

    async def assert_can_access(self, *, actor: ActorContext, family_id: str) -> None: ...


class SceneCConsentPort(Protocol):
    """Fresh ConsentGrant reads; the adapter never accepts grants from HTTP."""

    async def grants_for(
        self,
        *,
        actor: ActorContext,
        family_id: str,
        subject_person_id: str,
        purpose: ConsentPurpose,
    ) -> Iterable[ConsentGrant]: ...


class SceneCIntentStore(Protocol):
    """Canonical Intent persistence plus same-transaction audit/outbox."""

    async def create_or_replay(
        self,
        *,
        intent: SceneCIntentView,
        idempotency_key: str,
        request_hash: str,
        audit_event: AuditEvent,
        outbox_event: Mapping[str, object],
    ) -> SceneCStoreResult: ...

    async def load(
        self, *, tenant_id: str, family_id: str, intent_id: str
    ) -> SceneCIntentView | None: ...

    async def record_read_or_replay(
        self,
        *,
        intent: SceneCIntentView,
        idempotency_key: str,
        request_hash: str,
        audit_event: AuditEvent,
    ) -> SceneCStoreResult: ...

    async def withdraw_or_replay(
        self,
        *,
        intent: SceneCIntentView,
        actor: ActorContext,
        reason: str,
        idempotency_key: str,
        request_hash: str,
        audit_event: AuditEvent,
        outbox_event: Mapping[str, object],
    ) -> SceneCStoreResult: ...


class SceneCDeletionReferencePort(Protocol):
    """Return deletion handles; never execute deletion during withdrawal."""

    async def refs_for_intent(
        self, *, tenant_id: str, family_id: str, intent_id: str, subject_person_id: str
    ) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class SceneCReceipt:
    intent: SceneCIntentView
    replayed: bool
    deletion_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent.as_dict(),
            "replayed": self.replayed,
            "deletion_refs": list(self.deletion_refs),
            "boundary": SCENE_C_BOUNDARY,
        }


class SceneCApplication:
    """Orchestrate the one adult result-page action."""

    def __init__(
        self,
        *,
        scope: SceneCScopePort,
        consent: SceneCConsentPort,
        family_needs: FamilyNeedReader,
        intents: SceneCIntentStore,
        deletion_refs: SceneCDeletionReferencePort,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._scope = scope
        self._consent = consent
        self._family_needs = family_needs
        self._intents = intents
        self._deletion_refs = deletion_refs
        self._clock = clock or (lambda: datetime.now(UTC))

    async def choose_next_step(
        self,
        *,
        actor: ActorContext,
        family_id: str,
        need_id: str,
        subject_person_id: str,
        next_step: str,
        idempotency_key: str,
    ) -> SceneCReceipt:
        self._validate_actor(actor)
        self._validate_text(family_id, "family_id")
        self._validate_text(need_id, "need_id")
        self._validate_text(subject_person_id, "subject_person_id")
        self._validate_idempotency(idempotency_key)
        normalized_step = self._normalize_next_step(next_step)
        await self._scope.assert_can_access(actor=actor, family_id=family_id)

        need = await self._family_needs.load(
            tenant_id=actor.tenant_id, family_id=family_id, need_id=need_id
        )
        if need is None:
            raise SceneCNotFoundError("family_need_not_found")
        if need.tenant_id != actor.tenant_id or need.family_id != family_id:
            raise SceneCForbiddenError("family_need_scope_denied")
        if need.status is not NeedStatus.CONFIRMED:
            raise SceneCConflictError("family_need_must_be_confirmed")
        if subject_person_id not in need.subject_person_ids:
            raise SceneCForbiddenError("subject_not_in_family_need")
        await self._assert_live_consent(actor, family_id, subject_person_id)

        intent_id = str(
            uuid5(
                NAMESPACE_URL,
                f"scene-c-intent:{actor.tenant_id}:{family_id}:{need_id}:{normalized_step}",
            )
        )
        request_hash = _request_hash(
            {
                "actor_id": actor.actor_id,
                "family_id": family_id,
                "need_id": need_id,
                "subject_person_id": subject_person_id,
                "next_step": normalized_step,
            }
        )
        now = self._now()
        intent = SceneCIntentView(
            intent_id=intent_id,
            tenant_id=actor.tenant_id,
            family_id=family_id,
            need_id=need_id,
            subject_person_id=subject_person_id,
            next_step=normalized_step,
            status=SceneCStatus.OPEN.value,
            requested_by=actor.actor_id,
            created_at=now,
            deletion_ref=f"scene-c:intent:{actor.tenant_id}:{family_id}:{intent_id}",
        )
        result = await self._intents.create_or_replay(
            intent=intent,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            audit_event=_mutation_audit(
                actor=actor,
                action="scene_c.intent.confirmed",
                intent=intent,
                before=None,
                after={"need_id": need_id, "next_step": normalized_step, "status": intent.status},
                reason="adult_selected_non_commercial_next_step",
            ),
            outbox_event=_outbox(
                actor=actor,
                event_name="growth.intent.confirmed",
                intent=intent,
                idempotency_key=idempotency_key,
            ),
        )
        return await self._receipt(result)

    async def readback(
        self,
        *,
        actor: ActorContext,
        family_id: str,
        intent_id: str,
        idempotency_key: str,
    ) -> SceneCReceipt:
        self._validate_actor(actor)
        self._validate_text(family_id, "family_id")
        self._validate_text(intent_id, "intent_id")
        self._validate_idempotency(idempotency_key)
        await self._scope.assert_can_access(actor=actor, family_id=family_id)
        intent = await self._required_intent(actor.tenant_id, family_id, intent_id)
        grants = await self._assert_live_consent(
            actor, family_id, intent.subject_person_id, return_grants=True
        )
        grant = next(
            (item for item in grants if item.subject_person_id == intent.subject_person_id),
            None,
        )
        if grant is None:
            raise SceneCForbiddenError("growth_tracking_consent_required")
        request_hash = _request_hash(
            {"family_id": family_id, "intent_id": intent_id, "actor_id": actor.actor_id}
        )
        read_audit = AuditEvent(
            actor_id=actor.actor_id,
            tenant_id=actor.tenant_id,
            action="scene_c.intent.readback",
            resource_type="growth_intent",
            resource_id=intent_id,
            reason="adult_requested_result_page_readback",
            correlation_id=actor.correlation_id,
            action_kind=AuditActionKind.READ,
            subject_person_id=intent.subject_person_id,
            subject_is_minor=grant.subject_age.years < 18,
            accessed_fields=("intent_id", "need_id", "next_step", "status"),
            access_purpose=ConsentPurpose.GROWTH_TRACKING.value,
            approval_ref=grant.consent_id if grant.subject_age.years < 18 else None,
        )
        result = await self._intents.record_read_or_replay(
            intent=intent,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            audit_event=read_audit,
        )
        return await self._receipt(result)

    async def withdraw(
        self,
        *,
        actor: ActorContext,
        family_id: str,
        intent_id: str,
        reason: str,
        idempotency_key: str,
    ) -> SceneCReceipt:
        self._validate_actor(actor)
        self._validate_text(family_id, "family_id")
        self._validate_text(intent_id, "intent_id")
        self._validate_text(reason, "withdraw_reason")
        self._validate_idempotency(idempotency_key)
        await self._scope.assert_can_access(actor=actor, family_id=family_id)
        intent = await self._required_intent(actor.tenant_id, family_id, intent_id)
        if intent.status == SceneCStatus.WITHDRAWN.value:
            # A safe stop remains replayable even when Consent was withdrawn.
            # No subject content is read and no new processing is started.
            pass
        request_hash = _request_hash(
            {"family_id": family_id, "intent_id": intent_id, "reason": reason.strip()}
        )
        withdrawn = replace(
            intent,
            status=SceneCStatus.WITHDRAWN.value,
            withdrawn_by=actor.actor_id,
            withdrawn_reason=reason.strip(),
            withdrawn_at=self._now(),
        )
        result = await self._intents.withdraw_or_replay(
            intent=intent,
            actor=actor,
            reason=reason.strip(),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            audit_event=_mutation_audit(
                actor=actor,
                action="scene_c.intent.withdrawn",
                intent=withdrawn,
                before={"status": intent.status},
                after={"status": withdrawn.status},
                reason=reason.strip(),
            ),
            outbox_event=_outbox(
                actor=actor,
                event_name="growth.intent.withdrawn",
                intent=withdrawn,
                idempotency_key=idempotency_key,
            ),
        )
        return await self._receipt(result)

    async def _receipt(self, result: SceneCStoreResult) -> SceneCReceipt:
        refs = await self._deletion_refs.refs_for_intent(
            tenant_id=result.intent.tenant_id,
            family_id=result.intent.family_id,
            intent_id=result.intent.intent_id,
            subject_person_id=result.intent.subject_person_id,
        )
        return SceneCReceipt(result.intent, result.replayed, refs)

    async def _required_intent(
        self, tenant_id: str, family_id: str, intent_id: str
    ) -> SceneCIntentView:
        intent = await self._intents.load(
            tenant_id=tenant_id, family_id=family_id, intent_id=intent_id
        )
        if intent is None:
            raise SceneCNotFoundError("growth_intent_not_found")
        if intent.tenant_id != tenant_id or intent.family_id != family_id:
            raise SceneCForbiddenError("growth_intent_scope_denied")
        return intent

    async def _assert_live_consent(
        self,
        actor: ActorContext,
        family_id: str,
        subject_person_id: str,
        *,
        return_grants: bool = False,
    ) -> tuple[ConsentGrant, ...]:
        grants = tuple(
            await self._consent.grants_for(
                actor=actor,
                family_id=family_id,
                subject_person_id=subject_person_id,
                purpose=ConsentPurpose.GROWTH_TRACKING,
            )
        )
        if not ConsentGate.check(subject_person_id, ConsentPurpose.GROWTH_TRACKING, grants):
            raise SceneCForbiddenError("growth_tracking_consent_required")
        return grants if return_grants else grants

    @staticmethod
    def _validate_actor(actor: ActorContext) -> None:
        if not isinstance(actor, ActorContext) or not actor.is_human:
            raise SceneCForbiddenError("human_confirmation_required")

    @staticmethod
    def _validate_text(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise SceneCValidationError(f"{name}_required")

    @staticmethod
    def _validate_idempotency(value: str) -> None:
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise SceneCValidationError("idempotency_key_required")

    @staticmethod
    def _normalize_next_step(value: str) -> str:
        if not isinstance(value, str):
            raise SceneCValidationError("next_step_required")
        normalized = value.strip().upper()
        if normalized not in _ALLOWED_NEXT_STEPS:
            raise SceneCValidationError("next_step_not_available")
        return normalized

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise SceneCValidationError("scene_c_clock_requires_timezone")
        return value


def _request_hash(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _mutation_audit(
    *,
    actor: ActorContext,
    action: str,
    intent: SceneCIntentView,
    before: Mapping[str, object] | None,
    after: Mapping[str, object],
    reason: str,
) -> AuditEvent:
    return AuditEvent(
        actor_id=actor.actor_id,
        tenant_id=actor.tenant_id,
        action=action,
        resource_type="growth_intent",
        resource_id=intent.intent_id,
        reason=reason,
        correlation_id=actor.correlation_id,
        before=dict(before) if before is not None else None,
        after=dict(after),
    )


def _outbox(
    *, actor: ActorContext, event_name: str, intent: SceneCIntentView, idempotency_key: str
) -> dict[str, object]:
    return {
        "event_name": event_name,
        "event_version": 1,
        "aggregate_type": "GrowthIntent",
        "aggregate_id": intent.intent_id,
        "tenant_id": actor.tenant_id,
        "family_id": intent.family_id,
        "actor_id": actor.actor_id,
        "idempotency_key": idempotency_key,
        "boundary": SCENE_C_BOUNDARY,
        "status": intent.status,
    }


__all__ = [
    "FamilyNeedReader",
    "SCENE_C_BOUNDARY",
    "SceneCApplication",
    "SceneCConflictError",
    "SceneCConsentPort",
    "SceneCDeletionReferencePort",
    "SceneCError",
    "SceneCForbiddenError",
    "SceneCIntentStore",
    "SceneCIntentView",
    "SceneCNotFoundError",
    "SceneCReceipt",
    "SceneCScopePort",
    "SceneCStatus",
    "SceneCStoreResult",
    "SceneCValidationError",
]
