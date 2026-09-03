"""UI-03 assessment evidence to governed Agent Runtime adapter.

This application adapter is the first blueprint vertical slice from a domain
evidence record into Family Context, Principal routing and a provider-neutral
AI draft.  It deliberately implements only the read/draft side of the flow;
the assessment domain remains the sole owner of the guardian Named Action that
can create a GrowthIntent.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.assessment.application.ports import AssessmentInterpretationPort
from backend.domains.assessment.domain.entities import GrowthHypothesisEvidence
from backend.domains.assessment.domain.interpretation_boundary import (
    assert_interpretation_boundary,
)
from backend.intelligence.agent_runtime.authorization_persistence import (
    AgentAuthorizationScope,
    SqlAlchemyAgentAuthorizationLeaseStore,
)
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentRun,
    AgentTask,
)
from backend.intelligence.agent_runtime.persistence import (
    AgentRunScope,
    AgentRunStatus,
    SqlAlchemyAgentRunStore,
)
from backend.intelligence.context_engine.async_port import AsyncContextBrokerPort
from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    DataClass,
    StateObservation,
)
from backend.intelligence.principal.contracts import (
    PrincipalCapability,
    PrincipalEntryPoint,
    PrincipalHumanGate,
    PrincipalOutputType,
    PrincipalRouteRequest,
)
from backend.intelligence.principal.router import PrincipalCapabilityRouter


class AssessmentAgentHandle(Protocol):
    scope: ContextScope

    async def execute(
        self,
        task: AgentTask,
        authorization: AgentAuthorization | None,
        *,
        idempotency_key: str,
    ) -> AgentRun: ...


class AssessmentAgentResolver(Protocol):
    async def resolve(self, family_id: str) -> AssessmentAgentHandle: ...


AuthorizationResolver = Callable[
    [str, ContextScope, GrowthHypothesisEvidence],
    AgentAuthorization | Awaitable[AgentAuthorization],
]
ActorIdResolver = Callable[[], str | Awaitable[str]]
RunReplayResolver = Callable[
    [str, ContextScope],
    AgentRun | None | Awaitable[AgentRun | None],
]


@dataclass(frozen=True, slots=True)
class AssessmentAiAssets:
    """Reviewed execution-material identities selected by deployment."""

    prompt_ref: str
    prompt_version: str
    schema_ref: str
    schema_version: str
    reviewed_construct_refs: frozenset[str]
    observation_retention: timedelta = timedelta(days=365)
    snapshot_ttl: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.prompt_ref,
                self.prompt_version,
                self.schema_ref,
                self.schema_version,
            )
        ):
            raise ValueError("assessment AI prompt/schema identities are required")
        if not self.reviewed_construct_refs:
            raise ValueError("reviewed_construct_refs are required")
        if self.observation_retention <= timedelta(0) or self.snapshot_ttl <= timedelta(0):
            raise ValueError("assessment AI context TTLs must be positive")


@dataclass(frozen=True, slots=True)
class SqlAlchemyAssessmentAuthorizationResolver:
    """Resolve an already-issued lease for the authenticated request actor.

    This adapter never manufactures authorization. A guardian or designated
    professional must have issued a durable lease beforehand, and the current
    authenticated actor must be the lease issuer.
    """

    session_factory: async_sessionmaker[AsyncSession]
    actor_id_resolver: ActorIdResolver
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not callable(self.actor_id_resolver) or not callable(self.clock):
            raise TypeError("assessment authorization resolvers must be callable")

    async def __call__(
        self,
        agent_id: str,
        scope: ContextScope,
        evidence: GrowthHypothesisEvidence,
    ) -> AgentAuthorization:
        actor_id = self.actor_id_resolver()
        if inspect.isawaitable(actor_id):
            actor_id = await actor_id
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise PermissionError("AUTHENTICATED_ASSESSMENT_ACTOR_REQUIRED")
        if evidence.subject_person_id not in scope.subject_ids:
            raise PermissionError("ASSESSMENT_AUTHORIZATION_SUBJECT_SCOPE_MISMATCH")
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("assessment authorization clock must be timezone-aware")
        async with self.session_factory() as session:
            authorization = await SqlAlchemyAgentAuthorizationLeaseStore(session).find_active(
                scope=AgentAuthorizationScope(scope.tenant_id, scope.family_id),
                agent_id=agent_id,
                use_case=PrincipalCapability.ASSESSMENT_INTERPRETATION.value,
                issued_by=actor_id,
                requested_tools={"read_context"},
                estimated_steps=1,
                now=now,
            )
        if authorization is None:
            raise PermissionError("ACTIVE_ASSESSMENT_AGENT_AUTHORIZATION_REQUIRED")
        return authorization


@dataclass(frozen=True, slots=True)
class SqlAlchemyAssessmentRunReplayResolver:
    """Recover the exact successful draft previously shown for one request."""

    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")

    async def __call__(self, request_id: str, scope: ContextScope) -> AgentRun | None:
        async with self.session_factory() as session:
            replay = await SqlAlchemyAgentRunStore(session).replay_by_request_id(
                request_id,
                scope=AgentRunScope(scope.tenant_id, scope.family_id),
            )
        if replay is None:
            return None
        record = replay.run
        if record.status is AgentRunStatus.FAILED:
            raise RuntimeError("ASSESSMENT_AGENT_RUN_PREVIOUSLY_FAILED")
        if record.status is AgentRunStatus.STARTED:
            raise RuntimeError("ASSESSMENT_AGENT_RUN_IN_PROGRESS")
        if record.draft is None:
            raise RuntimeError("ASSESSMENT_AGENT_RUN_DRAFT_MISSING")
        return AgentRun(
            run_id=record.run_id,
            request_id=record.request_id,
            agent_id=record.agent_id,
            tenant_id=record.tenant_id,
            family_id=record.family_id,
            use_case=record.use_case,
            draft=record.draft,
            started_at=record.started_at,
            completed_at=record.completed_at or record.started_at,
        )


class AssessmentAiInterpretationAdapter(AssessmentInterpretationPort):
    """Produce a boundary-checked Perspective draft from submitted evidence."""

    def __init__(
        self,
        *,
        runtime_resolver: AssessmentAgentResolver,
        context_broker: AsyncContextBrokerPort,
        authorization_resolver: AuthorizationResolver,
        assets: AssessmentAiAssets,
        run_replay_resolver: RunReplayResolver | None = None,
        principal_router: PrincipalCapabilityRouter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(getattr(runtime_resolver, "resolve", None)):
            raise TypeError("runtime_resolver must implement resolve")
        if not isinstance(context_broker, AsyncContextBrokerPort):
            raise TypeError("context_broker must implement AsyncContextBrokerPort")
        if context_broker.durability_mode != "DURABLE":
            raise ValueError("assessment AI requires a durable Context Broker")
        if not callable(authorization_resolver):
            raise TypeError("authorization_resolver must be callable")
        if run_replay_resolver is not None and not callable(run_replay_resolver):
            raise TypeError("run_replay_resolver must be callable")
        self._runtime_resolver = runtime_resolver
        self._context_broker = context_broker
        self._authorization_resolver = authorization_resolver
        self._assets = assets
        self._run_replay_resolver = run_replay_resolver
        self._principal_router = principal_router or PrincipalCapabilityRouter()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def interpret(
        self,
        family_id: str,
        evidence: GrowthHypothesisEvidence,
        service_depth: str = "DEEP_AI_INTERPRETATION",
    ) -> dict:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("assessment AI clock must be timezone-aware")
        if evidence.submitted_at is None or evidence.submitted_at.tzinfo is None:
            raise ContextContractError("SUBMITTED_ASSESSMENT_TIMESTAMP_REQUIRED")

        subject_resolver = getattr(self._runtime_resolver, "resolve_for_subject", None)
        runtime = (
            await subject_resolver(family_id, evidence.subject_person_id)
            if callable(subject_resolver)
            else await self._runtime_resolver.resolve(family_id)
        )
        scope = runtime.scope
        self._assert_scope(scope, family_id, evidence)
        input_refs = _input_refs(evidence)
        observation = self._observation(scope, evidence, input_refs)
        if observation.expires_at is None or observation.expires_at <= now:
            raise ContextContractError("ASSESSMENT_EVIDENCE_RETENTION_EXPIRED")
        await self._context_broker.append(observation)
        snapshot = await self._context_broker.snapshot(
            subject_id=evidence.subject_person_id,
            scope=scope,
            now=now,
            snapshot_ttl=self._assets.snapshot_ttl,
        )
        if not set(input_refs).issubset(snapshot.source_refs):
            raise ContextContractError("ASSESSMENT_EVIDENCE_NOT_IN_CONTEXT_SNAPSHOT")

        authorization = self._authorization_resolver("parent_advisor", scope, evidence)
        if inspect.isawaitable(authorization):
            authorization = await authorization
        if not isinstance(authorization, AgentAuthorization):
            raise TypeError("authorization_resolver must return AgentAuthorization")

        request_id = _request_id(
            evidence,
            consent_version=scope.consent_version,
            service_depth=service_depth,
            assets=self._assets,
        )
        route = self._principal_router.resolve(
            PrincipalRouteRequest(
                request_id=request_id,
                tenant_id=scope.tenant_id,
                actor_type="authorized_guardian_or_professional",
                entry_point=PrincipalEntryPoint.ASK_PRINCIPAL,
                capability=PrincipalCapability.ASSESSMENT_INTERPRETATION,
                purpose=scope.purpose,
                data_class=scope.data_class.value,
                context_snapshot_ref=snapshot.snapshot_ref,
                consent_granted=scope.consent_granted,
                global_id=authorization.issued_by,
                consent_version=scope.consent_version,
                correlation_id=scope.correlation_id,
                causation_id=scope.causation_id,
                family_id=scope.family_id,
                subject_id=evidence.subject_person_id,
                locale=scope.locale,
                content_locale=scope.effective_content_locale,
                model_locale=scope.effective_model_locale,
                policy_locale=scope.effective_policy_locale,
                region=scope.region_id,
            )
        )
        if (
            route.agent_id != "parent_advisor"
            or route.output_type is not PrincipalOutputType.PERSPECTIVE
            or route.human_gate is not PrincipalHumanGate.REVIEW_REQUIRED
        ):
            raise RuntimeError("assessment Principal route violates reviewed governance")

        task = AgentTask(
            request_id=request_id,
            agent_id=route.agent_id,
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            use_case=PrincipalCapability.ASSESSMENT_INTERPRETATION.value,
            context_snapshot_ref=snapshot.snapshot_ref,
            prompt_version=self._assets.prompt_version,
            schema_version=self._assets.schema_version,
            data_class="MINOR_PERSONAL_DATA",
            payload=_payload(evidence, service_depth, route.human_gate.value),
            output_schema=_growth_perspective_schema(),
            prompt_ref=self._assets.prompt_ref,
            schema_ref=self._assets.schema_ref,
            input_refs=input_refs,
            requested_tools=frozenset({"read_context"}),
        )
        run = None
        if self._run_replay_resolver is not None:
            run = self._run_replay_resolver(request_id, scope)
            if inspect.isawaitable(run):
                run = await run
            if run is not None and (
                run.agent_id != route.agent_id
                or run.use_case != PrincipalCapability.ASSESSMENT_INTERPRETATION.value
            ):
                raise RuntimeError("assessment AgentRun replay binding mismatch")
        if run is None:
            run = await runtime.execute(
                task,
                authorization,
                idempotency_key=f"assessment-interpretation:{request_id}",
            )
        draft = dict(run.draft.output)
        if draft.get("assessment_ref") not in (None, evidence.assessment_session_id):
            raise ValueError("assessment draft evidence binding mismatch")
        assert_interpretation_boundary(draft, set(self._assets.reviewed_construct_refs))
        provenance = run.draft.provenance
        return {
            "subsystem_ref": "AIFAMILY_GOVERNED_AI_RUNTIME",
            "subsystem_version": "1.0.0",
            "service_depth": service_depth,
            "interpretation": {
                "backend_capability_ref": "ASSESSMENT_INTERPRETATION",
                "ai_use_case": "ASSESSMENT_INTERPRETATION",
                "generator": "MODEL_GATEWAY",
                "assessment_ref": evidence.assessment_session_id,
                "draft": draft,
            },
            "scorecard": {
                "generator": "MODEL_GATEWAY",
                "agent_run_ref": run.run_id,
                "provider_ref": provenance.provider_id,
                "model_ref": provenance.model,
                "model_version": provenance.model_version,
                "prompt_version": provenance.prompt_version,
                "schema_version": provenance.schema_version,
                "context_snapshot_ref": provenance.context_snapshot_ref,
                "input_refs": list(input_refs),
                "draft_status": run.draft.status,
            },
        }

    @staticmethod
    def _assert_scope(
        scope: ContextScope,
        family_id: str,
        evidence: GrowthHypothesisEvidence,
    ) -> None:
        scope.assert_active()
        if scope.family_id != family_id:
            raise PermissionError("assessment runtime family scope mismatch")
        if evidence.subject_person_id not in scope.subject_ids:
            raise PermissionError("assessment runtime subject scope mismatch")
        if scope.data_class is not DataClass.MINOR_PERSONAL_DATA:
            raise ContextContractError("assessment runtime requires minor data scope")

    def _observation(
        self,
        scope: ContextScope,
        evidence: GrowthHypothesisEvidence,
        input_refs: tuple[str, ...],
    ) -> StateObservation:
        identity = ":".join((*input_refs, scope.consent_version))
        digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
        observed_value = json.dumps(
            {
                "event": "assessment_submitted",
                "focus_ref": evidence.focus_ref,
                "need_type_ref": evidence.need_type_ref,
                "tool_ref": evidence.tool_ref,
                "tool_version": evidence.tool_version,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return StateObservation(
            observation_id=f"assessment-observation:{digest}",
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            subject_id=evidence.subject_person_id,
            dimension="assessment_evidence",
            observed_value=observed_value,
            evidence_refs=input_refs,
            provenance="assessment-domain:submitted-evidence",
            observed_at=evidence.submitted_at,
            data_class=scope.data_class,
            purpose=scope.purpose,
            consent_version=scope.consent_version,
            consent_granted=scope.consent_granted,
            region_id=scope.region_id,
            locale=scope.locale,
            deletion_ref=scope.deletion_ref,
            correlation_id=f"assessment-evidence:{evidence.assessment_evidence_id}",
            causation_id=f"assessment-session:{evidence.assessment_session_id}",
            expires_at=evidence.submitted_at + self._assets.observation_retention,
            retention_policy="assessment-evidence-reviewed-retention.v1",
        )


def _input_refs(evidence: GrowthHypothesisEvidence) -> tuple[str, ...]:
    return (
        f"assessment-evidence:{evidence.assessment_evidence_id}",
        f"assessment-session:{evidence.assessment_session_id}",
        f"assessment-response:{evidence.assessment_response_id}",
    )


def _request_id(
    evidence: GrowthHypothesisEvidence,
    *,
    consent_version: str,
    service_depth: str,
    assets: AssessmentAiAssets,
) -> str:
    material = json.dumps(
        {
            "consent_version": consent_version,
            "input_refs": _input_refs(evidence),
            "payload": _payload(evidence, service_depth, "REVIEW_REQUIRED"),
            "prompt_ref": assets.prompt_ref,
            "prompt_version": assets.prompt_version,
            "schema_ref": assets.schema_ref,
            "schema_version": assets.schema_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"assessment-ai-{hashlib.sha256(material.encode()).hexdigest()}"


def _payload(
    evidence: GrowthHypothesisEvidence,
    service_depth: str,
    human_gate: str,
) -> dict[str, object]:
    return {
        "assessment_ref": evidence.assessment_session_id,
        "service_depth": service_depth,
        "focus_ref": evidence.focus_ref,
        "need_type_ref": evidence.need_type_ref,
        "need_type_version": evidence.need_type_version,
        "title": evidence.title,
        "description": evidence.description,
        "required_capability_keys": list(evidence.required_capability_keys),
        "response_set": [dict(item) for item in evidence.response_set],
        "human_gate": human_gate,
        "output_boundary": "perspective_draft_only",
    }


def _growth_perspective_schema() -> dict[str, object]:
    """Bootstrap schema; production uses the reviewed registry definition."""

    return {
        "type": "object",
        "required": [
            "model_component_ref",
            "boundary_labels",
            "need_summary",
            "construct_signals",
            "hypotheses",
            "action_candidates",
        ],
        "properties": {
            "model_component_ref": {"type": "string"},
            "assessment_ref": {"type": "string"},
            "boundary_labels": {"type": "array", "items": {"type": "string"}},
            "need_summary": {"type": "array", "items": {"type": "object"}},
            "construct_signals": {"type": "array", "items": {"type": "object"}},
            "hypotheses": {"type": "array", "items": {"type": "object"}},
            "action_candidates": {"type": "array", "items": {"type": "object"}},
        },
    }


__all__ = [
    "AssessmentAiAssets",
    "AssessmentAiInterpretationAdapter",
    "SqlAlchemyAssessmentAuthorizationResolver",
    "SqlAlchemyAssessmentRunReplayResolver",
]
