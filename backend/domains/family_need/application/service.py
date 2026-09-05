"""Application service for the first Family Need vertical slice.

This adapter closes N0 (family signal) to N1 (captured FamilyNeed).  It owns
orchestration and idempotency, while aggregates own all transitions and the
policy port owns authorization/consent.  No model provider or HTTP framework is
referenced here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from ..domain.entities import (
    AssignmentPlan,
    FamilyConfirmedOutcome,
    FamilyNeed,
    NeedProfile,
    NeedSignal,
    SolutionDraft,
)
from ..domain.errors import (
    FamilyNeedConflictError,
    FamilyNeedForbiddenError,
    FamilyNeedValidationError,
)
from ..domain.policies import (
    assert_family_outcome_confirmer,
    assert_family_scope,
    assert_subjects_in_family,
)
from ..domain.value_objects import (
    FamilyOutcomeDecision,
    InterventionTier,
    NeedCategory,
    NeedComplexity,
    NeedContext,
    NeedSignalSource,
    NeedStatus,
    NeedUrgency,
    ResourceGap,
    ResourceGapReason,
    RiskLevel,
    SolutionComponentRef,
    SupplyShape,
)
from .ports import (
    FamilyNeedPolicyPort,
    FamilyNeedRepositoryPort,
    NeedClarificationInput,
    NeedEvent,
    NeedEventPort,
    NeedProfileInput,
    NeedSignalInput,
    SolutionDraftInput,
    SupplyReferencePort,
)

# Triple P Levels 3-5 (STANDARD_SELECTIVE, INTENSIVE_SELECTIVE,
# ENHANCED_SUPPORT): a real person, not self-help content, is the
# proportionate response from here up.
_SERVICE_REQUIRED_TIERS = frozenset(
    {
        InterventionTier.STANDARD_SELECTIVE,
        InterventionTier.INTENSIVE_SELECTIVE,
        InterventionTier.ENHANCED_SUPPORT,
    }
)


@dataclass(frozen=True)
class CaptureSignalResult:
    """Output projection for N0→N1; both objects remain domain facts."""

    signal: NeedSignal
    need: FamilyNeed
    replayed: bool = False


@dataclass(frozen=True)
class ClarifyNeedResult:
    """Transport-safe result for N1 confirmation with replay metadata.

    ``clarify_need`` keeps returning the aggregate for existing domain callers;
    HTTP/worker adapters that need to expose idempotency use
    ``clarify_need_result`` instead.  Replay state is deliberately kept out of
    the FamilyNeed fact itself.
    """

    need: FamilyNeed
    replayed: bool = False


@dataclass(frozen=True)
class ProfileNeedResult:
    """Transport-safe result for N1→N2 profiling with replay metadata."""

    profile: NeedProfile
    replayed: bool = False


@dataclass(frozen=True)
class SolutionDraftResult:
    """N2 output: a draft and, when applicable, an explicit resource gap."""

    draft: SolutionDraft | None
    resource_gap: ResourceGap | None = None
    replayed: bool = False

    @property
    def resolved_components(self) -> tuple[SolutionComponentRef, ...]:
        return self.draft.components if self.draft is not None else ()


class _EventPublisher(Protocol):
    async def publish(self, event: NeedEvent) -> None: ...


class FamilyNeedApplicationService:
    """Use-case orchestration for need capture and initial clarification."""

    def __init__(
        self,
        repository: FamilyNeedRepositoryPort,
        policy: FamilyNeedPolicyPort,
        event_port: NeedEventPort | None = None,
        supply_port: SupplyReferencePort | None = None,
    ) -> None:
        self._repository = repository
        self._policy = policy
        self._event_port: _EventPublisher | None = event_port
        self._supply_port = supply_port
        # Durable adapters should implement this same contract in their UoW.
        # Keeping a local cache here gives Fake/test an executable replay oracle
        # without pretending process-local state is production persistence.
        self._replays: dict[tuple[str, str, str], tuple[str, CaptureSignalResult]] = {}
        self._clarification_replays: dict[tuple[str, str, str], tuple[str, FamilyNeed]] = {}
        self._profile_replays: dict[tuple[str, str, str], tuple[str, NeedProfile]] = {}
        self._solution_replays: dict[tuple[str, str, str], tuple[str, SolutionDraftResult]] = {}
        self._outcome_replays: dict[tuple[str, str, str], tuple[str, FamilyConfirmedOutcome]] = {}

    async def clarify_need(self, command: NeedClarificationInput) -> FamilyNeed:
        """Confirm an explicit need and return its aggregate for domain callers."""

        return (await self.clarify_need_result(command)).need

    async def clarify_need_result(self, command: NeedClarificationInput) -> ClarifyNeedResult:
        """N1 activity: family/guardian confirms an explicit need statement."""

        context = command.context
        need = await self._required_need(context, command.need_id)
        subject_ids = command.subject_person_ids or need.context.subject_person_ids
        authorization_context = replace(context, subject_person_ids=tuple(subject_ids))
        actor_id = await self._authorize(authorization_context, subject_ids)
        assert_family_scope(need.context, authorization_context)
        assert_subjects_in_family(subject_ids, need.context.subject_person_ids)
        key = self._replay_key(context, command.idempotency_key)
        fingerprint = _clarification_fingerprint(command)
        if key is not None:
            previous = self._clarification_replays.get(key)
            if previous is not None:
                if previous[0] != fingerprint:
                    raise FamilyNeedConflictError("family_need_idempotency_payload_mismatch")
                return ClarifyNeedResult(previous[1], replayed=True)
        if need.version != command.expected_version:
            raise FamilyNeedConflictError("family_need_version_stale")
        if need.status not in {NeedStatus.CAPTURED, NeedStatus.CLARIFYING}:
            raise FamilyNeedConflictError("family_need_not_clarifiable")
        if not command.statement.strip() or not command.desired_outcome.strip():
            raise FamilyNeedValidationError("family_need_statement_and_outcome_required")
        clarifying = replace(
            need,
            statement=command.statement.strip(),
            desired_outcome=command.desired_outcome.strip(),
            subject_person_ids=tuple(subject_ids),
            version=need.version + 1,
            updated_at=datetime.now(UTC),
        )
        if clarifying.status is NeedStatus.CAPTURED:
            clarifying = clarifying.start_clarification()
        confirmed = clarifying.confirm(actor_id, context.actor_type)
        await self._repository.save_need(confirmed)
        await self._publish(
            self._event_for(
                "family_need.confirmed",
                confirmed.need_id,
                context,
                confirmed.version,
                subject_ids=confirmed.subject_person_ids,
                idempotency_key=command.idempotency_key,
            )
        )
        if key is not None:
            self._clarification_replays[key] = (fingerprint, confirmed)
        return ClarifyNeedResult(confirmed)

    async def profile_need(self, command: NeedProfileInput) -> NeedProfile:
        """Create a profile and return its aggregate for domain callers."""

        return (await self.profile_need_result(command)).profile

    async def profile_need_result(self, command: NeedProfileInput) -> ProfileNeedResult:
        """N2 activity: classify urgency/complexity/risk without a family score."""

        context = command.context
        need = await self._required_need(context, command.need_id)
        subject_ids = context.subject_person_ids or need.context.subject_person_ids
        authorization_context = replace(context, subject_person_ids=tuple(subject_ids))
        await self._authorize(authorization_context, subject_ids)
        assert_family_scope(need.context, authorization_context)
        key = self._replay_key(context, command.idempotency_key)
        fingerprint = _profile_fingerprint(command)
        if key is not None:
            previous = self._profile_replays.get(key)
            if previous is not None:
                if previous[0] != fingerprint:
                    raise FamilyNeedConflictError("family_need_idempotency_payload_mismatch")
                return ProfileNeedResult(previous[1], replayed=True)
        if need.version != command.expected_need_version:
            raise FamilyNeedConflictError("family_need_version_stale")
        try:
            urgency = NeedUrgency(command.urgency)
            complexity = NeedComplexity(command.complexity)
            risk_level = RiskLevel(command.risk_level)
        except ValueError as exc:
            raise FamilyNeedValidationError("need_profile_classification_invalid") from exc
        profile = NeedProfile.from_need(
            need,
            urgency=urgency,
            complexity=complexity,
            risk_level=risk_level,
            preferred_shapes=tuple(command.preferred_shapes),
            required_capability_keys=tuple(command.required_capability_keys),
            confirmed_by_actor_id=context.actor_id,
        )
        await self._repository.save_profile(profile)
        await self._publish(
            self._event_for(
                "family_need.profile_created",
                profile.profile_id,
                context,
                profile.version,
                subject_ids=need.subject_person_ids,
                idempotency_key=command.idempotency_key,
            )
        )
        if key is not None:
            self._profile_replays[key] = (fingerprint, profile)
        return ProfileNeedResult(profile)

    async def draft_solution(self, command: SolutionDraftInput) -> SolutionDraftResult:
        """N2/N3 activity: compose Product/Service/Solution references only."""

        context = command.context
        need = await self._required_need(context, command.need_id)
        subject_ids = context.subject_person_ids or need.context.subject_person_ids
        authorization_context = replace(context, subject_person_ids=tuple(subject_ids))
        await self._authorize(authorization_context, subject_ids)
        profile = await self._repository.get_profile(
            tenant_id=context.tenant_id, family_id=context.family_id, profile_id=command.profile_id
        )
        if profile is None:
            raise FamilyNeedConflictError("need_profile_not_found")
        assert_family_scope(need.context, authorization_context)
        assert_family_scope(need.context, profile.context)
        assert_subjects_in_family(
            profile.context.subject_person_ids, need.context.subject_person_ids
        )
        key = self._replay_key(context, command.idempotency_key)
        fingerprint = _solution_fingerprint(command)
        if key is not None:
            previous = self._solution_replays.get(key)
            if previous is not None:
                if previous[0] != fingerprint:
                    raise FamilyNeedConflictError("family_need_idempotency_payload_mismatch")
                return replace(previous[1], replayed=True)
        profile.ensure_current(need)
        if profile.version != command.expected_profile_version:
            raise FamilyNeedConflictError("need_profile_version_stale")

        # Triple-P-style intensity gate: STANDARD_SELECTIVE and above (Level 3+)
        # is, by definition, a level where a self-help/product interaction is
        # no longer proportionate — it requires a real person (SERVICE). A
        # PRODUCT-shaped draft request at this tier is rejected rather than
        # silently matched, so "what strength of support" actually constrains
        # "what supply gets matched" instead of being informational only.
        if (
            profile.intervention_tier in _SERVICE_REQUIRED_TIERS
            and command.shape is not SupplyShape.SERVICE
        ):
            raise FamilyNeedValidationError("intervention_tier_requires_service_shape")

        if self._supply_port is None:
            gap = ResourceGap.now(
                command.need_id,
                ResourceGapReason.NO_MATCHING_CAPABILITY,
                "supply_reference_port_unavailable",
            )
            result = SolutionDraftResult(draft=None, resource_gap=gap)
            await self._publish(
                self._event_for(
                    "family_need.resource_gap",
                    command.need_id,
                    context,
                    profile.version,
                    subject_ids=need.subject_person_ids,
                    idempotency_key=command.idempotency_key,
                )
            )
            if key is not None:
                self._solution_replays[key] = (fingerprint, result)
            return result

        resolved: list[SolutionComponentRef] = []
        for component in command.component_refs:
            reference = await self._supply_port.resolve_component(
                tenant_id=context.tenant_id,
                region=context.region,
                locale=context.locale,
                shape=component.shape,
                component_id=component.component_id,
                version=component.version,
            )
            if reference is None:
                gap = await self._supply_port.get_resource_gap(
                    need_id=need.need_id,
                    reason=ResourceGapReason.NO_MATCHING_CAPABILITY,
                    detail=f"component:{component.component_id}",
                )
                result = SolutionDraftResult(draft=None, resource_gap=gap)
                await self._publish(
                    self._event_for(
                        "family_need.resource_gap",
                        need.need_id,
                        context,
                        profile.version,
                        subject_ids=need.subject_person_ids,
                        idempotency_key=command.idempotency_key,
                    )
                )
                if key is not None:
                    self._solution_replays[key] = (fingerprint, result)
                return result
            resolved.append(reference)
        gap = await self._supply_port.check_resource_capacity(
            tenant_id=context.tenant_id,
            family_id=context.family_id,
            need_id=need.need_id,
            component_refs=tuple(resolved),
        )
        if gap is not None:
            result = SolutionDraftResult(draft=None, resource_gap=gap)
            await self._publish(
                self._event_for(
                    "family_need.resource_gap",
                    need.need_id,
                    context,
                    profile.version,
                    subject_ids=need.subject_person_ids,
                    idempotency_key=command.idempotency_key,
                )
            )
            if key is not None:
                self._solution_replays[key] = (fingerprint, result)
            return result
        draft = SolutionDraft.propose(
            need=need,
            profile=profile,
            shape=command.shape,
            components=tuple(resolved),
            commercial_intent=command.commercial_intent,
        )
        await self._repository.save_solution_draft(draft)
        await self._publish(
            self._event_for(
                "family_need.solution_draft_created",
                draft.draft_id,
                context,
                1,
                subject_ids=need.subject_person_ids,
                idempotency_key=command.idempotency_key,
            )
        )
        result = SolutionDraftResult(draft=draft)
        if key is not None:
            self._solution_replays[key] = (fingerprint, result)
        return result

    async def confirm_outcome(
        self,
        *,
        context: NeedContext,
        need_id: str,
        fulfillment_ref: str,
        decision: FamilyOutcomeDecision,
        draft_id: str | None = None,
        family_note: str | None = None,
        idempotency_key: str | None = None,
    ) -> FamilyConfirmedOutcome:
        """N6/N7: the family, and only the family, confirms whether a
        delivered service/course actually helped.

        This is the single most important gate this method enforces: an AI or
        SYSTEM actor attempting to call this must be rejected outright (R9 —
        AI output never becomes a family-authoritative fact). The ordinary
        `_authorize` tenant/subject/consent checks below do not by themselves
        stop an AI actor from confirming an outcome, so
        `assert_family_outcome_confirmer` is called explicitly and first.
        """

        assert_family_outcome_confirmer(context.actor_type)
        need = await self._required_need(context, need_id)
        subject_ids = context.subject_person_ids or need.context.subject_person_ids
        authorization_context = replace(context, subject_person_ids=tuple(subject_ids))
        actor_id = await self._authorize(authorization_context, subject_ids)
        assert_family_scope(need.context, authorization_context)
        if not fulfillment_ref.strip():
            raise FamilyNeedValidationError("family_confirmed_outcome_fulfillment_ref_required")

        key = self._replay_key(context, idempotency_key)
        fingerprint = _outcome_fingerprint(
            need_id=need_id,
            fulfillment_ref=fulfillment_ref,
            decision=decision,
            draft_id=draft_id,
            family_note=family_note,
        )
        if key is not None:
            previous = self._outcome_replays.get(key)
            if previous is not None:
                if previous[0] != fingerprint:
                    raise FamilyNeedConflictError("family_need_idempotency_payload_mismatch")
                return previous[1]

        outcome = FamilyConfirmedOutcome.confirm(
            context=context,
            need_id=need_id,
            draft_id=draft_id,
            fulfillment_ref=fulfillment_ref,
            decision=decision,
            confirmed_by=actor_id,
            family_note=family_note,
        )
        await self._repository.save_outcome(outcome)
        await self._publish(
            self._event_for(
                "family_need.outcome_confirmed",
                outcome.outcome_id,
                context,
                1,
                subject_ids=need.subject_person_ids,
                idempotency_key=idempotency_key,
            )
        )
        if key is not None:
            self._outcome_replays[key] = (fingerprint, outcome)
        return outcome

    async def create_assignment_plan(
        self, *, context: NeedContext, draft: SolutionDraft
    ) -> AssignmentPlan:
        """N4: turn "the family approved this draft" into a queryable
        assignment-decision fact, before anything is pushed to commerce or
        service_booking.

        `authorization_basis` names the family's own approval action, not an
        AI inference — `draft.approve()` already required a human actor
        (see `SolutionDraft.approve`), so this is never called on a
        system/AI-decided draft.
        """

        plan = AssignmentPlan.create(
            tenant_id=context.tenant_id,
            family_id=context.family_id,
            need_id=draft.need_id,
            draft_id=draft.draft_id,
            component_refs=draft.components,
            authorization_basis=f"family_confirmed_draft:{draft.draft_id}",
        )
        await self._repository.save_assignment_plan(plan)
        return plan

    async def resource_gap(
        self, *, context, need_id: str, reason: ResourceGapReason, detail: str
    ) -> ResourceGap:
        await self._authorize(context, context.subject_person_ids)
        if self._supply_port is not None:
            return await self._supply_port.get_resource_gap(
                need_id=need_id, reason=reason, detail=detail
            )
        return ResourceGap.now(need_id, reason, detail)

    def _replay_key(
        self, context: NeedContext, idempotency_key: str | None
    ) -> tuple[str, str, str] | None:
        if not idempotency_key:
            return None
        return (context.tenant_id, context.family_id, idempotency_key)

    @staticmethod
    def _event_for(
        event_name: str,
        aggregate_id: str,
        context: NeedContext,
        version: int,
        *,
        subject_ids: tuple[str, ...],
        idempotency_key: str | None,
    ) -> NeedEvent:
        return NeedEvent(
            event_name=event_name,
            aggregate_id=aggregate_id,
            tenant_id=context.tenant_id,
            family_id=context.family_id,
            version=version,
            correlation_id=context.correlation_id,
            occurred_at=datetime.now(UTC),
            purpose=context.purpose,
            consent_version=context.consent_version,
            data_class=context.data_class,
            subject_person_ids=subject_ids,
            idempotency_key=idempotency_key,
        )

    async def _authorize(self, context, subject_ids: tuple[str, ...]) -> str:
        actor_id = context.actor_id
        if not actor_id:
            raise FamilyNeedForbiddenError("family_need_actor_required")
        await self._policy.assert_tenant_family_scope(context=context, actor_id=actor_id)
        await self._policy.assert_subject_scope(context=context, subject_person_ids=subject_ids)
        await self._policy.assert_consent(
            context=context, purpose=context.purpose, data_class=context.data_class
        )
        return actor_id

    async def _required_need(self, context, need_id: str) -> FamilyNeed:
        need = await self._repository.get_need(
            tenant_id=context.tenant_id, family_id=context.family_id, need_id=need_id
        )
        if need is None:
            raise FamilyNeedConflictError("family_need_not_found")
        return need

    async def capture_signal(self, command: NeedSignalInput) -> CaptureSignalResult:
        context = command.context
        actor_id = context.actor_id
        if not actor_id:
            raise FamilyNeedForbiddenError("need_signal_actor_required")
        subject_ids = command.subject_person_ids or context.subject_person_ids
        # Authorization and consent are checked before looking at a replay so
        # an old idempotency key cannot become a cross-actor read capability.
        await self._policy.assert_tenant_family_scope(context=context, actor_id=actor_id)
        await self._policy.assert_subject_scope(context=context, subject_person_ids=subject_ids)
        await self._policy.assert_consent(
            context=context, purpose=context.purpose, data_class=context.data_class
        )
        fingerprint = _fingerprint(command, subject_ids)
        if command.idempotency_key:
            replay_key = (context.tenant_id, context.family_id, command.idempotency_key)
            previous = self._replays.get(replay_key)
            if previous is not None:
                if previous[0] != fingerprint:
                    raise FamilyNeedConflictError("need_signal_idempotency_payload_mismatch")
                return replace(previous[1], replayed=True)

        try:
            source = (
                command.source
                if isinstance(command.source, NeedSignalSource)
                else NeedSignalSource(command.source)
            )
        except ValueError as exc:
            raise FamilyNeedValidationError("need_signal_source_invalid") from exc
        try:
            category = (
                command.category
                if isinstance(command.category, NeedCategory)
                else NeedCategory(command.category)
            )
        except ValueError as exc:
            raise FamilyNeedValidationError("family_need_category_invalid") from exc
        if not command.statement or not command.statement.strip():
            raise FamilyNeedValidationError("family_need_statement_required")
        if not command.desired_outcome or not command.desired_outcome.strip():
            raise FamilyNeedValidationError("family_need_desired_outcome_required")

        signal = NeedSignal.capture(
            context=context,
            source=source,
            raw_text=command.raw_text,
            signal_id=command.signal_id,
            expires_at=command.expires_at,
            evidence_refs=command.evidence_refs,
        )
        # N1 is a family expression made explicit, not an AI diagnosis.
        need = FamilyNeed.from_signal(
            signal,
            statement=command.statement,
            desired_outcome=command.desired_outcome,
            subject_person_ids=subject_ids,
            category=category,
        )
        await self._repository.save_signal(signal)
        await self._repository.save_need(need)
        await self._publish(
            NeedEvent(
                event_name="family_need.signal_captured",
                aggregate_id=signal.signal_id,
                tenant_id=context.tenant_id,
                family_id=context.family_id,
                version=1,
                correlation_id=context.correlation_id,
                occurred_at=datetime.now(UTC),
                purpose=context.purpose,
                consent_version=context.consent_version,
                data_class=context.data_class,
                subject_person_ids=subject_ids,
                idempotency_key=command.idempotency_key,
            )
        )
        await self._publish(
            NeedEvent(
                event_name="family_need.created",
                aggregate_id=need.need_id,
                tenant_id=context.tenant_id,
                family_id=context.family_id,
                version=need.version,
                correlation_id=context.correlation_id,
                occurred_at=datetime.now(UTC),
                purpose=context.purpose,
                consent_version=context.consent_version,
                data_class=context.data_class,
                subject_person_ids=subject_ids,
                idempotency_key=command.idempotency_key,
            )
        )
        result = CaptureSignalResult(signal=signal, need=need)
        if command.idempotency_key:
            self._replays[(context.tenant_id, context.family_id, command.idempotency_key)] = (
                fingerprint,
                result,
            )
        return result

    async def _publish(self, event: NeedEvent) -> None:
        if self._event_port is not None:
            await self._event_port.publish(event)
            return
        await self._repository.append_event(event)


def _fingerprint(command: NeedSignalInput, subject_ids: tuple[str, ...]) -> str:
    payload = {
        "tenant_id": command.context.tenant_id,
        "family_id": command.context.family_id,
        "actor_id": command.context.actor_id,
        "purpose": command.context.purpose,
        "consent_version": command.context.consent_version,
        "data_class": str(command.context.data_class),
        "locale": command.context.locale,
        "region": command.context.region,
        "raw_text": command.raw_text,
        "source": str(command.source),
        "signal_id": command.signal_id,
        "expires_at": command.expires_at.isoformat() if command.expires_at else None,
        "subject_person_ids": subject_ids,
        "statement": command.statement,
        "desired_outcome": command.desired_outcome,
        "category": str(command.category),
        "evidence_refs": [
            {
                "media_ref": ref.media_ref,
                "kind": str(ref.kind),
                "provenance_ref": ref.provenance_ref,
                "consent_version": ref.consent_version,
            }
            for ref in command.evidence_refs
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _clarification_fingerprint(command: NeedClarificationInput) -> str:
    return _hash_payload(
        {
            "need_id": command.need_id,
            "statement": command.statement,
            "desired_outcome": command.desired_outcome,
            "subject_person_ids": command.subject_person_ids,
            "expected_version": command.expected_version,
        }
    )


def _profile_fingerprint(command: NeedProfileInput) -> str:
    return _hash_payload(
        {
            "need_id": command.need_id,
            "expected_need_version": command.expected_need_version,
            "urgency": command.urgency,
            "complexity": command.complexity,
            "risk_level": command.risk_level,
            "preferred_shapes": [str(item) for item in command.preferred_shapes],
            "required_capability_keys": command.required_capability_keys,
        }
    )


def _solution_fingerprint(command: SolutionDraftInput) -> str:
    return _hash_payload(
        {
            "need_id": command.need_id,
            "profile_id": command.profile_id,
            "expected_profile_version": command.expected_profile_version,
            "shape": str(command.shape),
            "component_refs": [
                {
                    "component_id": item.component_id,
                    "shape": str(item.shape),
                    "version": item.version,
                    "required": item.required,
                    "quantity": item.quantity,
                }
                for item in command.component_refs
            ],
            "commercial_intent": command.commercial_intent,
        }
    )


def _outcome_fingerprint(
    *,
    need_id: str,
    fulfillment_ref: str,
    decision: FamilyOutcomeDecision,
    draft_id: str | None,
    family_note: str | None,
) -> str:
    return _hash_payload(
        {
            "need_id": need_id,
            "fulfillment_ref": fulfillment_ref,
            "decision": str(decision),
            "draft_id": draft_id,
            "family_note": family_note,
        }
    )


def _hash_payload(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


__all__ = [
    "CaptureSignalResult",
    "ClarifyNeedResult",
    "FamilyNeedApplicationService",
    "ProfileNeedResult",
    "SolutionDraftResult",
]
