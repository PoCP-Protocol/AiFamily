"""AI-generated engagement candidates for the Web experience loop.

This module is a deliberately small application seam.  It accepts an explicit
authorization envelope and append-only :class:`ExperienceEvent` objects, then
asks the sole Model Gateway for a structured draft.  It never publishes a
decision, creates an achievement, or mutates a business domain.

The model may suggest pacing, immediate feedback, a growth narrative, a
difficulty adjustment, and an achievement candidate.  Every achievement
candidate must cite one of the supplied event ids; an event reference is
evidence, not a claim that a business milestone was completed.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from backend.intelligence.experience.contracts import (
    ExperienceContractError,
    ExperienceEvent,
    ExperienceScope,
    assert_scope_compatible,
)
from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest
from backend.intelligence.model_gateway.gateway import ModelGateway


class EngagementContractError(ValueError):
    """Raised when an engagement request or model draft is unsafe."""


@dataclass(frozen=True, slots=True)
class EngagementAuthorization:
    """Authorization context carried with one engagement generation request."""

    scope: ExperienceScope
    authorization_ref: str
    actor_id: str
    authorized_event_ids: tuple[str, ...]
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.authorization_ref or not self.actor_id:
            raise EngagementContractError("AUTHORIZATION_REF_AND_ACTOR_REQUIRED")
        if not self.scope.consent_granted:
            raise EngagementContractError("CONSENT_REQUIRED")
        if not self.authorized_event_ids or any(
            not event_id for event_id in self.authorized_event_ids
        ):
            raise EngagementContractError("AUTHORIZED_EVENT_IDS_REQUIRED")
        if len(set(self.authorized_event_ids)) != len(self.authorized_event_ids):
            raise EngagementContractError("AUTHORIZED_EVENT_IDS_MUST_BE_UNIQUE")
        if self.expires_at is not None and self.expires_at <= datetime.now(UTC):
            raise EngagementContractError("AUTHORIZATION_EXPIRED")

    def assert_active(self, *, now: datetime | None = None) -> None:
        """Re-check consent and expiry immediately before model invocation."""

        if not self.scope.consent_granted:
            raise EngagementContractError("CONSENT_REQUIRED")
        reference = now or datetime.now(UTC)
        if reference.tzinfo is None or reference.utcoffset() is None:
            raise EngagementContractError("AUTHORIZATION_CLOCK_TIMEZONE_REQUIRED")
        if self.expires_at is not None and self.expires_at <= reference:
            raise EngagementContractError("AUTHORIZATION_EXPIRED")


@dataclass(frozen=True, slots=True)
class EngagementDraftCommand:
    """Inputs for one AI engagement draft; events are supplied as real objects."""

    request_id: str
    provider_id: str
    authorization: EngagementAuthorization
    events: tuple[ExperienceEvent, ...]
    context_snapshot_ref: str
    prompt_version: str = "engagement.v1"
    schema_version: str = "engagement-draft.v1"
    use_case: str = "family-engagement-draft"
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = (
            self.request_id,
            self.provider_id,
            self.context_snapshot_ref,
            self.prompt_version,
            self.schema_version,
            self.use_case,
        )
        if not all(required):
            raise EngagementContractError("ENGAGEMENT_REQUEST_FIELDS_REQUIRED")
        if not self.events:
            raise EngagementContractError("EXPERIENCE_EVENTS_REQUIRED")
        if any(not isinstance(event, ExperienceEvent) for event in self.events):
            raise EngagementContractError("EXPERIENCE_EVENT_REFERENCES_REQUIRED")
        event_ids = tuple(event.event_id for event in self.events)
        if len(set(event_ids)) != len(event_ids):
            raise EngagementContractError("EXPERIENCE_EVENT_IDS_MUST_BE_UNIQUE")
        authorized = set(self.authorization.authorized_event_ids)
        if not set(event_ids).issubset(authorized):
            raise EngagementContractError("EVENT_NOT_AUTHORIZED")
        for event in self.events:
            try:
                assert_scope_compatible(self.authorization.scope, event)
            except ExperienceContractError as exc:
                raise EngagementContractError(f"EVENT_SCOPE_NOT_AUTHORIZED:{exc}") from exc

    def to_structured_request(self) -> StructuredRequest:
        """Build a provider-neutral request with event evidence references."""

        event_payload = tuple(
            {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "node": event.node.value,
                "occurred_at": event.occurred_at.isoformat(),
                "payload": dict(event.payload),
                "evidence_ref": f"experience-event:{event.event_id}",
            }
            for event in self.events
        )
        request_payload = {
            "authorization_ref": self.authorization.authorization_ref,
            "actor_id": self.authorization.actor_id,
            "scope": {
                "tenant_id": self.authorization.scope.tenant_id,
                "family_id": self.authorization.scope.family_id,
                "subject_ids": self.authorization.scope.subject_ids,
                "purpose": self.authorization.scope.purpose,
                "consent_version": self.authorization.scope.consent_version,
            },
            "events": event_payload,
            "context": dict(self.payload),
        }
        return StructuredRequest(
            use_case=self.use_case,
            prompt_version=self.prompt_version,
            schema_version=self.schema_version,
            data_class=self.authorization.scope.data_class,
            payload=request_payload,
            output_schema=ENGAGEMENT_DRAFT_SCHEMA,
            context_snapshot_ref=self.context_snapshot_ref,
            input_refs=tuple(event.event_id for event in self.events),
            request_id=self.request_id,
        )


CandidateKind = Literal[
    "pacing",
    "instant_feedback",
    "growth_narrative",
    "difficulty_adjustment",
    "achievement",
]


@dataclass(frozen=True, slots=True)
class EngagementDraft:
    """Validated DRAFT-only engagement output for Web rendering."""

    request_id: str
    draft: ModelDraft
    evidence_event_ids: tuple[str, ...]
    scope: ExperienceScope | None = None
    draft_id: str | None = None

    def __post_init__(self) -> None:
        if self.draft.status != "DRAFT":
            raise EngagementContractError("ENGAGEMENT_DRAFT_STATUS_MUST_REMAIN_DRAFT")
        if self.draft.may_mutate_business_state:
            raise EngagementContractError("ENGAGEMENT_DRAFT_MUTATION_FORBIDDEN")
        if self.draft_id is not None and (
            not isinstance(self.draft_id, str) or not self.draft_id.strip()
        ):
            raise EngagementContractError("ENGAGEMENT_DRAFT_ID_INVALID")
        if not self.evidence_event_ids:
            raise EngagementContractError("ENGAGEMENT_EVIDENCE_REQUIRED")
        _validate_output(self.draft.output, set(self.evidence_event_ids))

    @property
    def output(self) -> dict[str, Any]:
        return self.draft.output

    @property
    def pacing(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.output["pacing"])

    @property
    def instant_feedback(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.output["instant_feedback"])

    @property
    def growth_narrative(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.output["growth_narrative"])

    @property
    def difficulty_adjustment(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.output["difficulty_adjustment"])

    @property
    def achievement_candidates(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.output["achievement_candidates"])


class EngagementDraftService:
    """Generate engagement candidates through the sole Model Gateway."""

    def __init__(
        self, gateway: ModelGateway, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._gateway = gateway
        self._clock = clock or (lambda: datetime.now(UTC))

    async def generate_draft(self, command: EngagementDraftCommand) -> EngagementDraft:
        command.authorization.assert_active(now=self._clock())
        draft = await self._gateway.generate_structured(
            command.to_structured_request(),
            provider_id=command.provider_id,
        )
        return EngagementDraft(
            request_id=command.request_id,
            draft=draft,
            evidence_event_ids=tuple(event.event_id for event in command.events),
            scope=command.authorization.scope,
        )


class EngagementEventReader(Protocol):
    """Server-owned read port for scope-authorized experience events."""

    def read(
        self, *, scope: ExperienceScope, event_ids: tuple[str, ...]
    ) -> tuple[ExperienceEvent, ...] | Awaitable[tuple[ExperienceEvent, ...]]: ...


class EngagementDraftApplication:
    """Build an engagement draft from events loaded by a trusted read port.

    The application boundary accepts event identifiers, never client-created
    ``ExperienceEvent`` objects.  The injected reader owns tenant/family and
    deletion filtering; this class verifies that it returned exactly the
    requested set before constructing the Model Gateway command.
    """

    def __init__(
        self,
        service: EngagementDraftService,
        event_reader: EngagementEventReader,
    ) -> None:
        if not isinstance(service, EngagementDraftService):
            raise TypeError("service must be an EngagementDraftService")
        if not callable(getattr(event_reader, "read", None)):
            raise TypeError("event_reader must implement read(scope, event_ids)")
        self._service = service
        self._event_reader = event_reader

    async def generate_draft(
        self,
        *,
        request_id: str,
        provider_id: str,
        scope: ExperienceScope,
        actor_id: str,
        authorization_ref: str,
        event_ids: tuple[str, ...],
        context_snapshot_ref: str,
        payload: Mapping[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> EngagementDraft:
        if not event_ids or any(
            not isinstance(event_id, str) or not event_id.strip() for event_id in event_ids
        ):
            raise EngagementContractError("EXPERIENCE_EVENT_IDS_REQUIRED")
        if len(set(event_ids)) != len(event_ids):
            raise EngagementContractError("EXPERIENCE_EVENT_IDS_MUST_BE_UNIQUE")
        loaded = self._event_reader.read(scope=scope, event_ids=event_ids)
        events = await loaded if inspect.isawaitable(loaded) else loaded
        if not isinstance(events, tuple) or any(
            not isinstance(event, ExperienceEvent) for event in events
        ):
            raise EngagementContractError("EXPERIENCE_EVENT_READER_INVALID")
        by_id = {event.event_id: event for event in events}
        if set(by_id) != set(event_ids):
            raise EngagementContractError("EXPERIENCE_EVENTS_NOT_FOUND")
        command = EngagementDraftCommand(
            request_id=request_id,
            provider_id=provider_id,
            authorization=EngagementAuthorization(
                scope=scope,
                authorization_ref=authorization_ref,
                actor_id=actor_id,
                authorized_event_ids=event_ids,
                expires_at=expires_at,
            ),
            events=tuple(by_id[event_id] for event_id in event_ids),
            context_snapshot_ref=context_snapshot_ref,
            payload=dict(payload or {}),
        )
        return await self._service.generate_draft(command)


ENGAGEMENT_DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "pacing",
        "instant_feedback",
        "growth_narrative",
        "difficulty_adjustment",
        "achievement_candidates",
    ],
    "properties": {
        key: {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["candidate_id", "text"],
                "properties": {
                    "candidate_id": {"type": "string", "minLength": 1},
                    "text": {"type": "string", "minLength": 1},
                    "evidence_refs": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "additionalProperties": False,
            },
        }
        for key in (
            "pacing",
            "instant_feedback",
            "growth_narrative",
            "difficulty_adjustment",
            "achievement_candidates",
        )
    },
    "additionalProperties": False,
}

_FORBIDDEN_KEYS = {
    "family_score",
    "family_rank",
    "ranking",
    "score",
    "rank",
    "completed",
    "completion_status",
    "authoritative_fact",
    "canonical_state",
}


def _validate_output(output: Mapping[str, Any], event_ids: set[str]) -> None:
    if set(output) != set(ENGAGEMENT_DRAFT_SCHEMA["required"]):
        raise EngagementContractError("ENGAGEMENT_OUTPUT_SHAPE_INVALID")
    _reject_forbidden_keys(output)
    for candidate in output["achievement_candidates"]:
        refs = candidate.get("evidence_refs", ())
        if not refs:
            raise EngagementContractError("ACHIEVEMENT_EVIDENCE_REQUIRED")
        normalized = {ref.removeprefix("experience-event:") for ref in refs if isinstance(ref, str)}
        if not normalized or not normalized.issubset(event_ids):
            raise EngagementContractError("ACHIEVEMENT_EVIDENCE_NOT_REAL_EVENT")


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        if _FORBIDDEN_KEYS.intersection(value):
            raise EngagementContractError("ENGAGEMENT_OUTPUT_FORBIDDEN_FACT_OR_RANKING")
        for nested in value.values():
            _reject_forbidden_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_forbidden_keys(nested)


__all__ = [
    "CandidateKind",
    "ENGAGEMENT_DRAFT_SCHEMA",
    "EngagementAuthorization",
    "EngagementContractError",
    "EngagementDraft",
    "EngagementDraftCommand",
    "EngagementDraftApplication",
    "EngagementDraftService",
    "EngagementEventReader",
]
