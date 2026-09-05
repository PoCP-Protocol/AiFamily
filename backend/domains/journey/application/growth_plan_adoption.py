"""Family adoption boundary for a validated generative growth-plan draft."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from backend.platform.audit import AuditEvent

from ..domain.errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)

ADOPT_GROWTH_PLAN_ACTION = "AdoptFamilyGrowthPlanDraft"
ADOPTED_PLAN_BOUNDARY = "HUMAN_ADOPTED_GENERATIVE_DRAFT_NOT_AI_CREATED_FACT"


@dataclass(frozen=True, slots=True)
class GrowthPlanActor:
    actor_id: str
    tenant_id: str
    family_id: str
    membership_ref: str
    consent_ref: str
    actor_type: str = "GUARDIAN"


@dataclass(frozen=True, slots=True)
class ValidatedGrowthPlanDraft:
    draft_ref: str
    version: int
    tenant_id: str
    family_id: str
    subject_refs: tuple[str, ...]
    status: str
    model_run_ref: str
    provenance_ref: str
    validation_receipt_ref: str
    validated_by: str
    validated_at: datetime
    content_sha256: str
    output: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class AdoptedGrowthPlan:
    plan_id: str
    tenant_id: str
    family_id: str
    subject_refs: tuple[str, ...]
    draft_ref: str
    draft_version: int
    model_run_ref: str
    provenance_ref: str
    content_sha256: str
    title: str
    family_goal: Mapping[str, Any]
    why_this_plan: str
    duration: Mapping[str, Any]
    stages: tuple[Mapping[str, Any], ...]
    adjustable_choices: tuple[Mapping[str, Any], ...]
    selected_choices: Mapping[str, str]
    unknowns_to_watch: tuple[str, ...]
    review_rhythm: Mapping[str, Any]
    limitations: tuple[str, ...]
    status: str
    adopted_by: str
    adopted_at: datetime
    boundary: str = ADOPTED_PLAN_BOUNDARY

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "subject_refs": list(self.subject_refs),
            "draft_ref": self.draft_ref,
            "draft_version": self.draft_version,
            "model_run_ref": self.model_run_ref,
            "provenance_ref": self.provenance_ref,
            "content_sha256": self.content_sha256,
            "title": self.title,
            "family_goal": dict(self.family_goal),
            "why_this_plan": self.why_this_plan,
            "duration": dict(self.duration),
            "stages": [dict(stage) for stage in self.stages],
            "adjustable_choices": [dict(choice) for choice in self.adjustable_choices],
            "selected_choices": dict(self.selected_choices),
            "unknowns_to_watch": list(self.unknowns_to_watch),
            "review_rhythm": dict(self.review_rhythm),
            "limitations": list(self.limitations),
            "status": self.status,
            "adopted_by": self.adopted_by,
            "adopted_at": self.adopted_at.isoformat(),
            "boundary": self.boundary,
        }


class GrowthPlanDraftReader(Protocol):
    async def load_validated_draft(
        self, *, tenant_id: str, family_id: str, draft_ref: str, version: int
    ) -> ValidatedGrowthPlanDraft | None: ...

    async def load_latest_validated_draft(
        self, *, tenant_id: str, family_id: str
    ) -> ValidatedGrowthPlanDraft | None: ...


class AdoptedGrowthPlanRepository(Protocol):
    async def get_current(self, *, tenant_id: str, family_id: str) -> AdoptedGrowthPlan | None: ...

    async def adopt_once(
        self,
        *,
        plan: AdoptedGrowthPlan,
        idempotency_key: str,
        request_fingerprint: str,
        audit_event: AuditEvent,
    ) -> tuple[AdoptedGrowthPlan, bool, bool]:
        """Persist the plan and the R6 AuditEvent atomically.

        Implementations must write ``audit_event`` in the same atomic unit as
        the plan row (or, for the in-memory dev adapter, into the same
        `AuditRecorder` buffer) so "plan adopted" and "audit event produced"
        cannot diverge. Returns plan, created, idempotency_replayed.
        """


class GrowthPlanAdoptionPolicy(Protocol):
    async def assert_can_read(self, actor: GrowthPlanActor) -> None: ...

    async def assert_can_adopt(
        self, actor: GrowthPlanActor, subject_refs: tuple[str, ...]
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class AdoptGrowthPlanCommand:
    actor: GrowthPlanActor
    draft_ref: str
    draft_version: int
    idempotency_key: str
    selected_choices: Mapping[str, str]
    correlation_id: str


@dataclass(frozen=True, slots=True)
class GrowthPlanAdoptionService:
    draft_reader: GrowthPlanDraftReader
    repository: AdoptedGrowthPlanRepository
    policy: GrowthPlanAdoptionPolicy

    async def adopt(self, command: AdoptGrowthPlanCommand) -> dict[str, Any]:
        _validate_command(command)
        actor = command.actor
        draft = await self.draft_reader.load_validated_draft(
            tenant_id=actor.tenant_id,
            family_id=actor.family_id,
            draft_ref=command.draft_ref,
            version=command.draft_version,
        )
        if draft is None:
            raise JourneyNotFoundError("validated_growth_plan_draft_not_found")
        _validate_draft(draft, actor)
        await self.policy.assert_can_adopt(actor, draft.subject_refs)
        selected_choices = _validate_selected_choices(draft.output, command.selected_choices)

        output = draft.output
        adopted_at = datetime.now(UTC)
        plan = AdoptedGrowthPlan(
            plan_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"adopted-growth-plan:{actor.tenant_id}:{actor.family_id}:"
                    f"{draft.draft_ref}:{draft.version}",
                )
            ),
            tenant_id=actor.tenant_id,
            family_id=actor.family_id,
            subject_refs=draft.subject_refs,
            draft_ref=draft.draft_ref,
            draft_version=draft.version,
            model_run_ref=draft.model_run_ref,
            provenance_ref=draft.provenance_ref,
            content_sha256=draft.content_sha256,
            title=str(output["title"]),
            family_goal=output["family_goal"],
            why_this_plan=str(output["why_this_plan"]),
            duration=output["duration"],
            stages=tuple(output["stages"]),
            adjustable_choices=tuple(output["adjustable_choices"]),
            selected_choices=selected_choices,
            unknowns_to_watch=tuple(output["unknowns_to_watch"]),
            review_rhythm=output["review_rhythm"],
            limitations=tuple(output["limitations"]),
            status="ACTIVE",
            adopted_by=actor.actor_id,
            adopted_at=adopted_at,
        )
        audit_event = AuditEvent(
            actor_id=actor.actor_id,
            tenant_id=actor.tenant_id,
            action=ADOPT_GROWTH_PLAN_ACTION,
            resource_type="AdoptedGrowthPlan",
            resource_id=plan.plan_id,
            reason=f"guardian {actor.actor_id} adopted validated growth-plan draft "
            f"{draft.draft_ref}@{draft.version}",
            correlation_id=command.correlation_id,
            before=None,
            after=plan.as_dict(),
            timestamp=adopted_at,
        )
        stored, created, replayed = await self.repository.adopt_once(
            plan=plan,
            idempotency_key=command.idempotency_key,
            request_fingerprint=_request_fingerprint(command),
            audit_event=audit_event,
        )
        return {
            "plan": stored.as_dict(),
            "created": created,
            "idempotency_replayed": replayed,
            "named_action": ADOPT_GROWTH_PLAN_ACTION,
        }

    async def get_current(self, actor: GrowthPlanActor) -> dict[str, Any]:
        _validate_actor(actor)
        await self.policy.assert_can_read(actor)
        current = await self.repository.get_current(
            tenant_id=actor.tenant_id, family_id=actor.family_id
        )
        if current is not None:
            return {"family_id": actor.family_id, "plan": current.as_dict()}
        draft = await self.draft_reader.load_latest_validated_draft(
            tenant_id=actor.tenant_id, family_id=actor.family_id
        )
        if draft is None:
            return {"family_id": actor.family_id, "plan": None}
        _validate_draft(draft, actor)
        return {
            "family_id": actor.family_id,
            "plan": {
                "draft_ref": draft.draft_ref,
                "draft_version": draft.version,
                "validation_receipt_ref": draft.validation_receipt_ref,
                "provenance_ref": draft.provenance_ref,
                "content_sha256": draft.content_sha256,
                **dict(draft.output),
            },
        }


class GuardianGrowthPlanPolicy:
    async def assert_can_read(self, actor: GrowthPlanActor) -> None:
        _validate_actor(actor)
        if actor.actor_type != "GUARDIAN":
            raise JourneyForbiddenError("growth_plan_read_requires_guardian")

    async def assert_can_adopt(self, actor: GrowthPlanActor, subject_refs: tuple[str, ...]) -> None:
        _validate_actor(actor)
        if actor.actor_type != "GUARDIAN":
            raise JourneyForbiddenError("growth_plan_adoption_requires_guardian")
        if actor.actor_id not in subject_refs:
            raise JourneyForbiddenError("guardian_not_in_confirmed_subject_scope")


def _validate_actor(actor: GrowthPlanActor) -> None:
    if not all(
        value.strip()
        for value in (
            actor.actor_id,
            actor.tenant_id,
            actor.family_id,
            actor.membership_ref,
            actor.consent_ref,
        )
    ):
        raise JourneyForbiddenError("growth_plan_actor_context_required")


def _validate_command(command: AdoptGrowthPlanCommand) -> None:
    _validate_actor(command.actor)
    if not command.draft_ref.strip() or command.draft_version < 1:
        raise JourneyValidationError("growth_plan_draft_identity_required")
    if not command.idempotency_key.strip() or len(command.idempotency_key) > 128:
        raise JourneyValidationError("invalid_idempotency_key")
    if not command.correlation_id.strip() or len(command.correlation_id) > 128:
        raise JourneyValidationError("invalid_correlation_id")


def _validate_draft(draft: ValidatedGrowthPlanDraft, actor: GrowthPlanActor) -> None:
    if draft.tenant_id != actor.tenant_id or draft.family_id != actor.family_id:
        raise JourneyForbiddenError("growth_plan_draft_scope_denied")
    if draft.status != "VALIDATED_DRAFT":
        raise JourneyConflictError("growth_plan_draft_not_validated")
    if not draft.subject_refs or len(set(draft.subject_refs)) != len(draft.subject_refs):
        raise JourneyConflictError("growth_plan_draft_subject_scope_invalid")
    if not all(
        value.strip()
        for value in (
            draft.model_run_ref,
            draft.provenance_ref,
            draft.validation_receipt_ref,
            draft.validated_by,
            draft.content_sha256,
        )
    ):
        raise JourneyConflictError("growth_plan_draft_provenance_required")
    if draft.validated_at.tzinfo is None or draft.validated_at.utcoffset() is None:
        raise JourneyConflictError("growth_plan_validation_receipt_invalid")
    if draft.output.get("result_status") != "PLAN_DRAFT":
        raise JourneyConflictError("growth_plan_draft_not_adoptable")
    required = {
        "title",
        "family_goal",
        "why_this_plan",
        "duration",
        "stages",
        "adjustable_choices",
        "unknowns_to_watch",
        "review_rhythm",
        "limitations",
    }
    if not required <= set(draft.output):
        raise JourneyConflictError("growth_plan_draft_incomplete")
    if len(draft.output["stages"]) < 2:
        raise JourneyConflictError("growth_plan_draft_requires_stages")
    if draft.content_sha256 != _content_digest(draft.output):
        raise JourneyConflictError("growth_plan_draft_content_digest_mismatch")


def _validate_selected_choices(
    output: Mapping[str, Any], selected: Mapping[str, str]
) -> dict[str, str]:
    choices = output.get("adjustable_choices")
    if not isinstance(choices, list):
        raise JourneyConflictError("growth_plan_choices_invalid")
    allowed: dict[str, set[str]] = {}
    for choice in choices:
        if not isinstance(choice, Mapping):
            raise JourneyConflictError("growth_plan_choices_invalid")
        choice_id = choice.get("choice_id")
        options = choice.get("options")
        if not isinstance(choice_id, str) or not isinstance(options, list):
            raise JourneyConflictError("growth_plan_choices_invalid")
        allowed[choice_id] = {str(option) for option in options}
    if set(selected) != set(allowed):
        raise JourneyValidationError("growth_plan_choice_required")
    normalized = {key: str(value) for key, value in selected.items()}
    if any(value not in allowed[key] for key, value in normalized.items()):
        raise JourneyValidationError("growth_plan_choice_not_allowed")
    return normalized


def _content_digest(output: Mapping[str, Any]) -> str:
    encoded = json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _request_fingerprint(command: AdoptGrowthPlanCommand) -> str:
    encoded = json.dumps(
        {
            "action": ADOPT_GROWTH_PLAN_ACTION,
            "tenant_id": command.actor.tenant_id,
            "family_id": command.actor.family_id,
            "actor_id": command.actor.actor_id,
            "draft_ref": command.draft_ref,
            "draft_version": command.draft_version,
            "selected_choices": dict(sorted(command.selected_choices.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "ADOPT_GROWTH_PLAN_ACTION",
    "ADOPTED_PLAN_BOUNDARY",
    "AdoptGrowthPlanCommand",
    "AdoptedGrowthPlan",
    "AdoptedGrowthPlanRepository",
    "GrowthPlanActor",
    "GrowthPlanAdoptionPolicy",
    "GrowthPlanAdoptionService",
    "GrowthPlanDraftReader",
    "GuardianGrowthPlanPolicy",
    "ValidatedGrowthPlanDraft",
]
