"""Canonical dependency references required before opening an FGCN case.

FGCN does not own GrowthIntent, Consent, FamilyRequest, ActionRecord, or
Observation facts. The entry query returns immutable references to those
canonical facts; this boundary verifies their scope, lifecycle, version,
locale, and expiry without treating a copied counter as the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from backend.domains.service.domain.errors import ServiceForbiddenError, ServiceValidationError

from .contracts import GateServiceScope

_CONFIRMED_GROWTH_INTENT_STATUS = "CONFIRMED"
_ACTIVE_CONSENT_STATUS = "ACTIVE"
_ACTIVE_BINDING_STATUS = "ACTIVE"
_ACTIVE_FAMILY_REQUEST_STATUSES = frozenset({"ACTIVE", "OPEN", "REQUESTED"})
_VALID_ACTION_STATUSES = frozenset({"COMPLETED", "FAILED", "PARTIAL"})
_VALID_OBSERVATION_STATUSES = frozenset({"RECORDED", "CONFIRMED", "ACTIVE"})
_SUPPORTED_LOCALES = frozenset({"en", "zh", "fr"})


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceValidationError(f"fgcn_case_entry_{field_name}_required")
    return value.strip()


def _status(value: object, field_name: str) -> str:
    return _required_text(value, field_name).upper()


def _version(value: object, field_name: str) -> int:
    if type(value) is not int or value < 1:
        raise ServiceValidationError(f"fgcn_case_entry_{field_name}_invalid")
    return value


def _locale(value: object, field_name: str) -> str:
    normalized = _required_text(value, field_name).casefold()
    if normalized not in _SUPPORTED_LOCALES:
        raise ServiceValidationError(f"fgcn_case_entry_{field_name}_unsupported")
    return normalized


def _aware_or_none(value: datetime | None, field_name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ServiceValidationError(f"fgcn_case_entry_{field_name}_must_be_timezone_aware")


@dataclass(frozen=True, slots=True)
class FamilyRequestRef:
    """A canonical, versioned family-initiated request reference."""

    ref: str
    tenant_id: str
    family_id: str
    intent_ref: str
    status: str
    version: int
    locale: str
    initiated_by: str = "FAMILY"
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.ref, "family_request_ref"),
            (self.tenant_id, "family_request_tenant_id"),
            (self.family_id, "family_request_family_id"),
            (self.intent_ref, "family_request_intent_ref"),
        ):
            object.__setattr__(
                self, name.removeprefix("family_request_"), _required_text(value, name)
            )
        object.__setattr__(self, "status", _status(self.status, "family_request_status"))
        object.__setattr__(self, "version", _version(self.version, "family_request_version"))
        object.__setattr__(self, "locale", _locale(self.locale, "family_request_locale"))
        object.__setattr__(
            self, "initiated_by", _status(self.initiated_by, "family_request_initiator")
        )
        if self.initiated_by != "FAMILY":
            raise ServiceForbiddenError("fgcn_family_request_must_be_family_initiated")
        _aware_or_none(self.expires_at, "family_request_expiry")


@dataclass(frozen=True, slots=True)
class ActionRecordRef:
    """A canonical self-help ActionRecord reference and its outcome."""

    ref: str
    family_request_ref: str
    tenant_id: str
    family_id: str
    intent_ref: str
    action_type: str
    outcome: str
    status: str
    version: int
    locale: str
    observation_refs: tuple[str, ...]
    occurred_at: datetime
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.ref, "action_ref"),
            (self.family_request_ref, "action_family_request_ref"),
            (self.tenant_id, "action_tenant_id"),
            (self.family_id, "action_family_id"),
            (self.intent_ref, "action_intent_ref"),
            (self.action_type, "action_type"),
            (self.outcome, "action_outcome"),
        ):
            _required_text(value, name)
        object.__setattr__(self, "action_type", self.action_type.strip().upper())
        object.__setattr__(self, "outcome", self.outcome.strip().upper())
        object.__setattr__(self, "status", _status(self.status, "action_status"))
        object.__setattr__(self, "version", _version(self.version, "action_version"))
        object.__setattr__(self, "locale", _locale(self.locale, "action_locale"))
        if not isinstance(self.observation_refs, tuple) or not self.observation_refs:
            raise ServiceValidationError("fgcn_case_entry_action_observations_required")
        refs = tuple(_required_text(ref, "action_observation_ref") for ref in self.observation_refs)
        if len(refs) != len(set(refs)):
            raise ServiceValidationError("fgcn_case_entry_action_observations_duplicate")
        object.__setattr__(self, "observation_refs", refs)
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ServiceValidationError(
                "fgcn_case_entry_action_occurred_at_must_be_timezone_aware"
            )
        _aware_or_none(self.expires_at, "action_expiry")


@dataclass(frozen=True, slots=True)
class ObservationRef:
    """A canonical, versioned observation attached to one ActionRecord."""

    ref: str
    action_ref: str
    family_request_ref: str
    tenant_id: str
    family_id: str
    intent_ref: str
    kind: str
    value: str
    status: str
    version: int
    locale: str
    observed_at: datetime
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.ref, "observation_ref"),
            (self.action_ref, "observation_action_ref"),
            (self.family_request_ref, "observation_family_request_ref"),
            (self.tenant_id, "observation_tenant_id"),
            (self.family_id, "observation_family_id"),
            (self.intent_ref, "observation_intent_ref"),
            (self.kind, "observation_kind"),
            (self.value, "observation_value"),
        ):
            _required_text(value, name)
        object.__setattr__(self, "kind", self.kind.strip().upper())
        object.__setattr__(self, "value", self.value.strip().upper())
        object.__setattr__(self, "status", _status(self.status, "observation_status"))
        object.__setattr__(self, "version", _version(self.version, "observation_version"))
        object.__setattr__(self, "locale", _locale(self.locale, "observation_locale"))
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ServiceValidationError("fgcn_case_entry_observed_at_must_be_timezone_aware")
        _aware_or_none(self.expires_at, "observation_expiry")


# Longer aliases make the boundary readable to adapters while keeping the
# compact Ref names convenient for query implementations.
FamilyRequestReference = FamilyRequestRef
ActionRecordReference = ActionRecordRef
ObservationReference = ObservationRef


@dataclass(frozen=True, slots=True)
class CaseEntryDependencySnapshot:
    """Read-only canonical evidence required before a new ServiceCase write."""

    intent_ref: str
    growth_intent_status: str
    consent_subject_person_id: str
    consent_purpose: str
    consent_version: str
    consent_status: str
    binding_tenant_id: str
    binding_family_id: str
    binding_status: str
    family_request: FamilyRequestRef
    self_help_actions: tuple[ActionRecordRef, ...]
    self_help_observations: tuple[ObservationRef, ...]
    locale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_ref", _required_text(self.intent_ref, "intent_ref"))
        object.__setattr__(
            self, "growth_intent_status", _status(self.growth_intent_status, "growth_intent_status")
        )
        object.__setattr__(
            self,
            "consent_subject_person_id",
            _required_text(self.consent_subject_person_id, "consent_subject_person_id"),
        )
        object.__setattr__(
            self, "consent_purpose", _required_text(self.consent_purpose, "consent_purpose")
        )
        object.__setattr__(
            self, "consent_version", _required_text(self.consent_version, "consent_version")
        )
        object.__setattr__(self, "consent_status", _status(self.consent_status, "consent_status"))
        object.__setattr__(
            self, "binding_tenant_id", _required_text(self.binding_tenant_id, "binding_tenant_id")
        )
        object.__setattr__(
            self, "binding_family_id", _required_text(self.binding_family_id, "binding_family_id")
        )
        object.__setattr__(self, "binding_status", _status(self.binding_status, "binding_status"))
        if not isinstance(self.family_request, FamilyRequestRef):
            raise ServiceValidationError("fgcn_case_entry_family_request_invalid")
        if not isinstance(self.self_help_actions, tuple) or not self.self_help_actions:
            raise ServiceValidationError("fgcn_case_entry_actions_required")
        if not isinstance(self.self_help_observations, tuple) or not self.self_help_observations:
            raise ServiceValidationError("fgcn_case_entry_observations_required")
        if not all(isinstance(item, ActionRecordRef) for item in self.self_help_actions):
            raise ServiceValidationError("fgcn_case_entry_actions_invalid")
        if not all(isinstance(item, ObservationRef) for item in self.self_help_observations):
            raise ServiceValidationError("fgcn_case_entry_observations_invalid")
        if not isinstance(self.locale, str) or not self.locale.strip():
            raise ServiceValidationError("fgcn_case_entry_locale_required")
        object.__setattr__(self, "locale", _locale(self.locale, "locale"))

    @property
    def family_request_ref(self) -> str:
        """The canonical request identifier, derived from the typed ref."""

        return self.family_request.ref

    @property
    def self_help_action_refs(self) -> tuple[str, ...]:
        return tuple(action.ref for action in self.self_help_actions)

    @property
    def self_help_observation_refs(self) -> tuple[str, ...]:
        return tuple(observation.ref for observation in self.self_help_observations)


class CaseEntryDependencyQuery(Protocol):
    """Synchronous query port used by the in-memory FGCN engine."""

    def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> CaseEntryDependencySnapshot | None: ...


class AsyncCaseEntryDependencyQuery(Protocol):
    """Async query port used by the durable FGCN opening command."""

    async def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> CaseEntryDependencySnapshot | None: ...


class RejectingCaseEntryDependencyQuery:
    """Safe default when upstream canonical stores are not wired."""

    def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> None:
        return None


class AsyncRejectingCaseEntryDependencyQuery:
    """Safe durable default when the dependency boundary is not wired."""

    async def resolve(
        self,
        *,
        scope: GateServiceScope,
        intent_ref: str,
    ) -> None:
        return None


DEFAULT_CASE_ENTRY_DEPENDENCIES = RejectingCaseEntryDependencyQuery()
DEFAULT_ASYNC_CASE_ENTRY_DEPENDENCIES = AsyncRejectingCaseEntryDependencyQuery()


def _assert_live(
    *,
    status: str,
    accepted: frozenset[str],
    expires_at: datetime | None,
    as_of: datetime,
    expired_code: str,
    revoked_code: str,
    invalid_code: str,
) -> None:
    if status in {"REVOKED", "WITHDRAWN"}:
        raise ServiceForbiddenError(revoked_code)
    if status in {"DELETED", "EXPIRED"} or (expires_at is not None and expires_at <= as_of):
        raise ServiceForbiddenError(expired_code)
    if status not in accepted:
        raise ServiceForbiddenError(invalid_code)


def assert_case_entry_dependencies(
    snapshot: CaseEntryDependencySnapshot | None,
    *,
    scope: GateServiceScope,
    intent_ref: str,
    as_of: datetime | None = None,
) -> CaseEntryDependencySnapshot:
    """Enforce exact canonical relations before creating a ServiceCase."""

    if not isinstance(snapshot, CaseEntryDependencySnapshot):
        raise ServiceForbiddenError("fgcn_case_entry_dependencies_unavailable")
    if snapshot.intent_ref != intent_ref:
        raise ServiceForbiddenError("fgcn_growth_intent_identity_mismatch")
    if snapshot.growth_intent_status != _CONFIRMED_GROWTH_INTENT_STATUS:
        raise ServiceForbiddenError("fgcn_growth_intent_not_confirmed")
    if snapshot.consent_status != _ACTIVE_CONSENT_STATUS:
        raise ServiceForbiddenError("fgcn_consent_not_active")
    if (
        snapshot.consent_subject_person_id != scope.subject_person_id
        or snapshot.consent_purpose != scope.purpose
        or snapshot.consent_version != scope.consent_version
    ):
        raise ServiceForbiddenError("fgcn_consent_scope_mismatch")
    if (
        snapshot.binding_status != _ACTIVE_BINDING_STATUS
        or snapshot.binding_tenant_id != scope.tenant_id
        or snapshot.binding_family_id != scope.family_id
    ):
        raise ServiceForbiddenError("fgcn_tenant_family_binding_invalid")
    now = as_of or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ServiceValidationError("fgcn_case_entry_as_of_must_be_timezone_aware")

    request = snapshot.family_request
    if request.tenant_id != scope.tenant_id or request.family_id != scope.family_id:
        raise ServiceForbiddenError("fgcn_family_request_scope_mismatch")
    if request.intent_ref != intent_ref:
        raise ServiceForbiddenError("fgcn_family_request_intent_mismatch")
    if request.locale != snapshot.locale:
        raise ServiceForbiddenError("fgcn_case_entry_locale_mismatch")
    _assert_live(
        status=request.status,
        accepted=_ACTIVE_FAMILY_REQUEST_STATUSES,
        expires_at=request.expires_at,
        as_of=now,
        expired_code="fgcn_family_request_expired_or_deleted",
        revoked_code="fgcn_family_request_withdrawn",
        invalid_code="fgcn_family_request_not_active",
    )

    actions = snapshot.self_help_actions
    observations = snapshot.self_help_observations
    if len(actions) < 2 or len(observations) < 2:
        raise ServiceForbiddenError("fgcn_repeated_self_help_evidence_required")
    action_refs = {action.ref for action in actions}
    observation_by_ref = {observation.ref: observation for observation in observations}
    if len(action_refs) != len(actions) or len(observation_by_ref) != len(observations):
        raise ServiceForbiddenError("fgcn_case_entry_duplicate_reference")
    linked_observation_refs: set[str] = set()
    for action in actions:
        if (
            action.family_request_ref != request.ref
            or action.tenant_id != scope.tenant_id
            or action.family_id != scope.family_id
            or action.intent_ref != intent_ref
            or action.version != request.version
            or action.locale != snapshot.locale
            or action.action_type != "SELF_HELP"
            or action.outcome != "FAILED"
        ):
            raise ServiceForbiddenError("fgcn_self_help_action_reference_invalid")
        _assert_live(
            status=action.status,
            accepted=_VALID_ACTION_STATUSES,
            expires_at=action.expires_at,
            as_of=now,
            expired_code="fgcn_self_help_action_expired_or_deleted",
            revoked_code="fgcn_self_help_action_withdrawn",
            invalid_code="fgcn_self_help_action_status_invalid",
        )
        for observation_ref in action.observation_refs:
            linked_observation_refs.add(observation_ref)
            observation = observation_by_ref.get(observation_ref)
            if observation is None:
                raise ServiceForbiddenError("fgcn_self_help_observation_reference_missing")
            if (
                observation.action_ref != action.ref
                or observation.family_request_ref != request.ref
                or observation.tenant_id != scope.tenant_id
                or observation.family_id != scope.family_id
                or observation.intent_ref != intent_ref
                or observation.version != request.version
                or observation.locale != snapshot.locale
                or observation.kind != "SELF_HELP_OUTCOME"
                or observation.value != "FAILED"
            ):
                raise ServiceForbiddenError("fgcn_self_help_observation_reference_invalid")
            _assert_live(
                status=observation.status,
                accepted=_VALID_OBSERVATION_STATUSES,
                expires_at=observation.expires_at,
                as_of=now,
                expired_code="fgcn_self_help_observation_expired_or_deleted",
                revoked_code="fgcn_self_help_observation_withdrawn",
                invalid_code="fgcn_self_help_observation_status_invalid",
            )
    if linked_observation_refs != set(observation_by_ref):
        raise ServiceForbiddenError("fgcn_self_help_observation_reference_unlinked")
    return snapshot


def require_case_entry_dependencies(
    query: CaseEntryDependencyQuery,
    *,
    scope: GateServiceScope,
    intent_ref: str,
    as_of: datetime | None = None,
) -> CaseEntryDependencySnapshot:
    """Resolve and validate entry evidence for the synchronous engine."""

    try:
        snapshot = query.resolve(scope=scope, intent_ref=intent_ref)
    except ServiceForbiddenError:
        raise
    except Exception as exc:
        raise ServiceForbiddenError("fgcn_case_entry_dependencies_unavailable") from exc
    return assert_case_entry_dependencies(snapshot, scope=scope, intent_ref=intent_ref, as_of=as_of)


async def require_case_entry_dependencies_async(
    query: AsyncCaseEntryDependencyQuery,
    *,
    scope: GateServiceScope,
    intent_ref: str,
    as_of: datetime | None = None,
) -> CaseEntryDependencySnapshot:
    """Resolve and validate entry evidence for the durable command."""

    try:
        snapshot = await query.resolve(scope=scope, intent_ref=intent_ref)
    except ServiceForbiddenError:
        raise
    except Exception as exc:
        raise ServiceForbiddenError("fgcn_case_entry_dependencies_unavailable") from exc
    return assert_case_entry_dependencies(snapshot, scope=scope, intent_ref=intent_ref, as_of=as_of)


__all__ = [
    "ActionRecordRef",
    "ActionRecordReference",
    "AsyncCaseEntryDependencyQuery",
    "AsyncRejectingCaseEntryDependencyQuery",
    "CaseEntryDependencyQuery",
    "CaseEntryDependencySnapshot",
    "DEFAULT_ASYNC_CASE_ENTRY_DEPENDENCIES",
    "DEFAULT_CASE_ENTRY_DEPENDENCIES",
    "FamilyRequestRef",
    "FamilyRequestReference",
    "ObservationRef",
    "ObservationReference",
    "RejectingCaseEntryDependencyQuery",
    "assert_case_entry_dependencies",
    "require_case_entry_dependencies",
    "require_case_entry_dependencies_async",
]
