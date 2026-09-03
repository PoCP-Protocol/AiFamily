"""In-memory adapters used by the Family Need contract tests.

These fakes intentionally expose the same scope and resource-gap decisions as
a future regional PostgreSQL/FGCN adapter.  They are not an application API and
must never be used as a production persistence implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
from ..domain.policies import assert_context, assert_subjects_in_family
from ..domain.value_objects import (
    ActorType,
    DataClass,
    NeedContext,
    ResourceGap,
    ResourceGapReason,
    SolutionComponentRef,
    SupplyShape,
)


@dataclass
class FakeFamilyNeedRepository:
    signals: dict[str, NeedSignal] = field(default_factory=dict)
    needs: dict[str, FamilyNeed] = field(default_factory=dict)
    profiles: dict[str, NeedProfile] = field(default_factory=dict)
    solution_drafts: dict[str, SolutionDraft] = field(default_factory=dict)
    events: list[NeedEvent] = field(default_factory=list)
    outcomes: dict[str, FamilyConfirmedOutcome] = field(default_factory=dict)
    assignment_plans: dict[str, AssignmentPlan] = field(default_factory=dict)

    @staticmethod
    def _visible(context: NeedContext, *, tenant_id: str, family_id: str) -> bool:
        return context.tenant_id == tenant_id and context.family_id == family_id

    async def save_signal(self, signal: NeedSignal) -> None:
        assert_context(signal.context)
        existing = self.signals.get(signal.signal_id)
        if existing is not None and existing.context != signal.context:
            raise FamilyNeedConflictError("need_signal_identity_conflict")
        self.signals[signal.signal_id] = signal

    async def get_signal(
        self, *, tenant_id: str, family_id: str, signal_id: str
    ) -> NeedSignal | None:
        value = self.signals.get(signal_id)
        return (
            value
            if value is not None
            and self._visible(value.context, tenant_id=tenant_id, family_id=family_id)
            else None
        )

    async def save_need(self, need: FamilyNeed) -> None:
        assert_context(need.context)
        existing = self.needs.get(need.need_id)
        if existing is not None:
            if existing.context != need.context:
                raise FamilyNeedForbiddenError("need_tenant_scope_conflict")
            if need.version < existing.version:
                raise FamilyNeedConflictError("family_need_version_regressed")
            if need.version == existing.version and need != existing:
                raise FamilyNeedConflictError("family_need_version_replay_mismatch")
        self.needs[need.need_id] = need

    async def get_need(self, *, tenant_id: str, family_id: str, need_id: str) -> FamilyNeed | None:
        value = self.needs.get(need_id)
        return (
            value
            if value is not None
            and self._visible(value.context, tenant_id=tenant_id, family_id=family_id)
            else None
        )

    async def save_profile(self, profile: NeedProfile) -> None:
        assert_context(profile.context)
        existing = self.profiles.get(profile.profile_id)
        if existing is not None and existing.context != profile.context:
            raise FamilyNeedForbiddenError("profile_tenant_scope_conflict")
        if existing is not None and profile.version == existing.version and profile != existing:
            raise FamilyNeedConflictError("need_profile_version_replay_mismatch")
        self.profiles[profile.profile_id] = profile

    async def get_profile(
        self, *, tenant_id: str, family_id: str, profile_id: str
    ) -> NeedProfile | None:
        value = self.profiles.get(profile_id)
        return (
            value
            if value is not None
            and self._visible(value.context, tenant_id=tenant_id, family_id=family_id)
            else None
        )

    async def save_solution_draft(self, draft: SolutionDraft) -> None:
        assert_context(draft.context)
        existing = self.solution_drafts.get(draft.draft_id)
        if existing is not None and existing.context != draft.context:
            raise FamilyNeedForbiddenError("solution_tenant_scope_conflict")
        if existing is not None and draft.updated_at == existing.updated_at and draft != existing:
            raise FamilyNeedConflictError("solution_draft_replay_mismatch")
        self.solution_drafts[draft.draft_id] = draft

    async def get_solution_draft(
        self, *, tenant_id: str, family_id: str, draft_id: str
    ) -> SolutionDraft | None:
        value = self.solution_drafts.get(draft_id)
        return (
            value
            if value is not None
            and self._visible(value.context, tenant_id=tenant_id, family_id=family_id)
            else None
        )

    async def append_event(self, event: NeedEvent) -> None:
        if event.idempotency_key and any(
            item.aggregate_id == event.aggregate_id
            and item.version == event.version
            and item.idempotency_key == event.idempotency_key
            for item in self.events
        ):
            raise FamilyNeedConflictError("need_event_version_duplicate")
        self.events.append(event)

    async def save_outcome(self, outcome: FamilyConfirmedOutcome) -> None:
        assert_context(outcome.context)
        existing = self.outcomes.get(outcome.outcome_id)
        if existing is not None and existing.context != outcome.context:
            raise FamilyNeedForbiddenError("outcome_tenant_scope_conflict")
        self.outcomes[outcome.outcome_id] = outcome

    async def get_outcomes_for_need(
        self, *, tenant_id: str, family_id: str, need_id: str
    ) -> tuple[FamilyConfirmedOutcome, ...]:
        return tuple(
            outcome
            for outcome in self.outcomes.values()
            if outcome.need_id == need_id
            and self._visible(outcome.context, tenant_id=tenant_id, family_id=family_id)
        )

    async def save_assignment_plan(self, plan: AssignmentPlan) -> None:
        existing = self.assignment_plans.get(plan.plan_id)
        if existing is not None and (
            existing.tenant_id != plan.tenant_id or existing.family_id != plan.family_id
        ):
            raise FamilyNeedForbiddenError("assignment_plan_tenant_scope_conflict")
        self.assignment_plans[plan.plan_id] = plan

    async def get_assignment_plan(
        self, *, tenant_id: str, family_id: str, plan_id: str
    ) -> AssignmentPlan | None:
        value = self.assignment_plans.get(plan_id)
        return (
            value
            if value is not None and value.tenant_id == tenant_id and value.family_id == family_id
            else None
        )


@dataclass
class FakeFamilyNeedPolicy:
    tenant_family_bindings: set[tuple[str, str]] = field(default_factory=set)
    family_actors: dict[tuple[str, str], ActorType] = field(default_factory=dict)
    family_subjects: dict[str, set[str]] = field(default_factory=dict)
    grants: set[tuple[str, str, str, str]] = field(default_factory=set)

    def bind_family(self, tenant_id: str, family_id: str) -> None:
        self.tenant_family_bindings.add((tenant_id, family_id))

    def grant_actor(self, family_id: str, actor_id: str, actor_type: ActorType) -> None:
        self.family_actors[(family_id, actor_id)] = actor_type

    def add_subject(self, family_id: str, person_id: str) -> None:
        self.family_subjects.setdefault(family_id, set()).add(person_id)

    def grant_consent(self, family_id: str, subject_id: str, purpose: str, version: str) -> None:
        self.grants.add((family_id, subject_id, purpose, version))

    async def assert_tenant_family_scope(self, *, context: NeedContext, actor_id: str) -> None:
        if (context.tenant_id, context.family_id) not in self.tenant_family_bindings:
            raise FamilyNeedForbiddenError("tenant_family_scope_denied")
        if (context.family_id, actor_id) not in self.family_actors:
            raise FamilyNeedForbiddenError("actor_family_scope_denied")

    async def assert_subject_scope(
        self, *, context: NeedContext, subject_person_ids: tuple[str, ...]
    ) -> None:
        assert_subjects_in_family(
            subject_person_ids, self.family_subjects.get(context.family_id, set())
        )

    async def assert_consent(
        self, *, context: NeedContext, purpose: str, data_class: DataClass
    ) -> None:
        if purpose != context.purpose:
            raise FamilyNeedForbiddenError("purpose_scope_denied")
        if data_class is DataClass.PUBLIC:
            return
        if not context.subject_person_ids:
            raise FamilyNeedForbiddenError("consent_subject_required")
        for subject_id in context.subject_person_ids:
            if (context.family_id, subject_id, purpose, context.consent_version) not in self.grants:
                raise FamilyNeedForbiddenError("consent_not_granted")

    async def assert_can_manage(
        self, *, context: NeedContext, actor_id: str, actor_type: ActorType
    ) -> None:
        await self.assert_tenant_family_scope(context=context, actor_id=actor_id)
        if self.family_actors.get((context.family_id, actor_id)) not in {
            ActorType.FAMILY_GUARDIAN,
            ActorType.OPERATOR,
        } or actor_type not in {ActorType.FAMILY_GUARDIAN, ActorType.OPERATOR}:
            raise FamilyNeedForbiddenError("actor_cannot_manage_need")


@dataclass
class FakeSupplyReferencePort:
    components: dict[tuple[str, SupplyShape, str], SolutionComponentRef] = field(
        default_factory=dict
    )
    capacities: dict[str, int] = field(default_factory=dict)

    def add_component(self, component: SolutionComponentRef, *, tenant_id: str) -> None:
        self.components[(tenant_id, component.shape, component.component_id)] = component
        self.capacities.setdefault(component.component_id, 1)

    def set_capacity(self, component_id: str, capacity: int) -> None:
        self.capacities[component_id] = capacity

    async def resolve_component(
        self,
        *,
        tenant_id: str,
        region: str,
        locale: str,
        shape: SupplyShape,
        component_id: str,
        version: str,
    ) -> SolutionComponentRef | None:
        del region, locale
        component = self.components.get((tenant_id, shape, component_id))
        return component if component is not None and component.version == version else None

    async def check_resource_capacity(
        self,
        *,
        tenant_id: str,
        family_id: str,
        need_id: str = "",
        component_refs: tuple[SolutionComponentRef, ...],
    ) -> ResourceGap | None:
        del tenant_id, family_id
        for component in component_refs:
            if component.component_id not in self.capacities:
                return ResourceGap.now(
                    need_id=need_id,
                    reason=ResourceGapReason.NO_MATCHING_CAPABILITY,
                    detail=f"component:{component.component_id}",
                )
            if self.capacities[component.component_id] < component.quantity:
                return ResourceGap.now(
                    need_id=need_id,
                    reason=ResourceGapReason.NO_CAPACITY,
                    detail=f"component:{component.component_id}",
                )
        return None

    async def get_resource_gap(
        self, *, need_id: str, reason: ResourceGapReason, detail: str
    ) -> ResourceGap:
        return ResourceGap.now(need_id, reason, detail)


__all__ = ["FakeFamilyNeedPolicy", "FakeFamilyNeedRepository", "FakeSupplyReferencePort"]
