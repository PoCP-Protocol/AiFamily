"""Minimal Principal draft runtime.

The runtime is intentionally a narrow application seam: route a request, read
published knowledge, call the single Model Gateway, and return a draft carrying
provenance.  It never imports a domain repository and never performs a Named
Action, so a model response cannot become a Family/Journey/Service/Commerce
fact by accident.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal

from backend.intelligence.context_engine.contracts import ContextScope, ContextSnapshot
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceEvent,
    ExperienceScope,
    MemoryRef,
    ScopeMismatchError,
)
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    ModelDraft,
    PolicyContext,
    StructuredRequest,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.principal.contracts import (
    PrincipalRouteDecision,
    PrincipalRouteRequest,
)
from backend.intelligence.principal.router import PrincipalCapabilityRouter


class PrincipalRuntimeError(ValueError):
    """Fail-closed runtime boundary error."""


@dataclass(frozen=True, slots=True)
class PrincipalRuntimeRequest:
    """Input to one Principal draft/decision run."""

    route_request: PrincipalRouteRequest
    prompt: str
    knowledge_scope: str
    knowledge_purpose: str
    output_schema: Mapping[str, Any]
    input_refs: tuple[str, ...] = ()
    require_knowledge: bool = True
    experience_event: ExperienceEvent | None = None
    memory_refs: tuple[MemoryRef, ...] = ()
    prompt_version: str = "principal-runtime.v1"
    schema_version: str = "principal-draft.v1"

    def __post_init__(self) -> None:
        if not isinstance(self.route_request, PrincipalRouteRequest):
            raise PrincipalRuntimeError("ROUTE_REQUEST_REQUIRED")
        if not self.prompt.strip():
            raise PrincipalRuntimeError("PROMPT_REQUIRED")
        if not self.knowledge_scope.strip() or not self.knowledge_purpose.strip():
            raise PrincipalRuntimeError("KNOWLEDGE_SCOPE_AND_PURPOSE_REQUIRED")
        if not self.output_schema:
            raise PrincipalRuntimeError("OUTPUT_SCHEMA_REQUIRED")
        if not self.prompt_version or not self.schema_version:
            raise PrincipalRuntimeError("VERSION_REQUIRED")


@dataclass(frozen=True, slots=True)
class PrincipalDraft:
    """Structured, provenance-bearing output with an immutable DRAFT boundary."""

    draft_id: str
    route: PrincipalRouteDecision
    output: Mapping[str, Any]
    model_provenance: AiProvenance
    knowledge_claim_ids: tuple[str, ...]
    experience_event_id: str | None
    memory_ref_ids: tuple[str, ...]
    status: Literal["DRAFT"] = "DRAFT"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.draft_id or not isinstance(self.route, PrincipalRouteDecision):
            raise PrincipalRuntimeError("DRAFT_ID_AND_ROUTE_REQUIRED")
        if not isinstance(self.model_provenance, AiProvenance):
            raise PrincipalRuntimeError("DRAFT_PROVENANCE_REQUIRED")
        if self.status != "DRAFT":
            raise PrincipalRuntimeError("PRINCIPAL_DRAFT_STATUS_MUST_REMAIN_DRAFT")
        object.__setattr__(self, "output", MappingProxyType(dict(self.output)))

    @property
    def may_mutate_business_state(self) -> bool:
        return False

    @property
    def requires_human_confirmation(self) -> bool:
        return True

    @property
    def tenant_id(self) -> str:
        return self.route.tenant_id

    @property
    def family_id(self) -> str | None:
        return self.route.family_id

    @property
    def subject_id(self) -> str | None:
        return self.route.subject_id

    @property
    def purpose(self) -> str:
        return self.route.purpose

    @property
    def consent_version(self) -> str:
        return self.route.consent_version

    @property
    def correlation_id(self) -> str:
        return self.route.correlation_id

    @property
    def causation_id(self) -> str:
        return self.route.causation_id


class PrincipalRuntime:
    """Route → knowledge → Model Gateway → immutable PrincipalDraft."""

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        knowledge_registry: KnowledgeRegistry,
        router: PrincipalCapabilityRouter | None = None,
        context_broker: ContextBroker | None = None,
        provider_id: str,
    ) -> None:
        if not provider_id:
            raise PrincipalRuntimeError("PROVIDER_ID_REQUIRED")
        self._gateway = gateway
        self._knowledge = knowledge_registry
        self._router = router or PrincipalCapabilityRouter()
        self._context_broker = context_broker
        self._provider_id = provider_id

    async def draft(self, request: PrincipalRuntimeRequest) -> PrincipalDraft:
        """Produce a structured draft or fail closed before model invocation."""

        decision = self._router.resolve(request.route_request)
        self._assert_experience_scope(request, decision)
        context_projection = self._context_projection(request, decision)
        claims = self._knowledge.retrieve_reviewed(
            purpose=request.knowledge_purpose,
            scope=request.knowledge_scope,
        )
        if request.require_knowledge and not claims:
            raise PrincipalRuntimeError("KNOWLEDGE_NOT_AVAILABLE")

        payload: dict[str, Any] = {
            "prompt": request.prompt,
            "route": {
                "capability": decision.capability.value,
                "profile_id": decision.profile_id,
                "purpose": decision.purpose,
                "locale": decision.locale,
            },
            "context_projection": context_projection,
            "knowledge_claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "source_id": claim.source_id,
                    "provenance_level": claim.provenance.level,
                }
                for claim in claims
            ],
            # Only identifiers and interaction metadata cross this seam. Raw
            # memory/event payloads stay in their scoped stores.
            "experience_event": self._event_projection(request.experience_event),
            "memory_refs": [
                {
                    "memory_id": memory.memory_id,
                    "memory_scope": memory.memory_scope.value,
                    "level": memory.level.value,
                }
                for memory in request.memory_refs
            ],
        }
        structured_request = StructuredRequest(
            use_case=decision.capability.value,
            prompt_version=request.prompt_version,
            schema_version=request.schema_version,
            data_class=request.route_request.data_class,
            payload=payload,
            output_schema=dict(request.output_schema),
            context_snapshot_ref=request.route_request.context_snapshot_ref,
            input_refs=tuple(request.input_refs)
            + tuple(claim.claim_id for claim in claims)
            + tuple(memory.memory_id for memory in request.memory_refs),
            request_id=request.route_request.request_id,
            policy_context=PolicyContext(),
        )
        model_draft = await self._gateway.generate_structured(
            structured_request,
            provider_id=self._provider_id,
        )
        return self._to_principal_draft(request, decision, model_draft, claims)

    @staticmethod
    def _event_projection(event: ExperienceEvent | None) -> dict[str, str] | None:
        if event is None:
            return None
        return {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "node": event.node.value,
        }

    def _context_projection(
        self,
        request: PrincipalRuntimeRequest,
        decision: PrincipalRouteDecision,
    ) -> Mapping[str, Any]:
        """Load one authorized snapshot, or explicitly mark it unavailable.

        The no-broker path is retained for the first draft slice.  It carries a
        machine-readable unavailable marker rather than fabricating an empty
        family context, so callers cannot mistake compatibility for evidence.
        """

        if self._context_broker is None:
            return MappingProxyType(
                {
                    "status": "UNAVAILABLE",
                    "reason": "CONTEXT_PROJECTION_UNAVAILABLE",
                }
            )
        scope = self._context_scope(request, decision)
        snapshot = self._context_broker.read(
            request.route_request.context_snapshot_ref,
            scope,
        )
        self._assert_snapshot_boundary(snapshot, decision)
        return self._json_safe_projection(snapshot.read_only_projection)

    @staticmethod
    def _context_scope(
        request: PrincipalRuntimeRequest,
        decision: PrincipalRouteDecision,
    ) -> ContextScope:
        if decision.family_id is None:
            raise PrincipalRuntimeError("CONTEXT_FAMILY_SCOPE_REQUIRED")
        subject_ids: tuple[str, ...]
        if decision.subject_id:
            subject_ids = (decision.subject_id,)
        elif request.experience_event is not None:
            subject_ids = request.experience_event.subject_ids
        else:
            subject_ids = tuple(
                sorted(
                    {
                        subject_id
                        for memory in request.memory_refs
                        for subject_id in memory.subject_ids
                    }
                )
            )
        if not subject_ids:
            raise PrincipalRuntimeError("CONTEXT_SUBJECT_SCOPE_REQUIRED")
        return ContextScope(
            tenant_id=decision.tenant_id,
            region_id=decision.region,
            family_id=decision.family_id,
            subject_ids=subject_ids,
            purpose=decision.purpose,
            consent_version=decision.consent_version,
            consent_granted=decision.consent_granted,
            data_class=decision.data_class,
            locale=decision.locale,
            content_locale=decision.content_locale,
            model_locale=decision.model_locale,
            policy_locale=decision.policy_locale,
            deletion_ref=f"context:{request.route_request.context_snapshot_ref}",
            correlation_id=decision.correlation_id,
            causation_id=decision.causation_id,
        )

    @staticmethod
    def _assert_snapshot_boundary(
        snapshot: ContextSnapshot,
        decision: PrincipalRouteDecision,
    ) -> None:
        if snapshot.region_id != decision.region:
            raise ScopeMismatchError("CROSS_REGION_CONTEXT_SNAPSHOT")
        if snapshot.consent_version != decision.consent_version:
            raise ExperienceContractError("CONTEXT_CONSENT_VERSION_MISMATCH")
        if not snapshot.consent_granted or not decision.consent_granted:
            raise ExperienceContractError("CONSENT_REVOKED")
        if str(snapshot.data_class) != str(decision.data_class):
            raise ExperienceContractError("CONTEXT_DATA_CLASS_MISMATCH")

    @staticmethod
    def _json_safe_projection(value: Any) -> Any:
        """Convert immutable mapping/tuple wrappers to provider-safe JSON values."""

        if isinstance(value, Mapping):
            return {
                key: PrincipalRuntime._json_safe_projection(item)
                for key, item in value.items()
            }
        if isinstance(value, tuple):
            return [PrincipalRuntime._json_safe_projection(item) for item in value]
        return value

    @staticmethod
    def _to_principal_draft(
        request: PrincipalRuntimeRequest,
        decision: PrincipalRouteDecision,
        model_draft: ModelDraft,
        claims: tuple[Any, ...],
    ) -> PrincipalDraft:
        return PrincipalDraft(
            draft_id=f"draft:{request.route_request.request_id}",
            route=decision,
            output=model_draft.output,
            model_provenance=model_draft.provenance,
            knowledge_claim_ids=tuple(claim.claim_id for claim in claims),
            experience_event_id=(
                request.experience_event.event_id if request.experience_event else None
            ),
            memory_ref_ids=tuple(memory.memory_id for memory in request.memory_refs),
        )

    @staticmethod
    def _assert_experience_scope(
        request: PrincipalRuntimeRequest,
        decision: PrincipalRouteDecision,
    ) -> None:
        event = request.experience_event
        if event is not None:
            if event.tenant_id != decision.tenant_id:
                raise ScopeMismatchError("CROSS_TENANT_EXPERIENCE_CONTEXT")
            if event.family_id != decision.family_id:
                raise ScopeMismatchError("CROSS_FAMILY_EXPERIENCE_CONTEXT")
            if decision.subject_id and decision.subject_id not in event.subject_ids:
                raise ScopeMismatchError("CROSS_SUBJECT_EXPERIENCE_CONTEXT")
            if event.purpose != decision.purpose:
                raise ExperienceContractError("EXPERIENCE_PURPOSE_MISMATCH")
            if event.consent_version != decision.consent_version:
                raise ExperienceContractError("EXPERIENCE_CONSENT_VERSION_MISMATCH")

        if not request.memory_refs:
            return
        if decision.family_id is None:
            raise PrincipalRuntimeError("MEMORY_FAMILY_SCOPE_REQUIRED")
        subject_ids = (
            (decision.subject_id,)
            if decision.subject_id
            else tuple(
                sorted(
                    {
                        subject_id
                        for memory in request.memory_refs
                        for subject_id in memory.subject_ids
                    }
                )
            )
        )
        if not subject_ids:
            raise PrincipalRuntimeError("MEMORY_SUBJECT_SCOPE_REQUIRED")
        scope = ExperienceScope(
            global_id=decision.global_id,
            tenant_id=decision.tenant_id,
            region_id=decision.region,
            family_id=decision.family_id,
            subject_ids=subject_ids,
            purpose=decision.purpose,
            consent_version=decision.consent_version,
            consent_granted=decision.consent_granted,
            data_class=decision.data_class,
            locale=decision.locale,
            content_locale=decision.content_locale,
            model_locale=decision.model_locale,
            policy_locale=decision.policy_locale,
            deletion_ref=DeletionRef(
                deletion_id=f"runtime:{decision.global_id}",
                retention_policy="runtime-request",
            ),
            correlation_id=decision.correlation_id,
            causation_id=decision.causation_id,
        )
        for memory in request.memory_refs:
            memory.assert_readable_by(scope, purpose=decision.purpose)


__all__ = [
    "PrincipalDraft",
    "PrincipalRuntime",
    "PrincipalRuntimeError",
    "PrincipalRuntimeRequest",
]
