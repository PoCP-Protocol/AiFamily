"""Auditable fake adapters for the GrowthIntent -> Onboarding slice."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from ..application.growth_onboarding import (
    GrowthOnboardingDependencies,
    Operation,
    StartGrowthOnboardingCommand,
    _audit_record,
    idempotency_storage_key,
    request_hash,
)
from ..domain.growth_onboarding import (
    GROWTH_ONBOARDING_ACTION,
    GROWTH_ONBOARDING_EVENT,
    ConfirmedGrowthIntent,
    GrowthOnboarding,
    GrowthOnboardingConflictError,
    GrowthOnboardingForbiddenError,
    GrowthOnboardingScope,
)


class FakeConfirmedGrowthIntentReader:
    """Independent fake for the reader port; it is not an Assessment fake."""

    def __init__(self, intents: list[ConfirmedGrowthIntent] | None = None):
        self.intents = {
            (intent.tenant_id, intent.family_id, intent.intent_id): intent
            for intent in intents or []
        }

    def add(self, intent: ConfirmedGrowthIntent) -> None:
        self.intents[(intent.tenant_id, intent.family_id, intent.intent_id)] = intent

    async def load_confirmed_growth_intent(
        self, scope: GrowthOnboardingScope, intent_id: str
    ) -> ConfirmedGrowthIntent | None:
        return self.intents.get((scope.tenant_id, scope.family_id, intent_id))


class FakeGrowthOnboardingRepository:
    """Fake store with an explicit queryable binding, not an object-only link."""

    def __init__(self) -> None:
        self.onboardings: dict[str, GrowthOnboarding] = {}
        self.bindings: dict[tuple[str, str, str], dict[str, str]] = {}

    async def save_if_absent(
        self, onboarding: GrowthOnboarding
    ) -> tuple[GrowthOnboarding, bool]:
        key = (onboarding.tenant_id, onboarding.family_id, onboarding.intent_id)
        existing_binding = self.bindings.get(key)
        if existing_binding is not None:
            existing = self.onboardings.get(existing_binding["onboarding_id"])
            if existing is None or (
                existing != onboarding and existing.binding_id is None
            ):
                raise GrowthOnboardingConflictError("intent_onboarding_binding_invalid")
            return existing, False

        existing = self.onboardings.get(onboarding.onboarding_id)
        if existing is not None:
            if (
                existing.tenant_id != onboarding.tenant_id
                or existing.family_id != onboarding.family_id
                or existing.intent_id != onboarding.intent_id
            ):
                raise GrowthOnboardingConflictError("onboarding_identity_conflict")
            if existing.binding_id is None:
                raise GrowthOnboardingConflictError("intent_onboarding_binding_invalid")
            return existing, False

        binding_id = str(
            uuid5(
                NAMESPACE_URL,
                f"growth-onboarding-binding:{onboarding.tenant_id}:"
                f"{onboarding.family_id}:{onboarding.intent_id}",
            )
        )
        stored = GrowthOnboarding(
            **{**asdict(onboarding), "binding_id": binding_id}
        )
        self.onboardings[stored.onboarding_id] = stored
        self.bindings[key] = {
            "binding_id": binding_id,
            "tenant_id": stored.tenant_id,
            "family_id": stored.family_id,
            "intent_id": stored.intent_id,
            "onboarding_id": stored.onboarding_id,
            "subject_person_id": stored.subject_person_id,
        }
        return stored, True


@dataclass(frozen=True)
class FakeConsentRecord:
    family_id: str
    subject_person_id: str
    purpose: str
    status: str
    granted_at: datetime
    effective_from: datetime | None = None


@dataclass(frozen=True)
class FakeTenantFamilyBinding:
    """The canonical tenant-family scope used by the consent query."""

    tenant_id: str
    family_id: str
    status: str
    effective_from: datetime
    effective_to: datetime | None = None


class FakeGrowthOnboardingPolicy:
    def __init__(self) -> None:
        self.allowed_scopes: set[tuple[str, str, str]] = set()

    def allow(self, scope: GrowthOnboardingScope) -> None:
        self.allowed_scopes.add((scope.tenant_id, scope.family_id, scope.actor_id))

    async def assert_can_start(self, scope: GrowthOnboardingScope) -> None:
        if (scope.tenant_id, scope.family_id, scope.actor_id) not in self.allowed_scopes:
            raise GrowthOnboardingForbiddenError("actor_family_scope_denied")


class FakeGrowthOnboardingConsent:
    """Fake consent store with the canonical status/time predicate."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self.grants: list[FakeConsentRecord] = []
        self.bindings: dict[tuple[str, str], FakeTenantFamilyBinding] = {}
        self._now = now or (lambda: datetime.now(UTC))

    def bind(
        self,
        scope: GrowthOnboardingScope,
        *,
        status: str = "ACTIVE",
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
    ) -> None:
        self.bindings[(scope.tenant_id, scope.family_id)] = FakeTenantFamilyBinding(
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            status=status,
            effective_from=effective_from or self._now(),
            effective_to=effective_to,
        )

    def grant(
        self,
        scope: GrowthOnboardingScope,
        subject_person_id: str,
        purpose: str,
        *,
        granted_at: datetime | None = None,
        effective_from: datetime | None = None,
    ) -> None:
        recorded_at = granted_at or self._now()
        self.bindings.setdefault(
            (scope.tenant_id, scope.family_id),
            FakeTenantFamilyBinding(
                tenant_id=scope.tenant_id,
                family_id=scope.family_id,
                status="ACTIVE",
                effective_from=self._now(),
            ),
        )
        self.grants.append(
            FakeConsentRecord(
                family_id=scope.family_id,
                subject_person_id=subject_person_id,
                purpose=purpose,
                status="GRANTED",
                granted_at=recorded_at,
                effective_from=effective_from or recorded_at,
            )
        )

    def withdraw(self, scope: GrowthOnboardingScope, subject_person_id: str, purpose: str) -> None:
        self._replace_status(scope, subject_person_id, purpose, "WITHDRAWN")

    def expire(self, scope: GrowthOnboardingScope, subject_person_id: str, purpose: str) -> None:
        self._replace_status(scope, subject_person_id, purpose, "EXPIRED")

    def _replace_status(
        self, scope: GrowthOnboardingScope, subject_person_id: str, purpose: str, status: str
    ) -> None:
        self.grants = [
            FakeConsentRecord(
                **{**asdict(record), "status": status}
            )
            if (
                record.family_id == scope.family_id
                and record.subject_person_id == subject_person_id
                and record.purpose == purpose
            )
            else record
            for record in self.grants
        ]

    async def assert_granted(
        self,
        scope: GrowthOnboardingScope,
        subject_person_id: str,
        purpose: str,
    ) -> None:
        moment = self._now()
        binding = self.bindings.get((scope.tenant_id, scope.family_id))
        binding_active = binding is not None and (
            binding.status == "ACTIVE"
            and binding.effective_from <= moment
            and (binding.effective_to is None or binding.effective_to > moment)
        )
        active = any(
            binding_active
            and record.family_id == scope.family_id
            and record.subject_person_id == subject_person_id
            and record.purpose == purpose
            and record.status == "GRANTED"
            and record.granted_at <= moment
            and (record.effective_from or record.granted_at) <= moment
            for record in self.grants
        )
        if not active:
            raise GrowthOnboardingForbiddenError(f"missing_consent:{purpose}")


@dataclass
class _Replay:
    action: str
    request_hash: str
    response: dict


AuditWriter = Callable[[dict[str, object]], Awaitable[None]]
OutboxWriter = Callable[[dict[str, object]], Awaitable[None]]


class FakeGrowthOnboardingTransaction:
    """Single-process fake with the same atomic mutation contract as Postgres."""

    def __init__(
        self,
        *,
        intent_reader: FakeConfirmedGrowthIntentReader,
        repository: FakeGrowthOnboardingRepository,
        policy: FakeGrowthOnboardingPolicy,
        consent: FakeGrowthOnboardingConsent,
        audit_writer: AuditWriter | None = None,
        outbox_writer: OutboxWriter | None = None,
    ) -> None:
        self.dependencies = GrowthOnboardingDependencies(
            intent_reader=intent_reader,
            repository=repository,
            policy=policy,
            consent=consent,
        )
        self.repository = repository
        self.idempotency: dict[str, _Replay] = {}
        self.audit_log: list[dict] = []
        self.outbox_events: list[dict] = []
        self._audit_writer = audit_writer or self._write_audit
        self._outbox_writer = outbox_writer or self._write_outbox
        self._lock = asyncio.Lock()

    async def execute(self, command: StartGrowthOnboardingCommand, operation: Operation) -> dict:
        current_hash = request_hash(command)
        async with self._lock:
            storage_key = idempotency_storage_key(command)
            replay = self.idempotency.get(storage_key)
            if replay is not None:
                if replay.action != GROWTH_ONBOARDING_ACTION or replay.request_hash != current_hash:
                    raise GrowthOnboardingConflictError("idempotency_conflict")
                return {**deepcopy(replay.response), "replayed": True}

            before_onboardings = deepcopy(self.repository.onboardings)
            before_bindings = deepcopy(self.repository.bindings)
            before_idempotency = deepcopy(self.idempotency)
            before_audit = deepcopy(self.audit_log)
            before_outbox = deepcopy(self.outbox_events)
            try:
                response = await operation(self.dependencies)
                occurred_at = datetime.now(UTC)
                await self._audit_writer(_audit_record(command, response, occurred_at))
                await self._outbox_writer(
                    {
                        "aggregate_type": "GrowthOnboarding",
                        "aggregate_id": response["event"]["onboarding_id"],
                        "event_name": GROWTH_ONBOARDING_EVENT,
                        "event_version": response["event"]["event_version"],
                        "event_id": response["event"]["event_id"],
                        "correlation_id": command.correlation_id,
                        "payload": deepcopy(response["event"]),
                    }
                )
                self.idempotency[storage_key] = _Replay(
                    action=GROWTH_ONBOARDING_ACTION,
                    request_hash=current_hash,
                    response=deepcopy(response),
                )
                return response
            except Exception:
                self.repository.onboardings = before_onboardings
                self.repository.bindings = before_bindings
                self.idempotency = before_idempotency
                self.audit_log = before_audit
                self.outbox_events = before_outbox
                raise

    async def _write_audit(self, record: dict[str, object]) -> None:
        self.audit_log.append(record)

    async def _write_outbox(self, event: dict[str, object]) -> None:
        if not any(item["event_id"] == event["event_id"] for item in self.outbox_events):
            self.outbox_events.append(event)


__all__ = [
    "FakeConfirmedGrowthIntentReader",
    "FakeConsentRecord",
    "FakeGrowthOnboardingConsent",
    "FakeGrowthOnboardingPolicy",
    "FakeGrowthOnboardingRepository",
    "FakeGrowthOnboardingTransaction",
    "FakeTenantFamilyBinding",
]
