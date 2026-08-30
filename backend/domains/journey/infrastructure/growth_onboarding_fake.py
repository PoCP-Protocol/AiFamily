"""Auditable fake adapters for the GrowthIntent -> Onboarding slice."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from backend.platform.consent.models import ConsentGrant, ConsentPurpose, ConsentStatus

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

    async def save_if_absent(self, onboarding: GrowthOnboarding) -> tuple[GrowthOnboarding, bool]:
        key = (onboarding.tenant_id, onboarding.family_id, onboarding.intent_id)
        existing_binding = self.bindings.get(key)
        if existing_binding is not None:
            existing = self.onboardings.get(existing_binding["onboarding_id"])
            if existing is None or (existing != onboarding and existing.binding_id is None):
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
        stored = GrowthOnboarding(**{**asdict(onboarding), "binding_id": binding_id})
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
    """The fake's local representation of the canonical ``ConsentGrant``.

    The platform model is deliberately kept in the consent foundation.  This
    fake mirrors its scope and lifecycle fields so the Journey adapter can be
    exercised from the pre-foundation baseline as well as after that model is
    integrated.  In particular, a family id without its tenant id is never a
    sufficient query key.
    """

    consent_id: str
    subject_person_id: str
    guardian_person_id: str
    purpose: ConsentPurpose | str
    status: ConsentStatus | str
    granted_at: datetime
    tenant_id: str | None = None
    family_id: str | None = None
    guardian_relation: Any = None
    subject_age: Any = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    withdrawn_at: datetime | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "consent_id",
            "subject_person_id",
            "guardian_person_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"FakeConsentRecord.{field_name} must not be empty")

        for field_name in ("tenant_id", "family_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"FakeConsentRecord.{field_name} must not be empty")

        object.__setattr__(self, "purpose", _coerce_purpose(self.purpose))
        object.__setattr__(self, "status", _coerce_status(self.status))

        for field_name in (
            "granted_at",
            "effective_from",
            "effective_to",
            "withdrawn_at",
            "expires_at",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, datetime):
                raise TypeError(f"FakeConsentRecord.{field_name} must be datetime or None")

        if (
            self.effective_to is not None
            and self.expires_at is not None
            and _as_comparable(self.effective_to, self.expires_at) != self.expires_at
        ):
            raise ValueError(
                "FakeConsentRecord.effective_to and expires_at must describe the same boundary"
            )

        effective_from = self.effective_from or self.granted_at
        effective_to = self.effective_to or self.expires_at
        if (
            effective_to is not None
            and _as_comparable(effective_to, effective_from) <= effective_from
        ):
            raise ValueError("FakeConsentRecord.effective_to must be after effective_from")

    @property
    def effective_window(self) -> tuple[datetime, datetime | None]:
        return self.effective_from or self.granted_at, self.effective_to or self.expires_at

    def status_at(self, moment: datetime | None = None) -> ConsentStatus:
        if self.status is not ConsentStatus.GRANTED:
            return self.status

        at = moment or datetime.now(UTC)
        if (
            self.withdrawn_at is not None
            and _as_comparable(at, self.withdrawn_at) >= self.withdrawn_at
        ):
            return ConsentStatus.WITHDRAWN

        _, effective_to = self.effective_window
        if effective_to is not None and _as_comparable(at, effective_to) >= effective_to:
            return ConsentStatus.EXPIRED
        return ConsentStatus.GRANTED

    def is_active_at(self, moment: datetime | None = None) -> bool:
        at = moment or datetime.now(UTC)
        effective_from, effective_to = self.effective_window
        if _as_comparable(at, effective_from) < effective_from:
            return False
        if effective_to is not None and _as_comparable(at, effective_to) >= effective_to:
            return False
        return self.status_at(at) is ConsentStatus.GRANTED

    def matches_scope(
        self,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: ConsentPurpose | str,
    ) -> bool:
        return (
            self.tenant_id == tenant_id
            and self.family_id == family_id
            and self.subject_person_id == subject_person_id
            and self.purpose is _coerce_purpose(purpose)
        )

    def is_active_for(
        self,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: ConsentPurpose | str,
        moment: datetime | None = None,
    ) -> bool:
        return self.matches_scope(
            tenant_id=tenant_id,
            family_id=family_id,
            subject_person_id=subject_person_id,
            purpose=purpose,
        ) and self.is_active_at(moment)

    @property
    def is_active(self) -> bool:
        return self.is_active_at()


_CANONICAL_GRANT_FIELDS = frozenset(field.name for field in fields(ConsentGrant))
_HAS_SCOPED_CANONICAL_GRANT = {
    "tenant_id",
    "family_id",
    "effective_from",
    "effective_to",
    "withdrawn_at",
    "expires_at",
}.issubset(_CANONICAL_GRANT_FIELDS)


def _coerce_purpose(value: ConsentPurpose | str) -> ConsentPurpose:
    if isinstance(value, ConsentPurpose):
        return value
    if not isinstance(value, str):
        raise TypeError("consent purpose must be a ConsentPurpose or string")
    try:
        return ConsentPurpose(value)
    except ValueError:
        try:
            return ConsentPurpose[value.upper()]
        except KeyError as exc:
            raise ValueError(f"unknown consent purpose: {value}") from exc


def _coerce_status(value: ConsentStatus | str) -> ConsentStatus:
    if isinstance(value, ConsentStatus):
        return value
    if not isinstance(value, str):
        raise TypeError("consent status must be a ConsentStatus or string")
    try:
        return ConsentStatus(value)
    except ValueError:
        try:
            return ConsentStatus[value.upper()]
        except KeyError as exc:
            raise ValueError(f"unknown consent status: {value}") from exc


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _as_comparable(value: datetime, reference: datetime) -> datetime:
    """Use the canonical model's naive/aware comparison convention."""

    if _is_aware(reference):
        if not _is_aware(value):
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if _is_aware(value):
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


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
    """Fake consent store with the canonical scope and status/time predicate."""

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self.grants: list[FakeConsentRecord | ConsentGrant] = []
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
        scope: GrowthOnboardingScope | object | None = None,
        subject_person_id: str | None = None,
        purpose: ConsentPurpose | str | None = None,
        *,
        tenant_id: str | None = None,
        family_id: str | None = None,
        consent_id: str | None = None,
        guardian_person_id: str | None = None,
        guardian_relation: Any = None,
        subject_age: Any = None,
        status: ConsentStatus | str = ConsentStatus.GRANTED,
        granted_at: datetime | None = None,
        effective_from: datetime | None = None,
        effective_to: datetime | None = None,
        withdrawn_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> FakeConsentRecord | ConsentGrant:
        if scope is not None and not isinstance(scope, GrowthOnboardingScope):
            if (
                any(
                    value is not None
                    for value in (
                        subject_person_id,
                        purpose,
                        tenant_id,
                        family_id,
                        consent_id,
                        guardian_person_id,
                        guardian_relation,
                        subject_age,
                        effective_from,
                        effective_to,
                        withdrawn_at,
                        expires_at,
                    )
                )
                or status is not ConsentStatus.GRANTED
            ):
                raise TypeError("canonical consent object cannot be combined with grant fields")
            record = self._record_from_canonical(scope)
            self._ensure_binding(record.tenant_id, record.family_id)
            self.grants.append(record)
            return record

        if isinstance(scope, GrowthOnboardingScope):
            if tenant_id is not None and tenant_id != scope.tenant_id:
                raise ValueError("consent tenant_id conflicts with scope")
            if family_id is not None and family_id != scope.family_id:
                raise ValueError("consent family_id conflicts with scope")
            tenant_id = scope.tenant_id
            family_id = scope.family_id
            guardian_person_id = guardian_person_id or scope.actor_id

        if not tenant_id or not family_id:
            raise ValueError("tenant_id and family_id are required for a consent grant")
        if not subject_person_id or purpose is None:
            raise ValueError("subject_person_id and purpose are required for a consent grant")

        recorded_at = granted_at or self._now()
        record_values = dict(
            consent_id=consent_id
            or str(
                uuid5(
                    NAMESPACE_URL,
                    f"growth-consent:{tenant_id}:{family_id}:{subject_person_id}:"
                    f"{_coerce_purpose(purpose).value}:{len(self.grants)}",
                )
            ),
            subject_person_id=subject_person_id,
            guardian_person_id=guardian_person_id or "fake-guardian",
            purpose=_coerce_purpose(purpose),
            status=_coerce_status(status),
            granted_at=recorded_at,
            tenant_id=tenant_id,
            family_id=family_id,
            guardian_relation=guardian_relation,
            subject_age=subject_age,
            effective_from=effective_from,
            effective_to=effective_to,
            withdrawn_at=withdrawn_at,
            expires_at=expires_at,
        )
        record = (
            ConsentGrant(**record_values)
            if _HAS_SCOPED_CANONICAL_GRANT
            else FakeConsentRecord(**record_values)
        )

        self._ensure_binding(tenant_id, family_id)
        self.grants.append(record)
        return record

    def _record_from_canonical(self, grant: object) -> FakeConsentRecord | ConsentGrant:
        if _HAS_SCOPED_CANONICAL_GRANT and isinstance(grant, ConsentGrant):
            return grant
        return FakeConsentRecord(
            consent_id=str(grant.consent_id),
            subject_person_id=str(grant.subject_person_id),
            guardian_person_id=str(grant.guardian_person_id),
            purpose=grant.purpose,
            status=grant.status,
            granted_at=grant.granted_at,
            tenant_id=getattr(grant, "tenant_id", None),
            family_id=getattr(grant, "family_id", None),
            guardian_relation=getattr(grant, "guardian_relation", None),
            subject_age=getattr(grant, "subject_age", None),
            effective_from=getattr(grant, "effective_from", None),
            effective_to=getattr(grant, "effective_to", None),
            withdrawn_at=getattr(grant, "withdrawn_at", None),
            expires_at=getattr(grant, "expires_at", None),
        )

    def _ensure_binding(self, tenant_id: str | None, family_id: str | None) -> None:
        if tenant_id is None or family_id is None:
            return
        self.bindings.setdefault(
            (tenant_id, family_id),
            FakeTenantFamilyBinding(
                tenant_id=tenant_id,
                family_id=family_id,
                status="ACTIVE",
                effective_from=self._now(),
            ),
        )

    def query(
        self,
        scope: GrowthOnboardingScope | None = None,
        subject_person_id: str | None = None,
        purpose: ConsentPurpose | str | None = None,
        *,
        tenant_id: str | None = None,
        family_id: str | None = None,
        moment: datetime | None = None,
        active_only: bool = False,
    ) -> list[FakeConsentRecord | ConsentGrant]:
        """Return the exact tenant/family grant rows, including deny rows.

        ``active_only`` is opt-in so callers can inspect withdrawn/expired
        records as canonical ``ConsentGate`` inputs.  No query without both
        scope components can return a grant.
        """

        if scope is not None and not isinstance(scope, GrowthOnboardingScope):
            tenant_id = getattr(scope, "tenant_id", None)
            family_id = getattr(scope, "family_id", None)
            subject_person_id = getattr(scope, "subject_person_id", None)
            purpose = getattr(scope, "purpose", None)
        elif scope is not None:
            if tenant_id is not None and tenant_id != scope.tenant_id:
                return []
            if family_id is not None and family_id != scope.family_id:
                return []
            tenant_id = scope.tenant_id
            family_id = scope.family_id
        if not tenant_id or not family_id:
            return []

        try:
            requested_purpose = None if purpose is None else _coerce_purpose(purpose)
        except (TypeError, ValueError):
            return []
        active_moment = moment or self._now()
        return [
            record
            for record in self.grants
            if (
                record.tenant_id == tenant_id
                and record.family_id == family_id
                and (subject_person_id is None or record.subject_person_id == subject_person_id)
                and (requested_purpose is None or record.purpose is requested_purpose)
                and (not active_only or record.is_active_at(active_moment))
            )
        ]

    async def list_grants(
        self,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: ConsentPurpose | str,
    ) -> tuple[FakeConsentRecord | ConsentGrant, ...]:
        """Expose the canonical async query shape for integration wiring."""

        return tuple(
            self.query(
                tenant_id=tenant_id,
                family_id=family_id,
                subject_person_id=subject_person_id,
                purpose=purpose,
            )
        )

    def revoke(
        self,
        scope: GrowthOnboardingScope | str | None = None,
        subject_person_id: str | None = None,
        purpose: ConsentPurpose | str | None = None,
        *,
        consent_id: str | None = None,
        tenant_id: str | None = None,
        family_id: str | None = None,
        withdrawn_at: datetime | None = None,
    ) -> int:
        """Withdraw exact scoped rows and return the number changed."""

        if isinstance(scope, str) and consent_id is None:
            consent_id = scope
            scope = None
        elif scope is not None and not isinstance(scope, GrowthOnboardingScope):
            consent_id = consent_id or getattr(scope, "consent_id", None)
            tenant_id = tenant_id or getattr(scope, "tenant_id", None)
            family_id = family_id or getattr(scope, "family_id", None)
            subject_person_id = subject_person_id or getattr(scope, "subject_person_id", None)
            purpose = purpose or getattr(scope, "purpose", None)
            scope = None
        if scope is not None:
            if tenant_id is not None and tenant_id != scope.tenant_id:
                return 0
            if family_id is not None and family_id != scope.family_id:
                return 0
            tenant_id = scope.tenant_id
            family_id = scope.family_id
        if not consent_id and (not tenant_id or not family_id):
            return 0
        if consent_id and tenant_id is None and family_id is None:
            matching_scopes = {
                (record.tenant_id, record.family_id)
                for record in self.grants
                if record.consent_id == consent_id
            }
            if len(matching_scopes) > 1:
                return 0
        try:
            requested_purpose = None if purpose is None else _coerce_purpose(purpose)
        except (TypeError, ValueError):
            return 0
        withdrawal_time = withdrawn_at or self._now()
        changed = 0
        updated: list[FakeConsentRecord | ConsentGrant] = []
        for record in self.grants:
            matches = (
                (consent_id is None or record.consent_id == consent_id)
                and (tenant_id is None or record.tenant_id == tenant_id)
                and (family_id is None or record.family_id == family_id)
                and (subject_person_id is None or record.subject_person_id == subject_person_id)
                and (requested_purpose is None or record.purpose is requested_purpose)
            )
            if matches:
                updated.append(
                    replace(
                        record,
                        status=ConsentStatus.WITHDRAWN,
                        withdrawn_at=withdrawal_time,
                    )
                )
                changed += 1
            else:
                updated.append(record)
        self.grants = updated
        return changed

    def withdraw(
        self,
        scope: GrowthOnboardingScope | str | None = None,
        subject_person_id: str | None = None,
        purpose: ConsentPurpose | str | None = None,
        **kwargs: Any,
    ) -> int:
        return self.revoke(scope, subject_person_id, purpose, **kwargs)

    def expire(self, scope: GrowthOnboardingScope, subject_person_id: str, purpose: str) -> int:
        return self._replace_status(scope, subject_person_id, purpose, ConsentStatus.EXPIRED)

    def _replace_status(
        self,
        scope: GrowthOnboardingScope,
        subject_person_id: str,
        purpose: ConsentPurpose | str,
        status: ConsentStatus,
    ) -> int:
        try:
            requested_purpose = _coerce_purpose(purpose)
        except (TypeError, ValueError):
            return 0
        changed = 0
        updated: list[FakeConsentRecord | ConsentGrant] = []
        for record in self.grants:
            matches = (
                record.tenant_id == scope.tenant_id
                and record.family_id == scope.family_id
                and record.subject_person_id == subject_person_id
                and record.purpose is requested_purpose
                and not (
                    status is ConsentStatus.EXPIRED
                    and (
                        record.status is ConsentStatus.WITHDRAWN or record.withdrawn_at is not None
                    )
                )
            )
            if matches:
                updated.append(replace(record, status=status))
                changed += 1
            else:
                updated.append(record)
        self.grants = updated
        return changed

    async def assert_granted(
        self,
        scope: GrowthOnboardingScope,
        subject_person_id: str,
        purpose: str,
    ) -> None:
        moment = self._now()
        try:
            requested_purpose = _coerce_purpose(purpose)
        except (TypeError, ValueError) as exc:
            raise GrowthOnboardingForbiddenError(f"missing_consent:{purpose}") from exc
        binding = self.bindings.get((scope.tenant_id, scope.family_id))
        binding_active = self._binding_is_active(binding, moment)
        active = any(
            binding_active
            and record.is_active_for(
                tenant_id=scope.tenant_id,
                family_id=scope.family_id,
                subject_person_id=subject_person_id,
                purpose=requested_purpose,
                moment=moment,
            )
            for record in self.grants
        )
        if not active:
            raise GrowthOnboardingForbiddenError(f"missing_consent:{purpose}")

    @staticmethod
    def _binding_is_active(binding: FakeTenantFamilyBinding | None, moment: datetime) -> bool:
        return binding is not None and (
            binding.status == "ACTIVE"
            and _as_comparable(moment, binding.effective_from) >= binding.effective_from
            and (
                binding.effective_to is None
                or _as_comparable(moment, binding.effective_to) < binding.effective_to
            )
        )


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
