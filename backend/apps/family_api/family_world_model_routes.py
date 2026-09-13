"""Demo HTTP surface for the Family World Model cognition pipeline.

This router does not add any new cognition — every step it exposes
(`detect_conflicts`, `generate_hypothesis`, `generate_unknown`,
`resolve_unknown`, `BeliefStateQueryService.get_current_belief_state`) is a
call straight into `backend/intelligence/context_engine/`, wired the same way
`tests/family_journeys/test_family_scene_001.py` exercises it. This module is
deliberately DEMO-ORIENTED, not production-hardened: it accepts a small set of
already-STRUCTURED statements from the frontend (speaker/epistemic_kind/
predicate/text) rather than parsing free text, and it fixes `tenant_id` to a
single demo constant. It must never weaken any consent/scope/governance check
the kernel itself performs — a legitimately failing check surfaces as an
error, not a silently patched-over 200.

Real-model wiring (endpoints 2 and 3) follows the same shape
`ai_coach_wiring.py` uses for its gated real-model livecheck: a real
`OpenAICompatibleProvider` built from environment variables, registered with
an honest `ProviderRecord` in a private `ProviderRegistry`. Nothing in this
module fabricates a `PromptExecutionPlan` or substitutes `FakeProvider` on the
real-provider path — see `build_real_agent_runtime` for why a missing
provider is a fail-closed 503, not a silent fallback.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from backend.apps.family_api.belief_state_wiring import build_belief_state_query_service
from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AuthorizationBudget,
)
from backend.intelligence.agent_runtime.gateway_port import ModelGatewayExecutionPort
from backend.intelligence.agent_runtime.runtime import AgentRuntime
from backend.intelligence.context_engine.belief_engine import (
    HYPOTHESIS_USE_CASE,
    generate_hypothesis,
)
from backend.intelligence.context_engine.conflict_engine import detect_conflicts
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.postgres_conflict_repository import (
    PostgresConflictRepository,
)
from backend.intelligence.context_engine.postgres_unknown_repository import (
    PostgresUnknownRepository,
)
from backend.intelligence.context_engine.postgres_world_state_repository import (
    PostgresWorldStateRepository,
)
from backend.intelligence.context_engine.unknown_engine import (
    UNKNOWN_USE_CASE,
    generate_unknown,
)
from backend.intelligence.context_engine.unknown_resolution import resolve_unknown
from backend.intelligence.context_engine.world_state import (
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway, build_gateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.openai_compatible import (
    build_openai_compatible_provider,
)
from backend.intelligence.safety.runtime import SafetyRuntime
from backend.platform.persistence.session import get_sessionmaker

router = APIRouter(prefix="/families", tags=["family-world-model-demo"])

# --- Fixed demo constants ---------------------------------------------------
#
# This is a demo wiring layer, not a multi-tenant production surface: every
# request is scoped to one fixed tenant/purpose/consent-version so a frontend
# can drive the pipeline without also implementing an identity/consent flow.
DEMO_TENANT_ID = "demo-tenant"
DEMO_PURPOSE = "family_growth_support"
DEMO_CONSENT_VERSION = "consent.v1"
DEMO_LOCALE = "zh-CN"
DEMO_AGENT_ID = "family_world_model_cognition"
DEMO_PROJECTION_VERSION = "family-world-model-demo/v1"

# Real-model wiring: only used if both are set. Named after this task's own
# spec; there is no other place in the repository that reads these two names,
# so this is the one and only place they are defined.
WORLD_MODEL_PROVIDER_ID = "world-model-demo-provider"
WORLD_MODEL_MODEL_NAME_ENV_VAR = "AIFAMILY_MODEL_NAME"
WORLD_MODEL_BASE_URL_ENV_VAR = "AIFAMILY_MODEL_BASE_URL"
WORLD_MODEL_API_KEY_ENV_VAR = "AIFAMILY_MODEL_API_KEY"
DEFAULT_WORLD_MODEL_MODEL_NAME = "gpt-4o-mini"

_SPEAKER_TO_ACTOR: dict[str, WorldStateActorType] = {
    "mother": WorldStateActorType.FAMILY_MEMBER,
    "father": WorldStateActorType.FAMILY_MEMBER,
    "child": WorldStateActorType.FAMILY_MEMBER,
    "self": WorldStateActorType.FAMILY_MEMBER,
}

_ALLOWED_EPISTEMIC_KINDS = frozenset(
    {
        WorldStateEpistemicKind.PERSPECTIVE,
        WorldStateEpistemicKind.SELF_REPORT,
        WorldStateEpistemicKind.OBSERVATION,
        WorldStateEpistemicKind.OTHER_REPORT,
    }
)


# --- DB session dependency --------------------------------------------------
#
# Mirrors the family_need router's convention of a server-owned dependency
# (`get_family_need_actor`/`get_family_need_service` in
# `backend/domains/family_need/api/dependencies.py`): this module owns its own
# `AsyncConnection` dependency rather than inventing a second DB wiring
# pattern. `DATABASE_URL` (not the test-only `AIFAMILY_TEST_DATABASE_URL`) is
# the process database, matching `platform.persistence.session`'s own
# convention used throughout `main.py`.
async def get_world_model_connection() -> AsyncConnection:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        assert isinstance(session, AsyncSession)
        connection = await session.connection()
        try:
            yield connection
            await session.commit()
        except Exception:
            await session.rollback()
            raise


ConnectionDep = Annotated[AsyncConnection, Depends(get_world_model_connection)]


def _demo_scope(*, family_id: str, subject_ids: tuple[str, ...]) -> ContextScope:
    return ContextScope(
        tenant_id=DEMO_TENANT_ID,
        region_id="CN",
        family_id=family_id,
        subject_ids=subject_ids,
        purpose=DEMO_PURPOSE,
        consent_version=DEMO_CONSENT_VERSION,
        consent_granted=True,
        data_class=DataClass.FAMILY_PRIVATE_TEXT,
        locale=DEMO_LOCALE,
        deletion_ref=f"delete:{family_id}",
        correlation_id=str(uuid4()),
        causation_id=str(uuid4()),
    )


def build_real_agent_runtime(*, use_case: str) -> AgentRuntime:
    """Build a real `AgentRuntime` backed by a real `OpenAICompatibleProvider`.

    Raises `HTTPException(503)` when `AIFAMILY_MODEL_API_KEY`/
    `AIFAMILY_MODEL_BASE_URL` are not both set — this endpoint must never
    silently fall back to `FakeProvider`: doing so would let a demo response
    be mistaken for real cognition (see module docstring / task constraints).

    Returns only the `AgentRuntime`, not an `AgentAuthorization`: the
    authorization's `family_id` must exactly equal the task's `family_id`
    (`AgentAuthorizer.authorize`'s `scope_mismatch` check), and `family_id`
    is only known once a request's path parameter is in hand — see
    `_build_authorization`, which each route calls after resolving this
    dependency.

    Exposed as a plain function (not a FastAPI `Depends`) because it needs a
    `use_case` argument that differs per endpoint; each route wraps it as a
    zero-arg dependency via `get_hypothesis_agent_runtime`/
    `get_unknown_agent_runtime`, which is the seam a test overrides to inject
    a `FakeProvider`-backed runtime instead of a real network call — see
    `tests/apps/family_api/test_family_world_model_routes.py`.
    """

    base_url = os.environ.get(WORLD_MODEL_BASE_URL_ENV_VAR, "").strip()
    api_key = os.environ.get(WORLD_MODEL_API_KEY_ENV_VAR, "").strip()
    if not base_url or not api_key:
        missing = [
            name
            for name, value in (
                (WORLD_MODEL_BASE_URL_ENV_VAR, base_url),
                (WORLD_MODEL_API_KEY_ENV_VAR, api_key),
            )
            if not value
        ]
        raise HTTPException(
            status_code=503,
            detail=(
                "world_model_no_real_model_provider_configured: missing environment "
                f"variable(s) {missing}. This endpoint refuses to fall back to a fake "
                "provider for real cognition output; configure a real, §16-assessed "
                "provider to use this endpoint."
            ),
        )
    model_name = os.environ.get(WORLD_MODEL_MODEL_NAME_ENV_VAR, "").strip() or (
        DEFAULT_WORLD_MODEL_MODEL_NAME
    )

    provider = build_openai_compatible_provider(
        provider_id=WORLD_MODEL_PROVIDER_ID,
        model=model_name,
        base_url_env_var=WORLD_MODEL_BASE_URL_ENV_VAR,
        credential_env_var=WORLD_MODEL_API_KEY_ENV_VAR,
    )
    registry = ProviderRegistry(
        (
            ProviderRecord(
                provider_id=WORLD_MODEL_PROVIDER_ID,
                vendor="openai-compatible",
                model=model_name,
                model_version=model_name,
                status="INTERNAL_APPROVED",
                approved_environments=("internal_livecheck",),
                # No completed 《儿童个人信息网络保护规定》第16条 security
                # assessment/processing agreement exists for this demo
                # provider — sub_delegates stays unestablished (None), which
                # `admit()` treats as prohibitive for FAMILY_PRIVATE_TEXT.
                # This is an honest statement of this demo's compliance
                # posture, not a workaround for it.
                sub_delegates=None,
                minor_data_allowed=False,
                private_text_allowed=False,
                processing_region="unspecified",
                credential_env_var=WORLD_MODEL_API_KEY_ENV_VAR,
                base_url_env_var=WORLD_MODEL_BASE_URL_ENV_VAR,
                timeout_seconds=30.0,
                notes=(
                    "Family World Model demo router provider; no §16 assessment exists, "
                    "so admission rejects FAMILY_PRIVATE_TEXT/MINOR_PERSONAL_DATA "
                    "regardless of this record's status/environment fields."
                ),
            ),
        )
    )
    gateway: ModelGateway = build_gateway(
        environment="internal_livecheck",
        providers={WORLD_MODEL_PROVIDER_ID: provider},
        registry=registry,
        safety_runtime=SafetyRuntime(),
    )
    definition = AgentDefinition(
        agent_id=DEMO_AGENT_ID,
        name="Family World Model Cognition (demo)",
        allowed_use_cases=frozenset({use_case}),
        context_policy="family-world-model-demo-context-policy",
        safety_policy="family-world-model-demo-safety-policy",
        human_handoff_policy="family-world-model-demo-handoff-policy",
        budget_policy="family-world-model-demo-budget-policy",
    )
    return AgentRuntime(
        ModelGatewayExecutionPort(gateway, WORLD_MODEL_PROVIDER_ID),
        [definition],
    )


def _build_authorization(*, use_case: str, family_id: str) -> AgentAuthorization:
    """Build the per-request `AgentAuthorization` for `family_id`.

    Deliberately built fresh per request (never cached alongside the
    runtime): `AgentAuthorizer.authorize` requires `authorization.family_id
    == task.family_id` exactly, and `family_id` is only known once a
    request's path parameter is in hand.
    """

    now = datetime.now(UTC)
    return AgentAuthorization(
        authorization_id=f"auth-world-model-demo-{uuid4().hex}",
        agent_id=DEMO_AGENT_ID,
        tenant_id=DEMO_TENANT_ID,
        family_id=family_id,
        allowed_use_cases=frozenset({use_case}),
        allowed_tools=frozenset(),
        issued_by="family-world-model-demo-router",
        issued_at=now,
        expires_at=now.replace(year=now.year + 1),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="family-world-model-demo/v1",
        reason="demo world model cognition request",
        audit_ref=f"audit-world-model-demo-{uuid4().hex}",
    )


def get_hypothesis_agent_runtime() -> AgentRuntime:
    """FastAPI dependency seam for the Belief Engine's `AgentRuntime`.

    Kept separate from `get_unknown_agent_runtime` (even though both simply
    call `build_real_agent_runtime` with a different `use_case`) so a test
    can override exactly one of the two pipelines with `FakeProvider` without
    affecting the other.
    """

    return build_real_agent_runtime(use_case=HYPOTHESIS_USE_CASE)


def get_unknown_agent_runtime() -> AgentRuntime:
    """FastAPI dependency seam for the Unknown Engine's `AgentRuntime`."""

    return build_real_agent_runtime(use_case=UNKNOWN_USE_CASE)


HypothesisRuntimeDep = Annotated[AgentRuntime, Depends(get_hypothesis_agent_runtime)]
UnknownRuntimeDep = Annotated[AgentRuntime, Depends(get_unknown_agent_runtime)]


# --- Request/response models ------------------------------------------------


class StatementBody(BaseModel):
    """One structured statement — the demo's stand-in for NLP-parsed free text."""

    model_config = ConfigDict(extra="forbid")

    speaker: Literal["mother", "father", "child", "self"]
    epistemic_kind: Literal["PERSPECTIVE", "SELF_REPORT", "OBSERVATION", "OTHER_REPORT"]
    predicate: str = Field(min_length=1, max_length=256)
    text: str = Field(min_length=1, max_length=2_000)
    subject_ids: tuple[str, ...] = Field(min_length=1)


class SubmitStatementsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statements: tuple[StatementBody, ...] = Field(min_length=1)


def _serialize_atom(atom: WorldStateAtom) -> dict:
    return {
        "atom_id": atom.atom_id,
        "subject_ids": list(atom.subject_ids),
        "epistemic_kind": atom.epistemic_kind.value,
        "predicate": atom.predicate,
        "value_ref": atom.value_ref,
        "asserted_by": atom.asserted_by,
        "attributed_actor_type": atom.attributed_actor_type.value,
        "provenance": atom.provenance,
        "recorded_at": atom.recorded_at.isoformat(),
        "support_level": atom.support_level.value if atom.support_level else None,
        "contradiction_level": (
            atom.contradiction_level.value if atom.contradiction_level else None
        ),
        "uncertainty": atom.uncertainty.value if atom.uncertainty else None,
        "evidence_refs": list(atom.evidence_refs),
        "source_refs": list(atom.source_refs),
    }


def _atom_from_statement(body: StatementBody, *, family_id: str, now: datetime) -> WorldStateAtom:
    scope = _demo_scope(family_id=family_id, subject_ids=body.subject_ids)
    epistemic_kind = WorldStateEpistemicKind(body.epistemic_kind)
    if epistemic_kind not in _ALLOWED_EPISTEMIC_KINDS:
        raise HTTPException(
            status_code=400, detail=f"unsupported_epistemic_kind:{epistemic_kind.value}"
        )
    provenance = f"demo-statement:{body.speaker}:{uuid4().hex}"
    return WorldStateAtom(
        atom_id=f"atom-{uuid4().hex}",
        scope=scope,
        subject_ids=body.subject_ids,
        epistemic_kind=epistemic_kind,
        predicate=body.predicate,
        value_ref=body.text,
        asserted_by=body.speaker,
        attributed_actor_type=_SPEAKER_TO_ACTOR[body.speaker],
        provenance=provenance,
        observed_at=now,
        recorded_at=now,
        valid_from=now,
        source_refs=(provenance,),
    )


@router.post("/{family_id}/world-model/statements", status_code=201)
async def submit_statements(
    family_id: str,
    body: SubmitStatementsBody,
    connection: ConnectionDep,
) -> dict:
    """Persist a small batch of structured statements, then detect conflicts.

    Each statement becomes one real `WorldStateAtom`, appended via
    `PostgresWorldStateRepository.append_atom`. `detect_conflicts()` then runs
    over the atoms just submitted (deterministic, no model call); any
    detected `WorldStateConflict` is persisted via
    `PostgresConflictRepository.append_conflict`.
    """

    now = datetime.now(UTC)
    world_repo = PostgresWorldStateRepository(connection)
    conflict_repo = PostgresConflictRepository(connection)

    atoms: list[WorldStateAtom] = []
    for statement in body.statements:
        atom = _atom_from_statement(statement, family_id=family_id, now=now)
        try:
            result = await world_repo.append_atom(
                atom,
                source_ref=atom.provenance,
                source_version="v1",
                projection_version=DEMO_PROJECTION_VERSION,
            )
        except Exception as exc:  # noqa: BLE001 - surface a governed 400, not a 500
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # `append_atom` may replay an already-persisted atom under a
        # different atom_id (idempotent replay); reflect the atom that is
        # actually durable, not the caller's transient in-memory one.
        if result.atom_id != atom.atom_id:
            stored = await world_repo.get_atom(result.atom_id, scope=atom.scope)
            if stored is not None:
                atom = stored
        atoms.append(atom)

    conflicts = detect_conflicts(tuple(atoms), detected_at=now)
    for conflict in conflicts:
        await conflict_repo.append_conflict(conflict)

    return {
        "family_id": family_id,
        "atoms": [_serialize_atom(a) for a in atoms],
        "conflicts": [
            {
                "conflict_id": c.conflict_id,
                "predicate": c.predicate,
                "atom_ids": list(c.atom_ids),
                "conflict_type": c.conflict_type.value,
                "status": c.status.value,
                "detected_at": c.detected_at.isoformat(),
            }
            for c in conflicts
        ],
    }


class GenerateHypothesisBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_ids: tuple[str, ...] = Field(min_length=1)
    target_predicate: str = Field(min_length=1, max_length=256)
    evidence_atom_ids: tuple[str, ...] = Field(min_length=1)


@router.post("/{family_id}/world-model/hypothesis", status_code=201)
async def create_hypothesis(
    family_id: str,
    body: GenerateHypothesisBody,
    connection: ConnectionDep,
    agent_runtime: HypothesisRuntimeDep,
) -> dict:
    """Run the Belief Engine over caller-selected evidence atoms.

    Requires a real model provider (`AIFAMILY_MODEL_API_KEY`/
    `AIFAMILY_MODEL_BASE_URL`) — see `build_real_agent_runtime`. Without one
    this fails closed with 503 rather than silently using `FakeProvider`.
    """

    scope = _demo_scope(family_id=family_id, subject_ids=body.subject_ids)
    world_repo = PostgresWorldStateRepository(connection)

    evidence_atoms: list[WorldStateAtom] = []
    for atom_id in body.evidence_atom_ids:
        atom = await world_repo.get_atom(atom_id, scope=scope)
        if atom is None:
            raise HTTPException(status_code=404, detail=f"evidence_atom_not_found:{atom_id}")
        evidence_atoms.append(atom)

    authorization = _build_authorization(use_case=HYPOTHESIS_USE_CASE, family_id=family_id)
    now = datetime.now(UTC)
    try:
        hypothesis = await generate_hypothesis(
            agent_runtime,
            agent_id=DEMO_AGENT_ID,
            authorization=authorization,
            request_id=f"request-hypothesis-{uuid4().hex}",
            evidence_atoms=tuple(evidence_atoms),
            scope=scope,
            subject_ids=body.subject_ids,
            context_snapshot_ref=f"family-world-model-demo:{family_id}:{uuid4().hex}",
            proposal_id=f"proposal-{uuid4().hex}",
            atom_id=f"hypothesis-{uuid4().hex}",
            target_predicate=body.target_predicate,
            now=now,
        )
    except ModelGatewayError as exc:
        raise HTTPException(
            status_code=502, detail=f"world_model_hypothesis_model_gateway_failed:{exc.kind}"
        ) from None

    await world_repo.append_atom(
        hypothesis,
        source_ref=hypothesis.provenance,
        source_version="v1",
        projection_version=DEMO_PROJECTION_VERSION,
    )

    return {"family_id": family_id, "hypothesis": _serialize_atom(hypothesis)}


class GenerateUnknownBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_ids: tuple[str, ...] = Field(min_length=1)
    hypothesis_atom_ids: tuple[str, ...] = Field(min_length=1)
    allowed_target_predicates: tuple[str, ...] = Field(min_length=1)


@router.post("/{family_id}/world-model/unknown", status_code=201)
async def create_unknown(
    family_id: str,
    body: GenerateUnknownBody,
    connection: ConnectionDep,
    agent_runtime: UnknownRuntimeDep,
) -> dict:
    """Run the Unknown Engine over caller-selected hypothesis atoms.

    Returns `unknown: null` when the model's proposal deduplicates against an
    already-OPEN Unknown (`generate_unknown` returning `None` is a legitimate
    outcome, not an error — see that function's own docstring). Requires a
    real model provider, same as `create_hypothesis`.
    """

    scope = _demo_scope(family_id=family_id, subject_ids=body.subject_ids)
    world_repo = PostgresWorldStateRepository(connection)
    unknown_repo = PostgresUnknownRepository(connection)

    hypotheses: list[WorldStateAtom] = []
    for atom_id in body.hypothesis_atom_ids:
        atom = await world_repo.get_atom(atom_id, scope=scope)
        if atom is None:
            raise HTTPException(status_code=404, detail=f"hypothesis_atom_not_found:{atom_id}")
        if atom.epistemic_kind is not WorldStateEpistemicKind.HYPOTHESIS:
            raise HTTPException(status_code=400, detail=f"atom_is_not_a_hypothesis:{atom_id}")
        hypotheses.append(atom)

    existing_unknowns = await unknown_repo.list_open(scope=scope)

    authorization = _build_authorization(use_case=UNKNOWN_USE_CASE, family_id=family_id)
    now = datetime.now(UTC)
    try:
        unknown = await generate_unknown(
            agent_runtime,
            agent_id=DEMO_AGENT_ID,
            authorization=authorization,
            request_id=f"request-unknown-{uuid4().hex}",
            hypotheses=tuple(hypotheses),
            allowed_target_predicates=body.allowed_target_predicates,
            existing_unknowns=existing_unknowns,
            scope=scope,
            subject_ids=body.subject_ids,
            context_snapshot_ref=f"family-world-model-demo:{family_id}:{uuid4().hex}",
            unknown_id=f"unknown-{uuid4().hex}",
            now=now,
        )
    except ModelGatewayError as exc:
        raise HTTPException(
            status_code=502, detail=f"world_model_unknown_model_gateway_failed:{exc.kind}"
        ) from None

    if unknown is None:
        return {"family_id": family_id, "unknown": None}

    persisted = await unknown_repo.create(unknown)
    return {
        "family_id": family_id,
        "unknown": {
            "unknown_id": persisted.unknown_id,
            "subject_ids": list(persisted.subject_ids),
            "question": persisted.question,
            "why_it_matters": persisted.why_it_matters,
            "target_predicate": persisted.target_predicate,
            "decision_impact": persisted.decision_impact,
            "answerability": persisted.answerability,
            "urgency": persisted.urgency,
            "preferred_source": persisted.preferred_source,
            "blocking_refs": list(persisted.blocking_refs),
            "priority": persisted.priority,
            "status": persisted.status.value,
            "created_at": persisted.created_at.isoformat() if persisted.created_at else None,
        },
    }


class ResolveUnknownBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clarification: StatementBody


@router.post("/{family_id}/world-model/unknown/{unknown_id}/resolve")
async def resolve_unknown_route(
    family_id: str,
    unknown_id: str,
    body: ResolveUnknownBody,
    connection: ConnectionDep,
) -> dict:
    """Persist a new clarification statement, then resolve the Unknown with it.

    The clarification is projected into a real, durable `WorldStateAtom`
    first (never accepted as a raw string) — `resolve_unknown()` then
    re-validates it against the Unknown's own evidence-gate rules (real,
    new, non-AI-authored, addresses the target predicate) before the Unknown
    transitions to RESOLVED. A legitimate gate failure (e.g. evidence does
    not address the Unknown's target predicate) surfaces as 400, not a
    silently accepted resolution.
    """

    now = datetime.now(UTC)
    clarification_atom = _atom_from_statement(body.clarification, family_id=family_id, now=now)
    world_repo = PostgresWorldStateRepository(connection)
    unknown_repo = PostgresUnknownRepository(connection)

    result = await world_repo.append_atom(
        clarification_atom,
        source_ref=clarification_atom.provenance,
        source_version="v1",
        projection_version=DEMO_PROJECTION_VERSION,
    )
    if result.atom_id != clarification_atom.atom_id:
        stored = await world_repo.get_atom(result.atom_id, scope=clarification_atom.scope)
        if stored is not None:
            clarification_atom = stored

    try:
        resolved = await resolve_unknown(
            unknown_repository=unknown_repo,
            world_state_repository=world_repo,
            unknown_id=unknown_id,
            scope=clarification_atom.scope,
            resolution_atom_ids=(clarification_atom.atom_id,),
            resolved_at=now,
        )
    except Exception as exc:  # noqa: BLE001 - surface the kernel's own fail-closed error
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "family_id": family_id,
        "clarification_atom": _serialize_atom(clarification_atom),
        "unknown": {
            "unknown_id": resolved.unknown_id,
            "status": resolved.status.value,
            "resolution_refs": list(resolved.resolution_refs),
            "resolved_at": resolved.resolved_at.isoformat() if resolved.resolved_at else None,
        },
    }


class BeliefStateSubjectsQuery(BaseModel):
    """Query params are plain strings over HTTP; this model documents the shape
    the frontend must send, but FastAPI resolves the actual query params
    directly (see `get_belief_state` below) rather than via this class."""

    model_config = ConfigDict(extra="forbid")

    subject_ids: tuple[str, ...]


def _serialize_conflict(conflict) -> dict:
    return {
        "conflict_id": conflict.conflict_id,
        "predicate": conflict.predicate,
        "atom_ids": list(conflict.atom_ids),
        "conflict_type": conflict.conflict_type.value,
        "status": conflict.status.value,
        "detected_at": conflict.detected_at.isoformat(),
        "resolution_note": conflict.resolution_note,
    }


def _serialize_unknown(unknown) -> dict:
    return {
        "unknown_id": unknown.unknown_id,
        "subject_ids": list(unknown.subject_ids),
        "question": unknown.question,
        "why_it_matters": unknown.why_it_matters,
        "target_predicate": unknown.target_predicate,
        "decision_impact": unknown.decision_impact,
        "answerability": unknown.answerability,
        "urgency": unknown.urgency,
        "preferred_source": unknown.preferred_source,
        "blocking_refs": list(unknown.blocking_refs),
        "priority": unknown.priority,
        "status": unknown.status.value,
        "resolution_refs": list(unknown.resolution_refs),
        "created_at": unknown.created_at.isoformat() if unknown.created_at else None,
        "resolved_at": unknown.resolved_at.isoformat() if unknown.resolved_at else None,
    }


@router.get("/{family_id}/world-model/belief-state")
async def get_belief_state(
    family_id: str,
    subject_ids: str,
    connection: ConnectionDep,
) -> dict:
    """Return the family's current `FamilyBeliefState` as structured JSON.

    `subject_ids` is a comma-separated list of subject ids in scope for this
    read (e.g. `child-1,mother-1,father-1`) — HTTP query params are strings,
    so this is the one place this router parses a delimited string rather
    than accepting a JSON body.

    Every item explicitly carries its own `epistemic_kind` (and, for
    HYPOTHESIS, `support_level`/`contradiction_level`/`uncertainty`) — a
    HYPOTHESIS is never collapsed into a bare string indistinguishable from
    a FACT.
    """

    parsed_subject_ids = tuple(s for s in (part.strip() for part in subject_ids.split(",")) if s)
    if not parsed_subject_ids:
        raise HTTPException(status_code=400, detail="subject_ids_required")
    scope = _demo_scope(family_id=family_id, subject_ids=parsed_subject_ids)

    async with build_belief_state_query_service(connection) as query_service:
        belief_state = await query_service.get_current_belief_state(
            scope=scope,
            snapshot_ref=f"family-world-model-demo:{family_id}:belief-state:{uuid4().hex}",
        )

    return {
        "family_id": family_id,
        "as_of": belief_state.snapshot.as_of.isoformat(),
        "facts": [_serialize_atom(a) for a in belief_state.facts],
        "observations": [_serialize_atom(a) for a in belief_state.observations],
        "self_reports": [_serialize_atom(a) for a in belief_state.self_reports],
        "other_reports": [_serialize_atom(a) for a in belief_state.other_reports],
        "perspectives": [_serialize_atom(a) for a in belief_state.perspectives],
        "hypotheses": [_serialize_atom(a) for a in belief_state.hypotheses],
        "effective_open_conflicts": [
            _serialize_conflict(c) for c in belief_state.effective_open_conflicts
        ],
        "effective_open_unknowns": [
            _serialize_unknown(u) for u in belief_state.effective_open_unknowns
        ],
    }


__all__ = [
    "BeliefStateSubjectsQuery",
    "GenerateHypothesisBody",
    "GenerateUnknownBody",
    "ResolveUnknownBody",
    "StatementBody",
    "SubmitStatementsBody",
    "build_real_agent_runtime",
    "get_hypothesis_agent_runtime",
    "get_unknown_agent_runtime",
    "get_world_model_connection",
    "router",
]
