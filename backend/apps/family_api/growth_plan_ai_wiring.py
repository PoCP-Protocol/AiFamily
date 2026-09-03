"""Governed UI-05 GrowthIntent to AI plan-draft application adapter.

The adapter owns only the draft side of the blueprint flow.  It cannot create,
activate or mutate a JourneyPlan; the Journey domain remains the canonical
owner and may act only after an explicit guardian Named Action.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from backend.intelligence.model_gateway.provenance import ModelDraftIdentity
from backend.intelligence.principal.contracts import (
    PrincipalCapability,
    PrincipalEntryPoint,
    PrincipalHumanGate,
    PrincipalOutputType,
    PrincipalRouteRequest,
)
from backend.intelligence.principal.router import PrincipalCapabilityRouter

CONFIRMED_INTENT_BOUNDARY = "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
PLAN_DRAFT_BOUNDARIES = frozenset(
    {
        "plan_draft_not_active",
        "recommendation_not_outcome",
        "guardian_confirmation_required",
        "pause_without_penalty",
    }
)
PLAN_STAGE_IDS = ("SEE", "PARENT_FIRST", "CO_CREATE", "STABILIZE")
_FORBIDDEN_OUTPUT_KEYS = frozenset(
    {
        "activated_plan",
        "canonical_fact",
        "diagnosis",
        "efficacy_claim",
        "family_rank",
        "family_ranking",
        "family_score",
        "family_total_score",
        "outcome",
        "risk_score",
    }
)


@dataclass(frozen=True, slots=True)
class GrowthPlanEvidence:
    """Minimum immutable evidence required to draft a family plan."""

    intent_id: str
    onboarding_id: str
    priority_id: str
    subject_person_id: str
    need_type: str
    goal_text: str
    required_capability_keys: tuple[str, ...]
    dimension_id: str
    confirmed_by_actor_id: str
    confirmed_at: datetime
    priority_confirmed_by_actor_id: str
    priority_confirmed_at: datetime
    onboarding_version: int = 1
    priority_policy_version: str = "M2_104_DETERMINISTIC_V2"
    boundary: str = CONFIRMED_INTENT_BOUNDARY

    def __post_init__(self) -> None:
        required = (
            self.intent_id,
            self.onboarding_id,
            self.priority_id,
            self.subject_person_id,
            self.need_type,
            self.goal_text,
            self.dimension_id,
            self.confirmed_by_actor_id,
            self.priority_confirmed_by_actor_id,
            self.priority_policy_version,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ValueError("growth plan evidence fields are required")
        if self.confirmed_at.tzinfo is None:
            raise ValueError("growth plan confirmation timestamp must be timezone-aware")
        if self.priority_confirmed_at.tzinfo is None:
            raise ValueError("growth priority confirmation timestamp must be timezone-aware")
        if self.onboarding_version < 1:
            raise ValueError("growth onboarding version must be positive")
        if self.boundary != CONFIRMED_INTENT_BOUNDARY:
            raise PermissionError("GROWTH_PLAN_REQUIRES_CONFIRMED_INTENT")
        confirmation_actors = (
            self.confirmed_by_actor_id,
            self.priority_confirmed_by_actor_id,
        )
        if any(
            actor.lower().startswith("ai:") or actor.upper() in {"AI", "SYSTEM"}
            for actor in confirmation_actors
        ):
            raise PermissionError("GROWTH_PLAN_REQUIRES_HUMAN_CONFIRMATION")
        if not self.required_capability_keys or any(
            not value.strip() for value in self.required_capability_keys
        ):
            raise ValueError("growth plan required capabilities are required")


class GrowthPlanAgentHandle(Protocol):
    scope: ContextScope

    async def execute(
        self,
        task: AgentTask,
        authorization: AgentAuthorization | None,
        *,
        idempotency_key: str,
    ) -> AgentRun: ...


class GrowthPlanAgentResolver(Protocol):
    async def resolve(self, family_id: str) -> GrowthPlanAgentHandle: ...


AuthorizationResolver = Callable[
    [str, ContextScope, GrowthPlanEvidence],
    AgentAuthorization | Awaitable[AgentAuthorization],
]
ActorIdResolver = Callable[[], str | Awaitable[str]]
RunReplayResolver = Callable[
    [str, ContextScope],
    AgentRun | None | Awaitable[AgentRun | None],
]


class GrowthPlanDraftStore(Protocol):
    async def save(
        self,
        *,
        run: AgentRun,
        scope: ContextScope,
        evidence: GrowthPlanEvidence,
        input_refs: tuple[str, ...],
        created_at: datetime,
    ) -> ModelDraftIdentity: ...


@dataclass(frozen=True, slots=True)
class GrowthPlanAiAssets:
    prompt_ref: str
    prompt_version: str
    schema_ref: str
    schema_version: str
    journey_template_ref: str
    journey_template_version: str
    release_set_ref: str
    runtime_config_digest: str
    observation_retention: timedelta = timedelta(days=180)
    snapshot_ttl: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.prompt_ref,
                self.prompt_version,
                self.schema_ref,
                self.schema_version,
                self.journey_template_ref,
                self.journey_template_version,
                self.release_set_ref,
                self.runtime_config_digest,
            )
        ):
            raise ValueError("growth plan AI prompt/schema identities are required")
        if self.observation_retention <= timedelta(0) or self.snapshot_ttl <= timedelta(0):
            raise ValueError("growth plan AI context TTLs must be positive")


@dataclass(frozen=True, slots=True)
class SqlAlchemyGrowthPlanAuthorizationResolver:
    """Load a pre-issued growth-planner lease for the authenticated guardian."""

    session_factory: async_sessionmaker[AsyncSession]
    actor_id_resolver: ActorIdResolver
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def __call__(
        self,
        agent_id: str,
        scope: ContextScope,
        evidence: GrowthPlanEvidence,
    ) -> AgentAuthorization:
        actor_id = self.actor_id_resolver()
        if inspect.isawaitable(actor_id):
            actor_id = await actor_id
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise PermissionError("AUTHENTICATED_GROWTH_PLAN_ACTOR_REQUIRED")
        if evidence.subject_person_id not in scope.subject_ids:
            raise PermissionError("GROWTH_PLAN_AUTHORIZATION_SUBJECT_SCOPE_MISMATCH")
        async with self.session_factory() as session:
            authorization = await SqlAlchemyAgentAuthorizationLeaseStore(session).find_active(
                scope=AgentAuthorizationScope(scope.tenant_id, scope.family_id),
                agent_id=agent_id,
                use_case=PrincipalCapability.GROWTH_PLAN_DRAFT.value,
                issued_by=actor_id,
                requested_tools={"read_context"},
                estimated_steps=1,
                now=self.clock(),
            )
        if authorization is None:
            raise PermissionError("ACTIVE_GROWTH_PLAN_AGENT_AUTHORIZATION_REQUIRED")
        return authorization


@dataclass(frozen=True, slots=True)
class SqlAlchemyGrowthPlanRunReplayResolver:
    session_factory: async_sessionmaker[AsyncSession]

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
            raise RuntimeError("GROWTH_PLAN_AGENT_RUN_PREVIOUSLY_FAILED")
        if record.status is AgentRunStatus.STARTED:
            raise RuntimeError("GROWTH_PLAN_AGENT_RUN_IN_PROGRESS")
        if record.draft is None:
            raise RuntimeError("GROWTH_PLAN_AGENT_RUN_DRAFT_MISSING")
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


class GrowthPlanAiDraftAdapter:
    """Generate a replayable, evidence-bound plan draft for UI-05."""

    def __init__(
        self,
        *,
        runtime_resolver: GrowthPlanAgentResolver,
        context_broker: AsyncContextBrokerPort,
        authorization_resolver: AuthorizationResolver,
        assets: GrowthPlanAiAssets,
        draft_store: GrowthPlanDraftStore | None = None,
        run_replay_resolver: RunReplayResolver | None = None,
        principal_router: PrincipalCapabilityRouter | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(getattr(runtime_resolver, "resolve", None)):
            raise TypeError("runtime_resolver must implement resolve")
        if not isinstance(context_broker, AsyncContextBrokerPort):
            raise TypeError("context_broker must implement AsyncContextBrokerPort")
        if context_broker.durability_mode != "DURABLE":
            raise ValueError("growth plan AI requires a durable Context Broker")
        if not callable(authorization_resolver):
            raise TypeError("authorization_resolver must be callable")
        self._runtime_resolver = runtime_resolver
        self._context_broker = context_broker
        self._authorization_resolver = authorization_resolver
        self._assets = assets
        self._draft_store = draft_store
        self._run_replay_resolver = run_replay_resolver
        self._principal_router = principal_router or PrincipalCapabilityRouter()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def generate(self, family_id: str, evidence: GrowthPlanEvidence) -> dict[str, object]:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("growth plan AI clock must be timezone-aware")
        subject_resolver = getattr(self._runtime_resolver, "resolve_for_subject", None)
        runtime = (
            await subject_resolver(family_id, evidence.subject_person_id)
            if callable(subject_resolver)
            else await self._runtime_resolver.resolve(family_id)
        )
        scope = runtime.scope
        _assert_scope(scope, family_id, evidence)
        input_refs = growth_plan_input_refs(evidence, self._assets)
        for observation in _observations(scope, evidence, input_refs, self._assets):
            if observation.expires_at is None or observation.expires_at <= now:
                raise ContextContractError("GROWTH_PLAN_EVIDENCE_RETENTION_EXPIRED")
            await self._context_broker.append(observation)
        snapshot = await self._context_broker.snapshot(
            subject_id=evidence.subject_person_id,
            scope=scope,
            now=now,
            snapshot_ttl=self._assets.snapshot_ttl,
        )
        if not set(input_refs).issubset(snapshot.source_refs):
            raise ContextContractError("GROWTH_PLAN_EVIDENCE_NOT_IN_CONTEXT_SNAPSHOT")

        authorization = self._authorization_resolver("growth_planner", scope, evidence)
        if inspect.isawaitable(authorization):
            authorization = await authorization
        if not isinstance(authorization, AgentAuthorization):
            raise TypeError("authorization_resolver must return AgentAuthorization")

        request_id = _request_id(evidence, scope, self._assets)
        route = self._principal_router.resolve(
            PrincipalRouteRequest(
                request_id=request_id,
                tenant_id=scope.tenant_id,
                actor_type="authorized_guardian",
                entry_point=PrincipalEntryPoint.TWENTY_ONE_DAY_COMPANION,
                capability=PrincipalCapability.GROWTH_PLAN_DRAFT,
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
            route.agent_id != "growth_planner"
            or route.output_type is not PrincipalOutputType.DRAFT
            or route.human_gate is not PrincipalHumanGate.EXPLICIT_CONFIRMATION
        ):
            raise RuntimeError("growth plan Principal route violates reviewed governance")
        task = AgentTask(
            request_id=request_id,
            agent_id=route.agent_id,
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            use_case=PrincipalCapability.GROWTH_PLAN_DRAFT.value,
            context_snapshot_ref=snapshot.snapshot_ref,
            prompt_version=self._assets.prompt_version,
            schema_version=self._assets.schema_version,
            data_class="MINOR_PERSONAL_DATA",
            payload=_payload(evidence, self._assets),
            output_schema=growth_plan_draft_schema(),
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
                or run.use_case != PrincipalCapability.GROWTH_PLAN_DRAFT.value
            ):
                raise RuntimeError("growth plan AgentRun replay binding mismatch")
        if run is None:
            run = await runtime.execute(
                task,
                authorization,
                idempotency_key=f"growth-plan-draft:{request_id}",
            )
        draft = dict(run.draft.output)
        assert_growth_plan_draft_boundary(draft, evidence, input_refs=input_refs)
        draft_identity = ModelDraftIdentity.from_run_id(run.run_id)
        if self._draft_store is not None:
            stored = await self._draft_store.save(
                run=run,
                scope=scope,
                evidence=evidence,
                input_refs=input_refs,
                created_at=run.completed_at,
            )
            if stored.draft_id != draft_identity.draft_id:
                raise RuntimeError("growth plan persisted draft identity mismatch")
        provenance = run.draft.provenance
        return {
            "projection_version": "UI05_AI_PLAN_PREVIEW_V1",
            "family_id": family_id,
            "onboarding_id": evidence.onboarding_id,
            "state": "FAMILY_REVIEW",
            "source_priority_id": evidence.priority_id,
            "structure": draft,
            "ai_state": "MODEL_DRAFT_READY",
            "model_gateway_status": "INVOKED",
            "next_allowed_action": "REQUEST_GUARDIAN_CONFIRMATION",
            "boundary": "PLAN_PREVIEW_IS_AI_DRAFT_NOT_OUTCOME_OR_COMMITMENT",
            "scorecard": {
                "generator": "MODEL_GATEWAY",
                "agent_run_ref": run.run_id,
                "draft_id": draft_identity.draft_id,
                "provenance_ref": draft_identity.provenance_ref,
                "draft_persistence": (
                    "DURABLE" if self._draft_store is not None else "NOT_CONFIGURED"
                ),
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


def assert_growth_plan_draft_boundary(
    draft: Mapping[str, object],
    evidence: GrowthPlanEvidence,
    *,
    input_refs: tuple[str, ...] | None = None,
) -> None:
    if draft.get("draft_status") != "DRAFT":
        raise ValueError("growth plan output must remain DRAFT")
    if draft.get("intent_ref") != evidence.intent_id:
        raise ValueError("growth plan draft intent binding mismatch")
    if draft.get("onboarding_ref") != evidence.onboarding_id:
        raise ValueError("growth plan draft onboarding binding mismatch")
    if draft.get("priority_ref") != evidence.priority_id:
        raise ValueError("growth plan draft priority binding mismatch")
    if draft.get("horizon_days") != 90:
        raise ValueError("growth plan draft horizon must be 90 days")
    labels = draft.get("boundary_labels")
    if not isinstance(labels, list) or not PLAN_DRAFT_BOUNDARIES.issubset(labels):
        raise ValueError("growth plan draft boundary labels missing")
    stages = draft.get("stages")
    if (
        not isinstance(stages, list)
        or tuple(item.get("stage_id") if isinstance(item, dict) else None for item in stages)
        != PLAN_STAGE_IDS
    ):
        raise ValueError("growth plan draft stages are invalid")
    evidence_refs = draft.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise ValueError("growth plan draft evidence refs are required")
    allowed_refs = set(input_refs or growth_plan_input_refs(evidence, None))
    if not set(evidence_refs).issubset(allowed_refs):
        raise ValueError("growth plan draft contains unknown evidence refs")
    for stage_item in stages:
        assert isinstance(stage_item, dict)
        stage_refs = stage_item.get("evidence_refs")
        if not isinstance(stage_refs, list) or not stage_refs:
            raise ValueError("growth plan stage evidence refs are required")
        if not set(stage_refs).issubset(allowed_refs):
            raise ValueError("growth plan stage contains unknown evidence refs")
    pause_policy = draft.get("pause_policy")
    if not isinstance(pause_policy, dict) or (
        pause_policy.get("allowed") is not True or pause_policy.get("streak_penalty") is not False
    ):
        raise ValueError("growth plan draft must allow pause without penalty")
    for key in _walk_keys(draft):
        if key.lower() in _FORBIDDEN_OUTPUT_KEYS:
            raise ValueError(f"growth plan draft forbidden output: {key}")


def growth_plan_draft_schema() -> dict[str, object]:
    stage = {
        "type": "object",
        "required": [
            "stage_id",
            "goal",
            "small_actions",
            "review_prompt",
            "evidence_refs",
        ],
        "properties": {
            "stage_id": {"type": "string", "enum": list(PLAN_STAGE_IDS)},
            "goal": {"type": "string"},
            "small_actions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {"type": "string"},
            },
            "review_prompt": {"type": "string"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "required": [
            "draft_status",
            "intent_ref",
            "onboarding_ref",
            "priority_ref",
            "horizon_days",
            "boundary_labels",
            "stages",
            "pause_policy",
            "evidence_refs",
            "limitations",
        ],
        "properties": {
            "draft_status": {"type": "string", "const": "DRAFT"},
            "intent_ref": {"type": "string"},
            "onboarding_ref": {"type": "string"},
            "priority_ref": {"type": "string"},
            "horizon_days": {"type": "integer", "const": 90},
            "boundary_labels": {"type": "array", "items": {"type": "string"}},
            "stages": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": stage,
            },
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "limitations": {"type": "array", "items": {"type": "string"}},
            "pause_policy": {
                "type": "object",
                "required": ["allowed", "streak_penalty"],
                "properties": {
                    "allowed": {"type": "boolean", "const": True},
                    "streak_penalty": {"type": "boolean", "const": False},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _assert_scope(
    scope: ContextScope,
    family_id: str,
    evidence: GrowthPlanEvidence,
) -> None:
    scope.assert_active()
    if scope.family_id != family_id:
        raise PermissionError("growth plan runtime family scope mismatch")
    if scope.subject_ids != (evidence.subject_person_id,):
        raise PermissionError("growth plan runtime subject scope mismatch")
    if scope.data_class is not DataClass.MINOR_PERSONAL_DATA:
        raise ContextContractError("growth plan runtime requires minor data scope")
    if scope.purpose.lower() != "growth_tracking":
        raise ContextContractError("growth plan runtime requires GROWTH_TRACKING purpose")


def growth_plan_input_refs(
    evidence: GrowthPlanEvidence,
    assets: GrowthPlanAiAssets | None,
) -> tuple[str, ...]:
    template_ref = (
        f"journey-template:{assets.journey_template_ref}@{assets.journey_template_version}"
        if assets is not None
        else "journey-template:family-growth-90d@1.0.0"
    )
    return (
        f"growth-intent:{evidence.intent_id}:{_intent_digest(evidence)}",
        f"growth-onboarding:{evidence.onboarding_id}:v{evidence.onboarding_version}",
        f"growth-priority:{evidence.priority_id}:{evidence.priority_policy_version}:"
        f"{_priority_digest(evidence)}",
        template_ref,
    )


def _payload(
    evidence: GrowthPlanEvidence,
    assets: GrowthPlanAiAssets,
) -> dict[str, object]:
    return {
        "intent_ref": evidence.intent_id,
        "onboarding_ref": evidence.onboarding_id,
        "priority_ref": evidence.priority_id,
        "need_type": evidence.need_type,
        "goal_text": evidence.goal_text,
        "dimension_id": evidence.dimension_id,
        "required_capability_keys": list(evidence.required_capability_keys),
        "horizon_days": 90,
        "stage_ids": list(PLAN_STAGE_IDS),
        "journey_template_ref": assets.journey_template_ref,
        "journey_template_version": assets.journey_template_version,
        "human_gate": "EXPLICIT_CONFIRMATION",
        "output_boundary": "plan_draft_only",
    }


def _request_id(
    evidence: GrowthPlanEvidence,
    scope: ContextScope,
    assets: GrowthPlanAiAssets,
) -> str:
    material = json.dumps(
        {
            "use_case": PrincipalCapability.GROWTH_PLAN_DRAFT.value,
            "agent_id": "growth_planner",
            "tenant_id": scope.tenant_id,
            "family_id": scope.family_id,
            "subject_ids": scope.subject_ids,
            "region_id": scope.region_id,
            "purpose": scope.purpose,
            "consent_version": scope.consent_version,
            "input_refs": growth_plan_input_refs(evidence, assets),
            "evidence_bundle_digest": _evidence_digest(evidence),
            "context_material_digest": _context_material_digest(evidence, assets),
            "prompt_ref": assets.prompt_ref,
            "prompt_version": assets.prompt_version,
            "schema_ref": assets.schema_ref,
            "schema_version": assets.schema_version,
            "release_set_ref": assets.release_set_ref,
            "runtime_config_digest": assets.runtime_config_digest,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"growth-plan-ai-{hashlib.sha256(material.encode()).hexdigest()}"


def _observations(
    scope: ContextScope,
    evidence: GrowthPlanEvidence,
    input_refs: tuple[str, ...],
    assets: GrowthPlanAiAssets,
) -> tuple[StateObservation, ...]:
    materials = (
        (
            "confirmed_growth_intent",
            "journey-domain:confirmed-growth-intent",
            {
                "intent_ref": evidence.intent_id,
                "need_type": evidence.need_type,
                "goal_text": evidence.goal_text,
                "required_capability_keys": evidence.required_capability_keys,
            },
            (input_refs[0],),
        ),
        (
            "growth_onboarding",
            "journey-domain:active-growth-onboarding",
            {
                "onboarding_ref": evidence.onboarding_id,
                "version": evidence.onboarding_version,
            },
            (input_refs[1], input_refs[3]),
        ),
        (
            "active_growth_priority",
            "journey-domain:guardian-confirmed-priority",
            {
                "priority_ref": evidence.priority_id,
                "dimension_id": evidence.dimension_id,
                "policy_version": evidence.priority_policy_version,
                "confirmed_by_actor_id": evidence.priority_confirmed_by_actor_id,
                "confirmed_at": evidence.priority_confirmed_at.isoformat(),
            },
            (input_refs[2],),
        ),
    )
    observations: list[StateObservation] = []
    for dimension, provenance, value, refs in materials:
        digest = hashlib.sha256(
            ":".join(
                (
                    scope.tenant_id,
                    scope.family_id,
                    evidence.subject_person_id,
                    *refs,
                    scope.consent_version,
                )
            ).encode()
        ).hexdigest()[:24]
        observations.append(
            StateObservation(
                observation_id=f"growth-plan-observation:{dimension}:{digest}",
                tenant_id=scope.tenant_id,
                family_id=scope.family_id,
                subject_id=evidence.subject_person_id,
                dimension=dimension,
                observed_value=json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                evidence_refs=refs,
                provenance=provenance,
                observed_at=evidence.confirmed_at,
                data_class=scope.data_class,
                purpose=scope.purpose,
                consent_version=scope.consent_version,
                consent_granted=scope.consent_granted,
                region_id=scope.region_id,
                locale=scope.locale,
                deletion_ref=scope.deletion_ref,
                correlation_id=scope.correlation_id,
                causation_id=f"growth-onboarding:{evidence.onboarding_id}",
                expires_at=evidence.confirmed_at + assets.observation_retention,
                retention_policy="confirmed-growth-intent-plan-draft.v1",
            )
        )
    return tuple(observations)


def _intent_digest(evidence: GrowthPlanEvidence) -> str:
    return _digest(
        {
            "intent_id": evidence.intent_id,
            "subject_person_id": evidence.subject_person_id,
            "need_type": evidence.need_type,
            "goal_text": evidence.goal_text,
            "required_capability_keys": evidence.required_capability_keys,
            "confirmed_by_actor_id": evidence.confirmed_by_actor_id,
            "confirmed_at": evidence.confirmed_at.isoformat(),
            "boundary": evidence.boundary,
        }
    )


def _priority_digest(evidence: GrowthPlanEvidence) -> str:
    return _digest(
        {
            "priority_id": evidence.priority_id,
            "dimension_id": evidence.dimension_id,
            "policy_version": evidence.priority_policy_version,
            "confirmed_by_actor_id": evidence.priority_confirmed_by_actor_id,
            "confirmed_at": evidence.priority_confirmed_at.isoformat(),
        }
    )


def _evidence_digest(evidence: GrowthPlanEvidence) -> str:
    return _digest(
        {
            "intent": _intent_digest(evidence),
            "onboarding_id": evidence.onboarding_id,
            "onboarding_version": evidence.onboarding_version,
            "priority": _priority_digest(evidence),
        }
    )


def _context_material_digest(
    evidence: GrowthPlanEvidence,
    assets: GrowthPlanAiAssets,
) -> str:
    return _digest(
        {
            "evidence_digest": _evidence_digest(evidence),
            "template": f"{assets.journey_template_ref}@{assets.journey_template_version}",
        }
    )


def _digest(value: object) -> str:
    material = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _walk_keys(value: object) -> tuple[str, ...]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(item))
    elif isinstance(value, list | tuple):
        for item in value:
            keys.extend(_walk_keys(item))
    return tuple(keys)


__all__ = [
    "GrowthPlanAiAssets",
    "GrowthPlanAiDraftAdapter",
    "GrowthPlanEvidence",
    "SqlAlchemyGrowthPlanAuthorizationResolver",
    "SqlAlchemyGrowthPlanRunReplayResolver",
    "assert_growth_plan_draft_boundary",
    "growth_plan_draft_schema",
    "growth_plan_input_refs",
]
