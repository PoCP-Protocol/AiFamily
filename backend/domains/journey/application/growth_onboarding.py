"""Application boundary for ``CONFIRMED GrowthIntent -> Onboarding``.

The only Assessment dependency here is the ``ConfirmedGrowthIntentReader``
port.  Journey never imports or calls an Assessment repository.  Production
and fake adapters implement the same transaction-shaped contract, including
idempotency, audit and outbox behavior.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from backend.platform.audit.models import AuditEvent
from backend.platform.idempotency.keys import IdempotencyKey

from ..domain.growth_onboarding import (
    CONFIRMED_INTENT_BOUNDARY,
    GROWTH_ONBOARDING_ACTION,
    GROWTH_TRACKING_PURPOSE,
    ConfirmedGrowthIntent,
    GrowthOnboarding,
    GrowthOnboardingConflictError,
    GrowthOnboardingForbiddenError,
    GrowthOnboardingNotFoundError,
    GrowthOnboardingScope,
    GrowthOnboardingStarted,
    GrowthOnboardingValidationError,
)


class ConfirmedGrowthIntentReader(Protocol):
    async def load_confirmed_growth_intent(
        self, scope: GrowthOnboardingScope, intent_id: str
    ) -> ConfirmedGrowthIntent | None: ...


class GrowthOnboardingRepository(Protocol):
    """Persist the journey and its intent binding in the current transaction."""

    async def save_if_absent(
        self, onboarding: GrowthOnboarding
    ) -> tuple[GrowthOnboarding, bool]: ...


class GrowthOnboardingPolicy(Protocol):
    async def assert_can_start(self, scope: GrowthOnboardingScope) -> None: ...


class GrowthOnboardingConsentPort(Protocol):
    async def assert_granted(
        self,
        scope: GrowthOnboardingScope,
        subject_person_id: str,
        purpose: str,
    ) -> None: ...


@dataclass(frozen=True)
class StartGrowthOnboardingCommand:
    tenant_id: str
    family_id: str
    actor_id: str
    intent_id: str
    correlation_id: str
    idempotency_key: str

    @property
    def scope(self) -> GrowthOnboardingScope:
        return GrowthOnboardingScope(
            tenant_id=self.tenant_id,
            family_id=self.family_id,
            actor_id=self.actor_id,
        )

    def payload(self) -> dict[str, str]:
        return {
            "intent_id": self.intent_id,
            "consent_purpose": GROWTH_TRACKING_PURPOSE,
        }


@dataclass(frozen=True)
class GrowthOnboardingDependencies:
    intent_reader: ConfirmedGrowthIntentReader
    repository: GrowthOnboardingRepository
    policy: GrowthOnboardingPolicy
    consent: GrowthOnboardingConsentPort


Operation = Callable[[GrowthOnboardingDependencies], Awaitable[dict]]


class GrowthOnboardingTransaction(Protocol):
    async def execute(
        self,
        command: StartGrowthOnboardingCommand,
        operation: Operation,
    ) -> dict: ...


class GrowthOnboardingService:
    def __init__(self, dependencies: GrowthOnboardingDependencies):
        self._dependencies = dependencies

    async def start(self, command: StartGrowthOnboardingCommand) -> dict:
        scope = command.scope
        await self._dependencies.policy.assert_can_start(scope)
        intent = await self._dependencies.intent_reader.load_confirmed_growth_intent(
            scope, command.intent_id
        )
        if intent is None or not intent.is_confirmed:
            raise GrowthOnboardingNotFoundError("confirmed_growth_intent_not_found")
        if intent.tenant_id != scope.tenant_id or intent.family_id != scope.family_id:
            raise GrowthOnboardingForbiddenError("growth_intent_scope_denied")
        if intent.boundary != CONFIRMED_INTENT_BOUNDARY:
            raise GrowthOnboardingConflictError("growth_intent_boundary_invalid")
        await self._dependencies.consent.assert_granted(
            scope, intent.subject_person_id, GROWTH_TRACKING_PURPOSE
        )

        onboarding = GrowthOnboarding.start(scope, intent)
        stored, created = await self._dependencies.repository.save_if_absent(onboarding)
        if (
            stored.binding_id is None
            or stored.tenant_id != scope.tenant_id
            or stored.family_id != scope.family_id
            or stored.intent_id != intent.intent_id
            or stored.subject_person_id != intent.subject_person_id
        ):
            raise GrowthOnboardingConflictError("intent_onboarding_binding_invalid")
        event = GrowthOnboardingStarted.from_onboarding(stored)
        return {
            "onboarding": stored.as_dict(),
            "event": event.as_dict(),
            "created": created,
            "replayed": False,
        }


class GrowthOnboardingApplication:
    def __init__(self, transaction: GrowthOnboardingTransaction):
        self._transaction = transaction

    async def start(self, command: StartGrowthOnboardingCommand) -> dict:
        _validate_command(command)

        async def operation(dependencies: GrowthOnboardingDependencies) -> dict:
            return await GrowthOnboardingService(dependencies).start(command)

        return await self._transaction.execute(command, operation)


def _validate_command(command: StartGrowthOnboardingCommand) -> None:
    values = (
        command.tenant_id,
        command.family_id,
        command.actor_id,
        command.intent_id,
        command.correlation_id,
        command.idempotency_key,
    )
    if any(not value or not value.strip() for value in values):
        raise GrowthOnboardingValidationError("growth_onboarding_command_required")
    if len(command.idempotency_key) > 128:
        raise GrowthOnboardingValidationError("invalid_idempotency_key")
    if len(command.correlation_id) > 128:
        raise GrowthOnboardingValidationError("invalid_correlation_id")
    if command.actor_id.lower().startswith("ai:") or command.actor_id.upper() in {
        "AI",
        "SYSTEM",
    }:
        raise GrowthOnboardingForbiddenError("human_actor_required")


def request_hash(command: StartGrowthOnboardingCommand) -> str:
    canonical = json.dumps(
        {
            "action": GROWTH_ONBOARDING_ACTION,
            "tenant_id": command.tenant_id,
            "family_id": command.family_id,
            "actor_id": command.actor_id,
            "payload": command.payload(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def idempotency_storage_key(command: StartGrowthOnboardingCommand) -> str:
    """Return a bounded database key for the canonical tenant-scoped key.

    The legacy table has one ``varchar(128)`` key column and no tenant column.
    Persisting the raw client value there would make the namespace global.  The
    platform contract supplies the tenant-scoped value; hashing that encoded
    value keeps the namespace unambiguous and within the legacy column limit.
    The raw client value remains in the audit record for operator correlation.
    """

    scoped_value = IdempotencyKey(
        tenant_id=command.tenant_id,
        value=command.idempotency_key,
    ).scoped_value
    return hashlib.sha256(scoped_value.encode("utf-8")).hexdigest()


def growth_onboarding_audit_event(
    command: StartGrowthOnboardingCommand, response: dict, occurred_at: datetime
) -> AuditEvent:
    onboarding = response["onboarding"]
    assert isinstance(onboarding, dict)
    action = (
        "human-confirmed GrowthIntent accepted; GrowthOnboarding created"
        if response.get("created")
        else "human-confirmed GrowthIntent accepted; existing GrowthOnboarding reused"
    )
    return AuditEvent(
        actor_id=command.actor_id,
        tenant_id=command.tenant_id,
        action=GROWTH_ONBOARDING_ACTION,
        resource_type="GrowthOnboarding",
        resource_id=str(onboarding["onboarding_id"]),
        reason=action,
        correlation_id=command.correlation_id,
        before=None,
        after=onboarding,
        timestamp=occurred_at,
    )


def _audit_record(
    command: StartGrowthOnboardingCommand, response: dict, occurred_at: datetime
) -> dict[str, object]:
    event = growth_onboarding_audit_event(command, response, occurred_at)
    onboarding = response["onboarding"]
    assert isinstance(onboarding, dict)
    return {
        "tenant_id": event.tenant_id,
        "family_id": command.family_id,
        "actor_id": event.actor_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "intent_id": onboarding["intent_id"],
        "correlation_id": event.correlation_id,
        "idempotency_key": command.idempotency_key,
        "occurred_at": event.timestamp.isoformat(),
        "reason": event.reason,
        "before": event.before,
        "after": event.after,
        "action_kind": str(event.action_kind),
    }
