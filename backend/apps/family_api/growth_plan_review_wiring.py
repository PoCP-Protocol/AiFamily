"""Immutable UI-05 plan-draft envelope and Human Gate submission boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import JSON, Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.apps.family_api.growth_plan_ai_wiring import GrowthPlanEvidence
from backend.intelligence.agent_runtime.contracts import AgentRun
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.human_gate import (
    ActionProposal,
    ActorType,
    GateScope,
    HumanTask,
    SqlAlchemyHumanGate,
)
from backend.intelligence.model_gateway.provenance import (
    ModelDraftIdentity,
    ModelDraftScope,
    SqlAlchemyModelDraftRegistry,
    StoredModelDraft,
)
from backend.platform.audit import AuditRecorder

CREATE_JOURNEY_PLAN_ACTION = "CREATE_JOURNEY_PLAN_FROM_AI_DRAFT"
REVIEW_RETENTION_POLICY = "growth-plan-human-review.v1"
_STAGE_IDS = ("SEE", "PARENT_FIRST", "CO_CREATE", "STABILIZE")


class GrowthPlanReviewError(ValueError):
    """The persisted draft cannot safely enter guardian review."""


class GrowthPlanReviewNotFound(LookupError):
    """The draft is absent or outside the current trusted scope."""


class GrowthPlanReviewBase(DeclarativeBase):
    """Metadata boundary for the UI-05 review envelope."""


class GrowthPlanDraftReviewRow(GrowthPlanReviewBase):
    __tablename__ = "ai_growth_plan_draft_reviews"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "family_id",
            "request_id",
            name="uq_ai_growth_plan_review_request",
        ),
        sa.CheckConstraint(
            "status = 'DRAFT'",
            name="ck_ai_growth_plan_review_draft_only",
        ),
        sa.CheckConstraint(
            "may_mutate_business_state = false",
            name="ck_ai_growth_plan_review_cannot_mutate",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_ai_growth_plan_review_positive_ttl",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    draft_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    agent_run_id: Mapped[str] = mapped_column(String(160), nullable=False)
    provenance_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    family_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    region_id: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_person_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(96), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(160), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(32), nullable=False)
    deletion_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    generation_correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_payload: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    intent_id: Mapped[str] = mapped_column(String(160), nullable=False)
    onboarding_id: Mapped[str] = mapped_column(String(160), nullable=False)
    priority_id: Mapped[str] = mapped_column(String(160), nullable=False)
    input_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    stable_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    may_mutate_business_state: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    retention_policy: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class StoredGrowthPlanDraft:
    identity: ModelDraftIdentity
    request_id: str
    agent_run_id: str
    tenant_id: str
    family_id: str
    region_id: str
    subject_person_id: str
    purpose: str
    consent_version: str
    data_class: str
    locale: str
    deletion_ref: str
    generation_correlation_id: str
    scope_payload: dict[str, str]
    intent_id: str
    onboarding_id: str
    priority_id: str
    input_refs: tuple[str, ...]
    model_draft: StoredModelDraft
    stable_digest: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class SqlAlchemyGrowthPlanDraftRegistry:
    """Atomically persist ModelDraft plus its review-specific immutable envelope."""

    session_factory: async_sessionmaker[AsyncSession]
    retention_ttl: timedelta = timedelta(days=30)

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("growth plan draft registry requires async_sessionmaker")
        if self.retention_ttl <= timedelta(0):
            raise ValueError("growth plan draft retention TTL must be positive")

    async def save(
        self,
        *,
        run: AgentRun,
        scope: ContextScope,
        evidence: GrowthPlanEvidence,
        input_refs: tuple[str, ...],
        created_at: datetime,
    ) -> ModelDraftIdentity:
        _assert_generation_scope(run, scope, evidence, input_refs, created_at)
        identity = ModelDraftIdentity.from_run_id(run.run_id)
        expires_at = created_at + self.retention_ttl
        async with self.session_factory() as session:
            model_draft = await SqlAlchemyModelDraftRegistry(session).save(
                draft_id=identity.draft_id,
                provenance_ref=identity.provenance_ref,
                scope=ModelDraftScope(
                    tenant_id=scope.tenant_id,
                    family_id=scope.family_id,
                    subject_person_id=evidence.subject_person_id,
                    purpose=scope.purpose,
                    correlation_id=scope.correlation_id,
                ),
                draft=run.draft,
                created_at=created_at,
            )
            incoming = _stored_from_material(
                identity=identity,
                run=run,
                scope=scope,
                evidence=evidence,
                input_refs=input_refs,
                model_draft=model_draft,
                created_at=created_at,
                expires_at=expires_at,
            )
            existing = await session.get(
                GrowthPlanDraftReviewRow,
                {"tenant_id": scope.tenant_id, "draft_id": identity.draft_id},
            )
            if existing is not None:
                persisted = await self.resolve_in_session(
                    session,
                    scope=scope,
                    draft_id=identity.draft_id,
                    now=created_at,
                )
                if persisted != incoming:
                    raise GrowthPlanReviewError("GROWTH_PLAN_DRAFT_REPLAY_MISMATCH")
                await session.commit()
                return identity
            session.add(_row(incoming))
            await session.flush()
            await session.commit()
        return identity

    async def resolve(
        self,
        *,
        scope: ContextScope,
        draft_id: str,
        now: datetime,
    ) -> StoredGrowthPlanDraft:
        async with self.session_factory() as session:
            return await self.resolve_in_session(
                session,
                scope=scope,
                draft_id=draft_id,
                now=now,
            )

    async def resolve_in_session(
        self,
        session: AsyncSession,
        *,
        scope: ContextScope,
        draft_id: str,
        now: datetime,
    ) -> StoredGrowthPlanDraft:
        _assert_review_scope(scope)
        _require_aware(now, "now")
        if not isinstance(draft_id, str) or not draft_id.strip():
            raise GrowthPlanReviewError("GROWTH_PLAN_DRAFT_ID_REQUIRED")
        row = await session.get(
            GrowthPlanDraftReviewRow,
            {"tenant_id": scope.tenant_id, "draft_id": draft_id},
        )
        if row is None or not _row_visible(row, scope):
            raise GrowthPlanReviewNotFound(draft_id)
        if row.status != "DRAFT" or row.may_mutate_business_state:
            raise GrowthPlanReviewError("GROWTH_PLAN_DRAFT_PERSISTED_STATE_INVALID")
        if _utc(now) >= _utc(row.expires_at):
            raise GrowthPlanReviewError("GROWTH_PLAN_DRAFT_EXPIRED")
        model_draft = await SqlAlchemyModelDraftRegistry(session).resolve_stored(
            row.provenance_ref,
            tenant_id=row.tenant_id,
            family_id=row.family_id,
            subject_person_id=row.subject_person_id,
            purpose=row.purpose,
            correlation_id=row.generation_correlation_id,
        )
        stored = _stored(row, model_draft)
        if stored.stable_digest != _stable_digest(stored):
            raise GrowthPlanReviewError("GROWTH_PLAN_DRAFT_DIGEST_MISMATCH")
        return stored


@dataclass(frozen=True, slots=True)
class GrowthPlanHumanGateApplication:
    """Load a server-owned envelope and create one replayable guardian task."""

    session_factory: async_sessionmaker[AsyncSession]
    clock: Callable[[], datetime]
    review_ttl: timedelta = timedelta(days=7)

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("growth plan review requires async_sessionmaker")
        if not callable(self.clock):
            raise TypeError("growth plan review clock must be callable")
        if self.review_ttl <= timedelta(0):
            raise ValueError("growth plan review TTL must be positive")

    async def submit(self, *, scope: ContextScope, draft_id: str) -> HumanTask:
        now = self.clock()
        _require_aware(now, "now")
        registry = SqlAlchemyGrowthPlanDraftRegistry(self.session_factory)
        async with self.session_factory() as session:
            stored = await registry.resolve_in_session(
                session,
                scope=scope,
                draft_id=draft_id,
                now=now,
            )
            proposal = _proposal(stored, scope, now, self.review_ttl)
            recorder = AuditRecorder()
            gate = SqlAlchemyHumanGate(session)
            task = await gate.submit(proposal, recorder=recorder)
            await gate.flush_audit(recorder)
            await gate.commit()
            return task


def _assert_generation_scope(
    run: AgentRun,
    scope: ContextScope,
    evidence: GrowthPlanEvidence,
    input_refs: tuple[str, ...],
    created_at: datetime,
) -> None:
    _assert_review_scope(scope)
    _require_aware(created_at, "created_at")
    if run.tenant_id != scope.tenant_id or run.family_id != scope.family_id:
        raise GrowthPlanReviewError("GROWTH_PLAN_RUN_SCOPE_MISMATCH")
    if run.use_case != "growth_plan_draft" or run.draft.status != "DRAFT":
        raise GrowthPlanReviewError("GROWTH_PLAN_RUN_BOUNDARY_INVALID")
    if run.draft.may_mutate_business_state:
        raise GrowthPlanReviewError("GROWTH_PLAN_DRAFT_CANNOT_MUTATE")
    if scope.subject_ids != (evidence.subject_person_id,):
        raise GrowthPlanReviewError("GROWTH_PLAN_SUBJECT_SCOPE_MISMATCH")
    if not input_refs or any(not value.strip() for value in input_refs):
        raise GrowthPlanReviewError("GROWTH_PLAN_INPUT_REFS_REQUIRED")


def _assert_review_scope(scope: ContextScope) -> None:
    scope.assert_active()
    if scope.subject_id is None:
        raise GrowthPlanReviewError("SINGLE_GROWTH_PLAN_SUBJECT_REQUIRED")
    if scope.purpose.lower() != "growth_tracking":
        raise GrowthPlanReviewError("GROWTH_TRACKING_SCOPE_REQUIRED")
    if scope.data_class is not DataClass.MINOR_PERSONAL_DATA:
        raise GrowthPlanReviewError("MINOR_PERSONAL_DATA_SCOPE_REQUIRED")


def _stored_from_material(
    *,
    identity: ModelDraftIdentity,
    run: AgentRun,
    scope: ContextScope,
    evidence: GrowthPlanEvidence,
    input_refs: tuple[str, ...],
    model_draft: StoredModelDraft,
    created_at: datetime,
    expires_at: datetime,
) -> StoredGrowthPlanDraft:
    provisional = StoredGrowthPlanDraft(
        identity=identity,
        request_id=run.request_id,
        agent_run_id=run.run_id,
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        region_id=scope.region_id,
        subject_person_id=evidence.subject_person_id,
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        data_class=scope.data_class.value,
        locale=scope.locale,
        deletion_ref=scope.deletion_ref,
        generation_correlation_id=scope.correlation_id,
        scope_payload=_scope_payload(scope),
        intent_id=evidence.intent_id,
        onboarding_id=evidence.onboarding_id,
        priority_id=evidence.priority_id,
        input_refs=input_refs,
        model_draft=model_draft,
        stable_digest="pending",
        created_at=_utc(created_at),
        expires_at=_utc(expires_at),
    )
    return _replace_digest(provisional, _stable_digest(provisional))


def _row(stored: StoredGrowthPlanDraft) -> GrowthPlanDraftReviewRow:
    return GrowthPlanDraftReviewRow(
        tenant_id=stored.tenant_id,
        draft_id=stored.identity.draft_id,
        request_id=stored.request_id,
        agent_run_id=stored.agent_run_id,
        provenance_ref=stored.identity.provenance_ref,
        family_id=stored.family_id,
        region_id=stored.region_id,
        subject_person_id=stored.subject_person_id,
        purpose=stored.purpose,
        consent_version=stored.consent_version,
        data_class=stored.data_class,
        locale=stored.locale,
        deletion_ref=stored.deletion_ref,
        generation_correlation_id=stored.generation_correlation_id,
        scope_payload=stored.scope_payload,
        intent_id=stored.intent_id,
        onboarding_id=stored.onboarding_id,
        priority_id=stored.priority_id,
        input_refs=list(stored.input_refs),
        stable_digest=stored.stable_digest,
        status="DRAFT",
        may_mutate_business_state=False,
        retention_policy=REVIEW_RETENTION_POLICY,
        created_at=stored.created_at,
        expires_at=stored.expires_at,
    )


def _stored(row: GrowthPlanDraftReviewRow, model_draft: StoredModelDraft) -> StoredGrowthPlanDraft:
    if row.retention_policy != REVIEW_RETENTION_POLICY:
        raise GrowthPlanReviewError("GROWTH_PLAN_RETENTION_POLICY_INVALID")
    return StoredGrowthPlanDraft(
        identity=ModelDraftIdentity(row.draft_id, row.provenance_ref),
        request_id=row.request_id,
        agent_run_id=row.agent_run_id,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        region_id=row.region_id,
        subject_person_id=row.subject_person_id,
        purpose=row.purpose,
        consent_version=row.consent_version,
        data_class=row.data_class,
        locale=row.locale,
        deletion_ref=row.deletion_ref,
        generation_correlation_id=row.generation_correlation_id,
        scope_payload=dict(row.scope_payload),
        intent_id=row.intent_id,
        onboarding_id=row.onboarding_id,
        priority_id=row.priority_id,
        input_refs=tuple(row.input_refs),
        model_draft=model_draft,
        stable_digest=row.stable_digest,
        created_at=_utc(row.created_at),
        expires_at=_utc(row.expires_at),
    )


def _row_visible(row: GrowthPlanDraftReviewRow, scope: ContextScope) -> bool:
    return (
        row.family_id == scope.family_id
        and row.region_id == scope.region_id
        and row.subject_person_id == scope.subject_ids[0]
        and row.purpose == scope.purpose
        and row.consent_version == scope.consent_version
        and row.data_class == scope.data_class.value
        and row.locale == scope.locale
        and row.deletion_ref == scope.deletion_ref
        and _scope_payload_visible(row.scope_payload, scope)
    )


def _proposal(
    stored: StoredGrowthPlanDraft,
    scope: ContextScope,
    now: datetime,
    review_ttl: timedelta,
) -> ActionProposal:
    output = dict(stored.model_draft.draft.output)
    arguments = _action_arguments(stored, output)
    expiry = min(_utc(now + review_ttl), stored.expires_at)
    return ActionProposal(
        proposal_id=f"growth-plan-proposal:{stored.stable_digest}",
        draft_id=stored.identity.draft_id,
        draft_status="DRAFT",
        action_name=CREATE_JOURNEY_PLAN_ACTION,
        action_arguments=arguments,
        scope=GateScope(
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            subject_ids=scope.subject_ids,
            purpose=scope.purpose,
            consent_version=scope.consent_version,
            correlation_id=scope.correlation_id,
        ),
        allowed_actor_types=(ActorType.GUARDIAN,),
        risk_level="HIGH",
        provenance_ref=stored.identity.provenance_ref,
        created_at=_utc(now),
        expires_at=expiry,
    )


def _action_arguments(
    stored: StoredGrowthPlanDraft,
    output: dict[str, object],
) -> dict[str, object]:
    expected = {
        "intent_ref": stored.intent_id,
        "onboarding_ref": stored.onboarding_id,
        "priority_ref": stored.priority_id,
    }
    if any(output.get(key) != value for key, value in expected.items()):
        raise GrowthPlanReviewError("GROWTH_PLAN_DRAFT_BINDING_MISMATCH")
    if output.get("draft_status") != "DRAFT" or output.get("horizon_days") != 90:
        raise GrowthPlanReviewError("GROWTH_PLAN_DRAFT_SHAPE_INVALID")
    stages = output.get("stages")
    if (
        not isinstance(stages, list)
        or tuple(item.get("stage_id") if isinstance(item, dict) else None for item in stages)
        != _STAGE_IDS
    ):
        raise GrowthPlanReviewError("GROWTH_PLAN_DRAFT_STAGES_INVALID")
    return {
        "draft_id": stored.identity.draft_id,
        "intent_id": stored.intent_id,
        "onboarding_id": stored.onboarding_id,
        "priority_id": stored.priority_id,
        "draft_digest": stored.stable_digest,
    }


def _stable_digest(stored: StoredGrowthPlanDraft) -> str:
    draft = stored.model_draft.draft
    provenance = draft.provenance
    material: dict[str, Any] = {
        "identity": {
            "draft_id": stored.identity.draft_id,
            "provenance_ref": stored.identity.provenance_ref,
        },
        "request_id": stored.request_id,
        "agent_run_id": stored.agent_run_id,
        "scope": {
            "tenant_id": stored.tenant_id,
            "family_id": stored.family_id,
            "region_id": stored.region_id,
            "subject_person_id": stored.subject_person_id,
            "purpose": stored.purpose,
            "consent_version": stored.consent_version,
            "data_class": stored.data_class,
            "locale": stored.locale,
            "deletion_ref": stored.deletion_ref,
            "generation_correlation_id": stored.generation_correlation_id,
            "scope_payload": stored.scope_payload,
        },
        "bindings": {
            "intent_id": stored.intent_id,
            "onboarding_id": stored.onboarding_id,
            "priority_id": stored.priority_id,
            "input_refs": stored.input_refs,
        },
        "draft": dict(draft.output),
        "provenance": {
            "provider_id": provenance.provider_id,
            "model": provenance.model,
            "model_version": provenance.model_version,
            "prompt_version": provenance.prompt_version,
            "schema_version": provenance.schema_version,
            "context_snapshot_ref": provenance.context_snapshot_ref,
            "latency_ms": provenance.latency_ms,
            "data_class": provenance.data_class,
            "use_case": provenance.use_case,
            "confidence": provenance.confidence,
            "generated_at": _utc(provenance.generated_at).isoformat(),
        },
        "created_at": stored.created_at.isoformat(),
        "expires_at": stored.expires_at.isoformat(),
        "retention_policy": REVIEW_RETENTION_POLICY,
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _replace_digest(stored: StoredGrowthPlanDraft, digest: str) -> StoredGrowthPlanDraft:
    return StoredGrowthPlanDraft(
        identity=stored.identity,
        request_id=stored.request_id,
        agent_run_id=stored.agent_run_id,
        tenant_id=stored.tenant_id,
        family_id=stored.family_id,
        region_id=stored.region_id,
        subject_person_id=stored.subject_person_id,
        purpose=stored.purpose,
        consent_version=stored.consent_version,
        data_class=stored.data_class,
        locale=stored.locale,
        deletion_ref=stored.deletion_ref,
        generation_correlation_id=stored.generation_correlation_id,
        scope_payload=stored.scope_payload,
        intent_id=stored.intent_id,
        onboarding_id=stored.onboarding_id,
        priority_id=stored.priority_id,
        input_refs=stored.input_refs,
        model_draft=stored.model_draft,
        stable_digest=digest,
        created_at=stored.created_at,
        expires_at=stored.expires_at,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _scope_payload(scope: ContextScope) -> dict[str, str]:
    return {
        "locale": scope.locale,
        "content_locale": scope.effective_content_locale,
        "model_locale": scope.effective_model_locale,
        "policy_locale": scope.effective_policy_locale,
        "deletion_state": scope.deletion_state,
        "generation_correlation_id": scope.correlation_id,
        "generation_causation_id": scope.causation_id,
    }


def _scope_payload_visible(payload: dict[str, str], scope: ContextScope) -> bool:
    return (
        payload.get("locale") == scope.locale
        and payload.get("content_locale") == scope.effective_content_locale
        and payload.get("model_locale") == scope.effective_model_locale
        and payload.get("policy_locale") == scope.effective_policy_locale
        and payload.get("deletion_state") == "ACTIVE"
    )


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise GrowthPlanReviewError(f"{name.upper()}_TIMEZONE_REQUIRED")


__all__ = [
    "CREATE_JOURNEY_PLAN_ACTION",
    "GrowthPlanDraftReviewRow",
    "GrowthPlanHumanGateApplication",
    "GrowthPlanReviewBase",
    "GrowthPlanReviewError",
    "GrowthPlanReviewNotFound",
    "SqlAlchemyGrowthPlanDraftRegistry",
    "StoredGrowthPlanDraft",
]
