"""PostgreSQL adapter for :class:`FamilyNeedRepositoryPort`.

Schema is created by ``database/migrations/versions/0055_family_need_domain.py``
(need_signals / family_needs / need_profiles / solution_drafts /
family_need_events) and
``database/migrations/versions/0058_family_need_assignment_and_outcome.py``
(family_need_assignment_plans / family_need_confirmed_outcomes). One
repository instance owns one ``AsyncConnection``; the caller owns the
transaction boundary (mirrors
``backend/domains/journey/infrastructure/sqlalchemy_repository.py``).

Optimistic concurrency mirrors ``FakeFamilyNeedRepository``: a ``save_*`` call
for an aggregate that already exists at an equal-or-lower version than the
persisted row raises ``FamilyNeedConflictError`` unless the payload is
byte-identical (idempotent replay). Tenant/family scope on an existing row
that would change is ``FamilyNeedForbiddenError``, never a silent overwrite.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from ..application.ports import NeedEvent
from ..domain.entities import (
    AssignmentPlan,
    FamilyConfirmedOutcome,
    FamilyNeed,
    NeedProfile,
    NeedSignal,
    SolutionDraft,
)
from ..domain.errors import FamilyNeedConflictError, FamilyNeedForbiddenError
from ..domain.value_objects import (
    AcceptanceCriterion,
    ActorType,
    DataClass,
    EmotionalGate,
    EvidenceKind,
    EvidenceRef,
    FamilyOutcomeDecision,
    InterventionTier,
    NeedCategory,
    NeedComplexity,
    NeedConstraint,
    NeedContext,
    NeedSignalSource,
    NeedSignalStatus,
    NeedStatus,
    NeedUrgency,
    RiskLevel,
    SolutionComponentRef,
    SolutionDraftStatus,
    SupplyShape,
)


def _dump(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _evidence_refs_to_json(refs: tuple[EvidenceRef, ...]) -> list[dict]:
    payload = []
    for ref in refs:
        item = asdict(ref)
        item["kind"] = ref.kind.value
        item["data_class"] = ref.data_class.value
        item["expires_at"] = ref.expires_at.isoformat() if ref.expires_at else None
        payload.append(item)
    return payload


def _evidence_refs_from_json(rows: list[dict] | None) -> tuple[EvidenceRef, ...]:
    if not rows:
        return ()
    result = []
    for row in rows:
        expires_at = row.get("expires_at")
        result.append(
            EvidenceRef(
                media_ref=row["media_ref"],
                kind=EvidenceKind(row["kind"]),
                tenant_id=row["tenant_id"],
                family_id=row["family_id"],
                provenance_ref=row["provenance_ref"],
                consent_version=row.get("consent_version"),
                data_class=DataClass(row["data_class"]),
                authorized=row.get("authorized", True),
                expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
            )
        )
    return tuple(result)


def _constraints_to_json(constraints: tuple[NeedConstraint, ...]) -> list[dict]:
    return [asdict(item) for item in constraints]


def _constraints_from_json(rows: list[dict] | None) -> tuple[NeedConstraint, ...]:
    if not rows:
        return ()
    return tuple(NeedConstraint(**row) for row in rows)


def _acceptance_criteria_to_json(items: tuple[AcceptanceCriterion, ...]) -> list[dict]:
    return [asdict(item) for item in items]


def _acceptance_criteria_from_json(rows: list[dict] | None) -> tuple[AcceptanceCriterion, ...]:
    if not rows:
        return ()
    return tuple(AcceptanceCriterion(**row) for row in rows)


def _components_to_json(components: tuple[SolutionComponentRef, ...]) -> list[dict]:
    payload = []
    for component in components:
        item = asdict(component)
        item["shape"] = component.shape.value
        payload.append(item)
    return payload


def _components_from_json(rows: list[dict] | None) -> tuple[SolutionComponentRef, ...]:
    if not rows:
        return ()
    result = []
    for row in rows:
        result.append(
            SolutionComponentRef(
                component_id=row["component_id"],
                shape=SupplyShape(row["shape"]),
                version=row["version"],
                required=row.get("required", True),
                quantity=row.get("quantity", 1),
            )
        )
    return tuple(result)


def _context_columns(context: NeedContext) -> dict:
    return {
        "tenant_id": context.tenant_id,
        "family_id": context.family_id,
        "purpose": context.purpose,
        "consent_version": context.consent_version,
        "data_class": context.data_class.value,
        "locale": context.locale,
        "region": context.region,
        "subject_person_ids": _dump(list(context.subject_person_ids)),
        "actor_id": context.actor_id,
        "actor_type": context.actor_type.value,
        "source_system": context.source_system,
        "environment": context.environment,
        "provenance_ref": context.provenance_ref,
        "correlation_id": context.correlation_id,
        "causation_id": context.causation_id,
    }


def _context_from_row(row) -> NeedContext:
    return NeedContext(
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        purpose=row.purpose,
        consent_version=row.consent_version,
        data_class=DataClass(row.data_class),
        locale=row.locale,
        region=row.region,
        subject_person_ids=tuple(row.subject_person_ids or ()),
        actor_id=row.actor_id,
        actor_type=ActorType(row.actor_type),
        source_system=row.source_system,
        environment=row.environment,
        provenance_ref=row.provenance_ref,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
    )


class SqlAlchemyFamilyNeedRepository:
    """One connection per instance; caller owns commit/rollback."""

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    # -- N0: NeedSignal -----------------------------------------------------

    async def save_signal(self, signal: NeedSignal) -> None:
        existing = await self._connection.execute(
            text(
                """
                select tenant_id, family_id from need_signals
                where tenant_id=:tenant_id and signal_id=:signal_id
                """
            ),
            {"tenant_id": signal.context.tenant_id, "signal_id": signal.signal_id},
        )
        row = existing.first()
        if row is not None and row.family_id != signal.context.family_id:
            raise FamilyNeedForbiddenError("need_signal_identity_conflict")

        idempotency_key = _idempotency_key_from_evidence(signal.evidence_refs)
        params = {
            "signal_id": signal.signal_id,
            **_context_columns(signal.context),
            "source": signal.source.value,
            "raw_text": signal.raw_text,
            "status": signal.status.value,
            "captured_at": signal.captured_at,
            "expires_at": signal.expires_at,
            "evidence_refs": _dump(_evidence_refs_to_json(signal.evidence_refs)),
            "idempotency_key": idempotency_key,
        }
        try:
            await self._connection.execute(
                text(
                    """
                    insert into need_signals(
                      signal_id, tenant_id, family_id, purpose, consent_version, data_class,
                      locale, region, subject_person_ids, actor_id, actor_type, source_system,
                      environment, provenance_ref, correlation_id, causation_id,
                      source, raw_text, status, captured_at, expires_at, evidence_refs,
                      idempotency_key, updated_at
                    ) values (
                      :signal_id, :tenant_id, :family_id, :purpose, :consent_version, :data_class,
                      :locale, :region, :subject_person_ids, :actor_id, :actor_type, :source_system,
                      :environment, :provenance_ref, :correlation_id, :causation_id,
                      :source, :raw_text, :status, :captured_at, :expires_at, :evidence_refs,
                      :idempotency_key, now()
                    )
                    on conflict (tenant_id, signal_id) do update set
                      status=excluded.status, expires_at=excluded.expires_at, updated_at=now()
                    """
                ),
                params,
            )
        except IntegrityError as exc:
            raise FamilyNeedConflictError("need_signal_idempotency_conflict") from exc

    async def get_signal(
        self, *, tenant_id: str, family_id: str, signal_id: str
    ) -> NeedSignal | None:
        result = await self._connection.execute(
            text(
                """
                select * from need_signals
                where tenant_id=:tenant_id and family_id=:family_id and signal_id=:signal_id
                """
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "signal_id": signal_id},
        )
        row = result.mappings().first()
        return _signal_from_row(row) if row is not None else None

    # -- N1-N8: FamilyNeed ----------------------------------------------------

    async def save_need(self, need: FamilyNeed) -> None:
        existing = await self._connection.execute(
            text(
                """
                select tenant_id, family_id, version from family_needs
                where tenant_id=:tenant_id and need_id=:need_id
                """
            ),
            {"tenant_id": need.context.tenant_id, "need_id": need.need_id},
        )
        row = existing.first()
        if row is not None:
            if row.family_id != need.context.family_id:
                raise FamilyNeedForbiddenError("need_tenant_scope_conflict")
            if need.version < row.version:
                raise FamilyNeedConflictError("family_need_version_regressed")

        params = {
            "need_id": need.need_id,
            **_context_columns(need.context),
            "context_subject_person_ids": _dump(list(need.context.subject_person_ids)),
            "source_signal_ids": _dump(list(need.source_signal_ids)),
            "subject_person_ids": _dump(list(need.subject_person_ids)),
            "statement": need.statement,
            "desired_outcome": need.desired_outcome,
            "category": need.category.value,
            "status": need.status.value,
            "emotional_gate": need.emotional_gate.value,
            "constraints": _dump(_constraints_to_json(need.constraints)),
            "version": need.version,
            "confirmed_by_actor_id": need.confirmed_by_actor_id,
            "rejected_reason": need.rejected_reason,
            "pause_reason": need.pause_reason,
            "evidence_refs": _dump(_evidence_refs_to_json(need.evidence_refs)),
            "created_at": need.created_at,
            "updated_at": need.updated_at,
        }
        result = await self._connection.execute(
            text(
                """
                insert into family_needs(
                  need_id, tenant_id, family_id, purpose, consent_version, data_class,
                  locale, region, subject_person_ids, context_subject_person_ids,
                  actor_id, actor_type, source_system, environment, provenance_ref,
                  correlation_id, causation_id, source_signal_ids, statement, desired_outcome,
                  category, status, emotional_gate, constraints, version,
                  confirmed_by_actor_id, rejected_reason, pause_reason, evidence_refs,
                  created_at, updated_at
                ) values (
                  :need_id, :tenant_id, :family_id, :purpose, :consent_version, :data_class,
                  :locale, :region, :subject_person_ids, :context_subject_person_ids,
                  :actor_id, :actor_type, :source_system, :environment, :provenance_ref,
                  :correlation_id, :causation_id, :source_signal_ids, :statement, :desired_outcome,
                  :category, :status, :emotional_gate, :constraints, :version,
                  :confirmed_by_actor_id, :rejected_reason, :pause_reason, :evidence_refs,
                  :created_at, :updated_at
                )
                on conflict (tenant_id, need_id) do update set
                  status=excluded.status, emotional_gate=excluded.emotional_gate,
                  constraints=excluded.constraints, version=excluded.version,
                  confirmed_by_actor_id=excluded.confirmed_by_actor_id,
                  rejected_reason=excluded.rejected_reason, pause_reason=excluded.pause_reason,
                  subject_person_ids=excluded.subject_person_ids,
                  updated_at=excluded.updated_at
                where family_needs.version < excluded.version
                   or (family_needs.version = excluded.version)
                """
            ),
            params,
        )
        if row is not None and result.rowcount == 0 and need.version == row.version:
            # Same version re-save: only acceptable if it is a byte-identical replay.
            current = await self.get_need(
                tenant_id=need.context.tenant_id,
                family_id=need.context.family_id,
                need_id=need.need_id,
            )
            if current != need:
                raise FamilyNeedConflictError("family_need_version_replay_mismatch")

    async def get_need(self, *, tenant_id: str, family_id: str, need_id: str) -> FamilyNeed | None:
        result = await self._connection.execute(
            text(
                """
                select * from family_needs
                where tenant_id=:tenant_id and family_id=:family_id and need_id=:need_id
                """
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "need_id": need_id},
        )
        row = result.mappings().first()
        return _need_from_row(row) if row is not None else None

    # -- N2: NeedProfile ------------------------------------------------------

    async def save_profile(self, profile: NeedProfile) -> None:
        existing = await self._connection.execute(
            text(
                """
                select tenant_id, family_id from need_profiles
                where tenant_id=:tenant_id and profile_id=:profile_id
                """
            ),
            {"tenant_id": profile.context.tenant_id, "profile_id": profile.profile_id},
        )
        row = existing.first()
        if row is not None and row.family_id != profile.context.family_id:
            raise FamilyNeedForbiddenError("profile_tenant_scope_conflict")

        params = {
            "profile_id": profile.profile_id,
            "need_id": profile.need_id,
            "need_version": profile.need_version,
            **_context_columns(profile.context),
            "category": profile.category.value,
            "urgency": profile.urgency.value,
            "complexity": profile.complexity.value,
            "risk_level": profile.risk_level.value,
            "intervention_tier": profile.intervention_tier.value,
            "preferred_shapes": _dump([s.value for s in profile.preferred_shapes]),
            "constraints": _dump(_constraints_to_json(profile.constraints)),
            "required_capability_keys": _dump(list(profile.required_capability_keys)),
            "profile_locale": profile.locale,
            "profile_region": profile.region,
            "confirmed_by_actor_id": profile.confirmed_by_actor_id,
            "version": profile.version,
            "created_at": profile.created_at,
        }
        try:
            await self._connection.execute(
                text(
                    """
                    insert into need_profiles(
                      profile_id, need_id, need_version, tenant_id, family_id, purpose,
                      consent_version, data_class, locale, region, subject_person_ids,
                      actor_id, actor_type, source_system, environment, provenance_ref,
                      correlation_id, causation_id, category, urgency, complexity, risk_level,
                      intervention_tier, preferred_shapes, constraints, required_capability_keys,
                      profile_locale, profile_region, confirmed_by_actor_id, version, created_at
                    ) values (
                      :profile_id, :need_id, :need_version, :tenant_id, :family_id, :purpose,
                      :consent_version, :data_class, :locale, :region, :subject_person_ids,
                      :actor_id, :actor_type, :source_system, :environment, :provenance_ref,
                      :correlation_id, :causation_id, :category, :urgency, :complexity, :risk_level,
                      :intervention_tier, :preferred_shapes, :constraints,
                      :required_capability_keys, :profile_locale, :profile_region,
                      :confirmed_by_actor_id, :version, :created_at
                    )
                    on conflict (tenant_id, profile_id) do nothing
                    """
                ),
                params,
            )
        except IntegrityError as exc:
            raise FamilyNeedConflictError("need_profile_conflict") from exc

        if row is not None:
            current = await self.get_profile(
                tenant_id=profile.context.tenant_id,
                family_id=profile.context.family_id,
                profile_id=profile.profile_id,
            )
            if current != profile:
                raise FamilyNeedConflictError("need_profile_version_replay_mismatch")

    async def get_profile(
        self, *, tenant_id: str, family_id: str, profile_id: str
    ) -> NeedProfile | None:
        result = await self._connection.execute(
            text(
                """
                select * from need_profiles
                where tenant_id=:tenant_id and family_id=:family_id and profile_id=:profile_id
                """
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "profile_id": profile_id},
        )
        row = result.mappings().first()
        return _profile_from_row(row) if row is not None else None

    # -- N3: SolutionDraft ----------------------------------------------------

    async def save_solution_draft(self, draft: SolutionDraft) -> None:
        existing = await self._connection.execute(
            text(
                """
                select tenant_id, family_id, updated_at from solution_drafts
                where tenant_id=:tenant_id and draft_id=:draft_id
                """
            ),
            {"tenant_id": draft.context.tenant_id, "draft_id": draft.draft_id},
        )
        row = existing.first()
        if row is not None and row.family_id != draft.context.family_id:
            raise FamilyNeedForbiddenError("solution_tenant_scope_conflict")

        params = {
            "draft_id": draft.draft_id,
            "need_id": draft.need_id,
            "need_profile_id": draft.need_profile_id,
            "profile_version": draft.profile_version,
            **_context_columns(draft.context),
            "shape": draft.shape.value,
            "components": _dump(_components_to_json(draft.components)),
            "emotional_gate": draft.emotional_gate.value,
            "commercial_intent": draft.commercial_intent,
            "status": draft.status.value,
            "author_type": draft.author_type.value,
            "acceptance_criteria": _dump(_acceptance_criteria_to_json(draft.acceptance_criteria)),
            "estimated_cost_minor": draft.estimated_cost_minor,
            "sla_hours": draft.sla_hours,
            "can_pause": draft.can_pause,
            "can_exit": draft.can_exit,
            "respectful_language": draft.respectful_language,
            "manipulative": draft.manipulative,
            "approved_by_actor_id": draft.approved_by_actor_id,
            "rejection_reason": draft.rejection_reason,
            "requires_human_case_review": draft.requires_human_case_review,
            "human_case_review_note": draft.human_case_review_note,
            "created_at": draft.created_at,
            "updated_at": draft.updated_at,
        }
        await self._connection.execute(
            text(
                """
                insert into solution_drafts(
                  draft_id, need_id, need_profile_id, profile_version, tenant_id, family_id,
                  purpose, consent_version, data_class, locale, region, subject_person_ids,
                  actor_id, actor_type, source_system, environment, provenance_ref,
                  correlation_id, causation_id, shape, components, emotional_gate,
                  commercial_intent, status, author_type, acceptance_criteria,
                  estimated_cost_minor, sla_hours, can_pause, can_exit, respectful_language,
                  manipulative, approved_by_actor_id, rejection_reason,
                  requires_human_case_review, human_case_review_note, created_at, updated_at
                ) values (
                  :draft_id, :need_id, :need_profile_id, :profile_version, :tenant_id, :family_id,
                  :purpose, :consent_version, :data_class, :locale, :region, :subject_person_ids,
                  :actor_id, :actor_type, :source_system, :environment, :provenance_ref,
                  :correlation_id, :causation_id, :shape, :components, :emotional_gate,
                  :commercial_intent, :status, :author_type, :acceptance_criteria,
                  :estimated_cost_minor, :sla_hours, :can_pause, :can_exit, :respectful_language,
                  :manipulative, :approved_by_actor_id, :rejection_reason,
                  :requires_human_case_review, :human_case_review_note, :created_at, :updated_at
                )
                on conflict (tenant_id, draft_id) do update set
                  status=excluded.status, emotional_gate=excluded.emotional_gate,
                  approved_by_actor_id=excluded.approved_by_actor_id,
                  rejection_reason=excluded.rejection_reason, updated_at=excluded.updated_at
                where solution_drafts.updated_at is distinct from excluded.updated_at
                """
            ),
            params,
        )
        if row is not None and row.updated_at == draft.updated_at:
            current = await self.get_solution_draft(
                tenant_id=draft.context.tenant_id,
                family_id=draft.context.family_id,
                draft_id=draft.draft_id,
            )
            if current != draft:
                raise FamilyNeedConflictError("solution_draft_replay_mismatch")

    async def get_solution_draft(
        self, *, tenant_id: str, family_id: str, draft_id: str
    ) -> SolutionDraft | None:
        result = await self._connection.execute(
            text(
                """
                select * from solution_drafts
                where tenant_id=:tenant_id and family_id=:family_id and draft_id=:draft_id
                """
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "draft_id": draft_id},
        )
        row = result.mappings().first()
        return _draft_from_row(row) if row is not None else None

    # -- N4: AssignmentPlan ---------------------------------------------------

    async def save_assignment_plan(self, plan: AssignmentPlan) -> None:
        existing = await self._connection.execute(
            text(
                """
                select tenant_id, family_id from family_need_assignment_plans
                where tenant_id=:tenant_id and plan_id=:plan_id
                """
            ),
            {"tenant_id": plan.tenant_id, "plan_id": plan.plan_id},
        )
        row = existing.first()
        if row is not None and row.family_id != plan.family_id:
            raise FamilyNeedForbiddenError("assignment_plan_tenant_scope_conflict")

        params = {
            "plan_id": plan.plan_id,
            "tenant_id": plan.tenant_id,
            "family_id": plan.family_id,
            "need_id": plan.need_id,
            "draft_id": plan.draft_id,
            "component_refs": _dump(_components_to_json(plan.component_refs)),
            "authorization_basis": plan.authorization_basis,
            "created_at": plan.created_at,
            "resolved_slot_id": plan.resolved_slot_id,
            "resolved_booking_ref": plan.resolved_booking_ref,
            "resolved_order_intent_ref": plan.resolved_order_intent_ref,
        }
        try:
            await self._connection.execute(
                text(
                    """
                    insert into family_need_assignment_plans(
                      plan_id, tenant_id, family_id, need_id, draft_id, component_refs,
                      authorization_basis, created_at, resolved_slot_id, resolved_booking_ref,
                      resolved_order_intent_ref
                    ) values (
                      :plan_id, :tenant_id, :family_id, :need_id, :draft_id, :component_refs,
                      :authorization_basis, :created_at, :resolved_slot_id, :resolved_booking_ref,
                      :resolved_order_intent_ref
                    )
                    on conflict (tenant_id, plan_id) do update set
                      resolved_slot_id=excluded.resolved_slot_id,
                      resolved_booking_ref=excluded.resolved_booking_ref,
                      resolved_order_intent_ref=excluded.resolved_order_intent_ref
                    where family_need_assignment_plans.resolved_slot_id is distinct from
                          excluded.resolved_slot_id
                       or family_need_assignment_plans.resolved_booking_ref is distinct from
                          excluded.resolved_booking_ref
                       or family_need_assignment_plans.resolved_order_intent_ref is distinct from
                          excluded.resolved_order_intent_ref
                    """
                ),
                params,
            )
        except IntegrityError as exc:
            raise FamilyNeedConflictError("assignment_plan_conflict") from exc

        if row is not None:
            current = await self.get_assignment_plan(
                tenant_id=plan.tenant_id, family_id=plan.family_id, plan_id=plan.plan_id
            )
            if current != plan:
                raise FamilyNeedConflictError("assignment_plan_replay_mismatch")

    async def get_assignment_plan(
        self, *, tenant_id: str, family_id: str, plan_id: str
    ) -> AssignmentPlan | None:
        result = await self._connection.execute(
            text(
                """
                select * from family_need_assignment_plans
                where tenant_id=:tenant_id and family_id=:family_id and plan_id=:plan_id
                """
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "plan_id": plan_id},
        )
        row = result.mappings().first()
        return _assignment_plan_from_row(row) if row is not None else None

    # -- N6/N7: FamilyConfirmedOutcome ----------------------------------------

    async def save_outcome(self, outcome: FamilyConfirmedOutcome) -> None:
        existing = await self._connection.execute(
            text(
                """
                select tenant_id, family_id from family_need_confirmed_outcomes
                where tenant_id=:tenant_id and outcome_id=:outcome_id
                """
            ),
            {"tenant_id": outcome.context.tenant_id, "outcome_id": outcome.outcome_id},
        )
        row = existing.first()
        if row is not None and row.family_id != outcome.context.family_id:
            raise FamilyNeedForbiddenError("outcome_tenant_scope_conflict")

        params = {
            "outcome_id": outcome.outcome_id,
            **_context_columns(outcome.context),
            "need_id": outcome.need_id,
            "draft_id": outcome.draft_id,
            "fulfillment_ref": outcome.fulfillment_ref,
            "decision": outcome.decision.value,
            "confirmed_by": outcome.confirmed_by,
            "confirmed_at": outcome.confirmed_at,
            "family_note": outcome.family_note,
        }
        try:
            await self._connection.execute(
                text(
                    """
                    insert into family_need_confirmed_outcomes(
                      outcome_id, tenant_id, family_id, purpose, consent_version, data_class,
                      locale, region, subject_person_ids, actor_id, actor_type, source_system,
                      environment, provenance_ref, correlation_id, causation_id,
                      need_id, draft_id, fulfillment_ref, decision, confirmed_by, confirmed_at,
                      family_note
                    ) values (
                      :outcome_id, :tenant_id, :family_id, :purpose, :consent_version, :data_class,
                      :locale, :region, :subject_person_ids, :actor_id, :actor_type, :source_system,
                      :environment, :provenance_ref, :correlation_id, :causation_id,
                      :need_id, :draft_id, :fulfillment_ref, :decision, :confirmed_by,
                      :confirmed_at, :family_note
                    )
                    on conflict (tenant_id, outcome_id) do nothing
                    """
                ),
                params,
            )
        except IntegrityError as exc:
            raise FamilyNeedConflictError("outcome_conflict") from exc

        if row is not None:
            current = await self._get_outcome(
                tenant_id=outcome.context.tenant_id,
                family_id=outcome.context.family_id,
                outcome_id=outcome.outcome_id,
            )
            if current != outcome:
                raise FamilyNeedConflictError("outcome_replay_mismatch")

    async def _get_outcome(
        self, *, tenant_id: str, family_id: str, outcome_id: str
    ) -> FamilyConfirmedOutcome | None:
        result = await self._connection.execute(
            text(
                """
                select * from family_need_confirmed_outcomes
                where tenant_id=:tenant_id and family_id=:family_id and outcome_id=:outcome_id
                """
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "outcome_id": outcome_id},
        )
        row = result.mappings().first()
        return _outcome_from_row(row) if row is not None else None

    async def get_outcomes_for_need(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> tuple[FamilyConfirmedOutcome, ...]:
        result = await self._connection.execute(
            text(
                """
                select * from family_need_confirmed_outcomes
                where tenant_id=:tenant_id and family_id=:family_id and need_id=:need_id
                order by confirmed_at asc
                """
            ),
            {"tenant_id": tenant_id, "family_id": family_id, "need_id": need_id},
        )
        rows = result.mappings().all()
        return tuple(_outcome_from_row(row) for row in rows)

    # -- Event outbox / idempotency -----------------------------------------

    async def append_event(self, event: NeedEvent) -> None:
        # A duplicate idempotency_key is an expected, caller-recoverable
        # outcome (a replayed request), not a corrupt transaction. Without a
        # SAVEPOINT, Postgres poisons the entire enclosing transaction on the
        # first failed statement, so any later statement on this connection —
        # including the caller's own `find_by_idempotency_key` replay lookup —
        # would raise `InFailedSqlTransactionError` instead of the intended
        # `FamilyNeedConflictError`.
        try:
            async with self._connection.begin_nested():
                await self._connection.execute(
                    text(
                        """
                        insert into family_need_events(
                          event_name, aggregate_id, tenant_id, family_id, version,
                          correlation_id, occurred_at, purpose, consent_version, data_class,
                          subject_person_ids, idempotency_key
                        ) values (
                          :event_name, :aggregate_id, :tenant_id, :family_id, :version,
                          :correlation_id, :occurred_at, :purpose, :consent_version, :data_class,
                          :subject_person_ids, :idempotency_key
                        )
                        """
                    ),
                    {
                        "event_name": event.event_name,
                        "aggregate_id": event.aggregate_id,
                        "tenant_id": event.tenant_id,
                        "family_id": event.family_id,
                        "version": event.version,
                        "correlation_id": event.correlation_id,
                        "occurred_at": event.occurred_at,
                        "purpose": event.purpose,
                        "consent_version": event.consent_version,
                        "data_class": event.data_class.value if event.data_class else None,
                        "subject_person_ids": _dump(list(event.subject_person_ids)),
                        "idempotency_key": event.idempotency_key,
                    },
                )
        except IntegrityError as exc:
            raise FamilyNeedConflictError("need_event_version_duplicate") from exc

    async def find_by_idempotency_key(
        self, *, tenant_id: str, family_id: str, idempotency_key: str
    ) -> NeedEvent | None:
        """Support-lookup used by durable UoWs to detect a prior replay.

        Not part of ``FamilyNeedRepositoryPort`` (the port is aggregate-scoped
        via ``append_event``'s unique constraint); exposed for callers that
        want to short-circuit before re-running domain logic.
        """

        result = await self._connection.execute(
            text(
                """
                select * from family_need_events
                where tenant_id=:tenant_id and family_id=:family_id
                  and idempotency_key=:idempotency_key
                order by created_at asc limit 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "family_id": family_id,
                "idempotency_key": idempotency_key,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        return NeedEvent(
            event_name=row["event_name"],
            aggregate_id=row["aggregate_id"],
            tenant_id=row["tenant_id"],
            family_id=row["family_id"],
            version=row["version"],
            correlation_id=row["correlation_id"],
            occurred_at=row["occurred_at"],
            purpose=row["purpose"],
            consent_version=row["consent_version"],
            data_class=DataClass(row["data_class"]) if row["data_class"] else None,
            subject_person_ids=tuple(row["subject_person_ids"] or ()),
            idempotency_key=row["idempotency_key"],
        )


def _idempotency_key_from_evidence(evidence_refs: tuple[EvidenceRef, ...]) -> None:
    # NeedSignal carries no explicit idempotency_key field; the application
    # layer keys replay off (tenant, family, command.idempotency_key) and the
    # durable dedup point is `append_event`'s unique index. This hook exists
    # so a future signal-level idempotency key has one place to land.
    del evidence_refs
    return None


def _signal_from_row(row) -> NeedSignal:
    return NeedSignal(
        signal_id=row["signal_id"],
        context=_context_from_row(row),
        source=NeedSignalSource(row["source"]),
        raw_text=row["raw_text"],
        captured_at=row["captured_at"],
        status=NeedSignalStatus(row["status"]),
        expires_at=row["expires_at"],
        evidence_refs=_evidence_refs_from_json(row["evidence_refs"]),
    )


def _need_from_row(row) -> FamilyNeed:
    context = _context_from_row(row)
    return FamilyNeed(
        need_id=row["need_id"],
        context=context,
        source_signal_ids=tuple(row["source_signal_ids"] or ()),
        subject_person_ids=tuple(row["subject_person_ids"] or ()),
        statement=row["statement"],
        desired_outcome=row["desired_outcome"],
        category=NeedCategory(row["category"]),
        status=NeedStatus(row["status"]),
        emotional_gate=EmotionalGate(row["emotional_gate"]),
        constraints=_constraints_from_json(row["constraints"]),
        version=row["version"],
        confirmed_by_actor_id=row["confirmed_by_actor_id"],
        rejected_reason=row["rejected_reason"],
        pause_reason=row["pause_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        evidence_refs=_evidence_refs_from_json(row["evidence_refs"]),
    )


def _profile_from_row(row) -> NeedProfile:
    return NeedProfile(
        profile_id=row["profile_id"],
        need_id=row["need_id"],
        need_version=row["need_version"],
        context=_context_from_row(row),
        category=NeedCategory(row["category"]),
        urgency=NeedUrgency(row["urgency"]),
        complexity=NeedComplexity(row["complexity"]),
        risk_level=RiskLevel(row["risk_level"]),
        intervention_tier=InterventionTier(row["intervention_tier"]),
        preferred_shapes=tuple(SupplyShape(v) for v in (row["preferred_shapes"] or ())),
        constraints=_constraints_from_json(row["constraints"]),
        required_capability_keys=tuple(row["required_capability_keys"] or ()),
        locale=row["profile_locale"],
        region=row["profile_region"],
        confirmed_by_actor_id=row["confirmed_by_actor_id"],
        version=row["version"],
        created_at=row["created_at"],
    )


def _draft_from_row(row) -> SolutionDraft:
    return SolutionDraft(
        draft_id=row["draft_id"],
        need_id=row["need_id"],
        need_profile_id=row["need_profile_id"],
        profile_version=row["profile_version"],
        context=_context_from_row(row),
        shape=SupplyShape(row["shape"]),
        components=_components_from_json(row["components"]),
        emotional_gate=EmotionalGate(row["emotional_gate"]),
        commercial_intent=row["commercial_intent"],
        status=SolutionDraftStatus(row["status"]),
        author_type=ActorType(row["author_type"]),
        acceptance_criteria=_acceptance_criteria_from_json(row["acceptance_criteria"]),
        estimated_cost_minor=row["estimated_cost_minor"],
        sla_hours=row["sla_hours"],
        can_pause=row["can_pause"],
        can_exit=row["can_exit"],
        respectful_language=row["respectful_language"],
        manipulative=row["manipulative"],
        approved_by_actor_id=row["approved_by_actor_id"],
        rejection_reason=row["rejection_reason"],
        requires_human_case_review=row["requires_human_case_review"],
        human_case_review_note=row["human_case_review_note"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _assignment_plan_from_row(row) -> AssignmentPlan:
    return AssignmentPlan(
        plan_id=row["plan_id"],
        tenant_id=row["tenant_id"],
        family_id=row["family_id"],
        need_id=row["need_id"],
        draft_id=row["draft_id"],
        component_refs=_components_from_json(row["component_refs"]),
        authorization_basis=row["authorization_basis"],
        created_at=row["created_at"],
        resolved_slot_id=row["resolved_slot_id"],
        resolved_booking_ref=row["resolved_booking_ref"],
        resolved_order_intent_ref=row["resolved_order_intent_ref"],
    )


def _outcome_from_row(row) -> FamilyConfirmedOutcome:
    return FamilyConfirmedOutcome(
        outcome_id=row["outcome_id"],
        context=_context_from_row(row),
        need_id=row["need_id"],
        fulfillment_ref=row["fulfillment_ref"],
        decision=FamilyOutcomeDecision(row["decision"]),
        confirmed_by=row["confirmed_by"],
        confirmed_at=row["confirmed_at"],
        draft_id=row["draft_id"],
        family_note=row["family_note"],
    )


__all__ = ["SqlAlchemyFamilyNeedRepository"]
