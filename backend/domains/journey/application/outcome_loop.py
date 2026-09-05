"""S05-S08 result loop contract.

This module keeps the business boundary explicit while the durable journey
repository is being completed.  It is an in-memory test adapter, not a
production store: action facts are recorded first, and every later artifact
requires an explicit family decision.  In particular, a completed action
never becomes an outcome, recommendation, story, or renewal automatically.

The sequence represented here is:

``ActionFact -> ChallengeReview -> Outcome(PENDING) -> Outcome(CONFIRMED)``
``                     -> private Story -> Recommendation(DRAFT)``
``                     -> ServiceCaseCommand -> DeliveryReceipt -> Renewal``
``                     -> AnnualReviewProjection``

All objects carry tenant/family scope.  The production implementation must
persist the same transitions with audit and outbox records in one transaction
and route deletion handles to the durable deletion worker.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from backend.platform.consent import ConsentGate, ConsentGrant, ConsentPurpose

from ..domain.errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)


class ActionFactStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"


class ChallengeDecision(StrEnum):
    CONTINUE = "CONTINUE"
    ADJUST = "ADJUST"
    PAUSE = "PAUSE"


class ChallengeReviewStatus(StrEnum):
    PENDING_FAMILY_DECISION = "PENDING_FAMILY_DECISION"
    ACCEPTED = "ACCEPTED"
    ADJUSTMENT_REQUESTED = "ADJUSTMENT_REQUESTED"
    PAUSED = "PAUSED"


class OutcomeStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    WITHDRAWN = "WITHDRAWN"


class StoryVisibility(StrEnum):
    PRIVATE = "PRIVATE"
    SHARED = "SHARED"


class RecommendationStatus(StrEnum):
    DRAFT = "DRAFT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class ServiceCaseCommandStatus(StrEnum):
    REQUESTED = "REQUESTED"


class ServiceDeliveryStatus(StrEnum):
    DELIVERED = "DELIVERED"


class RenewalStatus(StrEnum):
    REQUESTED = "REQUESTED"
    WITHDRAWN = "WITHDRAWN"


@dataclass(frozen=True)
class LoopNodeContract:
    """L4/L5 traceability for the result loop."""

    node_id: str
    inputs: tuple[str, ...]
    activity: str
    outputs: tuple[str, ...]
    command: str
    event: str
    unique_writer: str
    rule: str


S05_S08_NODE_CONTRACTS = (
    LoopNodeContract(
        node_id="S07-N03",
        inputs=("ActionTask", "check_in", "note"),
        activity="record behaviour fact",
        outputs=("ActionFact",),
        command="RecordActionFact",
        event="ActionFactRecorded",
        unique_writer="journey.action_fact",
        rule="idempotent; no inferred outcome, score, or rank",
    ),
    LoopNodeContract(
        node_id="S07-N05",
        inputs=("ActionFact[day 1..21]", "family_decision"),
        activity="close challenge and surface missing days",
        outputs=("ChallengeReview",),
        command="CloseChallenge",
        event="ChallengeClosed",
        unique_writer="journey.challenge_review",
        rule="missing days remain explicit; completion is not an outcome",
    ),
    LoopNodeContract(
        node_id="S08-N02",
        inputs=("ChallengeReview", "evidence"),
        activity="propose then family-confirm an observed result",
        outputs=("OutcomeRecord(PENDING|CONFIRMED)",),
        command="ProposeOutcome / ConfirmOutcome",
        event="OutcomeProposed / OutcomeConfirmed",
        unique_writer="journey.outcome_record",
        rule="AI may propose; only a human actor confirms canonical fact",
    ),
    LoopNodeContract(
        node_id="S08-N03",
        inputs=("OutcomeRecord(CONFIRMED)", "story_consent"),
        activity="write private story or explicitly shared story",
        outputs=("FamilyStory",),
        command="CreateFamilyStory / WithdrawFamilyStory",
        event="StoryCreated / StoryWithdrawn",
        unique_writer="journey.family_story",
        rule="private by default; shared visibility requires explicit consent",
    ),
    LoopNodeContract(
        node_id="S09-N03",
        inputs=("OutcomeRecord(CONFIRMED)", "candidate_refs"),
        activity="produce an explainable next-step draft",
        outputs=("RecommendationDraft",),
        command="DraftRecommendation",
        event="RecommendationDrafted",
        unique_writer="journey.recommendation",
        rule="draft only; family decision creates a service case",
    ),
    LoopNodeContract(
        node_id="S10-N01",
        inputs=("RecommendationDraft", "family_decision"),
        activity="open and deliver a selected service case",
        outputs=("ServiceCaseCommand", "ServiceDeliveryReceipt"),
        command="AcceptRecommendation / RecordDeliveryReceipt",
        event="ServiceCaseRequested / ServiceDelivered",
        unique_writer="service.case (canonical service port)",
        rule="renewal waits for delivery evidence; no automatic purchase",
    ),
    LoopNodeContract(
        node_id="S08-N04",
        inputs=("OutcomeRecord(CONFIRMED)", "consented stories"),
        activity="build private annual review projection",
        outputs=("AnnualReviewProjection",),
        command="BuildAnnualReview / RequestRenewal",
        event="AnnualReviewGenerated / RenewalRequested",
        unique_writer="journey.annual_review",
        rule="no ranking or family total; deletable references are retained",
    ),
)


@dataclass(frozen=True)
class ActionFact:
    action_id: str
    tenant_id: str
    family_id: str
    plan_id: str
    task_id: str
    day_number: int
    status: ActionFactStatus
    recorded_by: str
    evidence_refs: tuple[str, ...]
    recorded_at: datetime
    locale: str = "zh-CN"
    deletion_ref: str = ""


@dataclass(frozen=True)
class ChallengeReview:
    review_id: str
    tenant_id: str
    family_id: str
    plan_id: str
    action_ids: tuple[str, ...]
    observed_days: tuple[int, ...]
    missing_days: tuple[int, ...]
    decision: ChallengeDecision
    status: ChallengeReviewStatus
    limitations: tuple[str, ...]
    decided_by: str
    decided_at: datetime
    locale: str = "zh-CN"
    deletion_ref: str = ""


@dataclass(frozen=True)
class OutcomeRecord:
    outcome_id: str
    tenant_id: str
    family_id: str
    review_id: str
    subject_ref: str
    statement: str
    evidence_refs: tuple[str, ...]
    status: OutcomeStatus
    proposed_by: str
    confirmed_by: str | None
    confirmed_at: datetime | None
    deletion_ref: str
    locale: str = "zh-CN"


@dataclass(frozen=True)
class FamilyStory:
    story_id: str
    tenant_id: str
    family_id: str
    outcome_ids: tuple[str, ...]
    title: str
    body: str
    media_refs: tuple[str, ...]
    visibility: StoryVisibility
    story_consent_ref: str | None
    created_by: str
    withdrawn_at: datetime | None
    deletion_ref: str
    locale: str = "zh-CN"


@dataclass(frozen=True)
class RecommendationDraft:
    recommendation_id: str
    tenant_id: str
    family_id: str
    outcome_ids: tuple[str, ...]
    candidate_refs: tuple[str, ...]
    purpose: str
    rationale: str
    limitations: tuple[str, ...]
    status: RecommendationStatus
    created_by: str
    deletion_ref: str
    locale: str = "zh-CN"


@dataclass(frozen=True)
class ServiceCaseCommand:
    """Command handed to the canonical ``service/fgcn`` case port.

    This module must not create a second ``ServiceCase`` aggregate.  The
    command carries enough scope for the service Named Action to create the
    real case in its own domain.
    """

    command_id: str
    service_case_ref: str
    tenant_id: str
    family_id: str
    recommendation_id: str
    selected_candidate_ref: str
    subject_refs: tuple[str, ...]
    status: ServiceCaseCommandStatus
    issued_by: str
    issued_at: datetime
    deletion_ref: str
    locale: str = "zh-CN"

    @property
    def case_id(self) -> str:
        """Compatibility alias for callers that pass a service case reference."""
        return self.service_case_ref


@dataclass(frozen=True)
class ServiceDeliveryReceipt:
    """Receipt returned by the canonical service delivery port."""

    service_case_ref: str
    tenant_id: str
    family_id: str
    evidence_refs: tuple[str, ...]
    delivered_by: str
    delivered_at: datetime
    status: ServiceDeliveryStatus
    deletion_ref: str
    locale: str = "zh-CN"


@dataclass(frozen=True)
class AnnualReviewProjection:
    projection_id: str
    tenant_id: str
    family_id: str
    outcome_ids: tuple[str, ...]
    story_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    generated_at: datetime
    deletion_refs: tuple[str, ...]
    locale: str = "zh-CN"
    deletion_ref: str = ""


@dataclass(frozen=True)
class RenewalIntent:
    renewal_id: str
    tenant_id: str
    family_id: str
    case_id: str
    annual_projection_id: str | None
    candidate_ref: str
    status: RenewalStatus
    requested_by: str
    deletion_ref: str
    locale: str = "zh-CN"


@dataclass(frozen=True)
class OutcomeLoopSnapshot:
    """Read-only evidence projection for a family.

    This projection deliberately contains no score, rank, level, or completion
    percentage.  It is useful for contract tests and for a future API read
    model; it is not a source of business facts.
    """

    tenant_id: str
    family_id: str
    actions: tuple[ActionFact, ...]
    reviews: tuple[ChallengeReview, ...]
    outcomes: tuple[OutcomeRecord, ...]
    stories: tuple[FamilyStory, ...]
    recommendations: tuple[RecommendationDraft, ...]
    service_case_commands: tuple[ServiceCaseCommand, ...]
    delivery_receipts: tuple[ServiceDeliveryReceipt, ...]
    annual_projections: tuple[AnnualReviewProjection, ...]
    renewals: tuple[RenewalIntent, ...]
    locale: str = "zh-CN"


class GrowthOutcomeLoop:
    """Deterministic application contract for the S05-S08 result loop.

    ``now`` is injectable so replay tests can assert exact receipts.  The
    object is intentionally scoped to one process and must be replaced by a
    PostgreSQL repository/outbox adapter before production release.
    """

    production_ready = False

    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        locale: str = "zh-CN",
        consent_loader: Callable[[str, ConsentPurpose], Iterable[ConsentGrant]] | None = None,
    ) -> None:
        if not locale.strip() or len(locale) > 32:
            raise JourneyValidationError("invalid_locale")
        self._now = now or (lambda: datetime.now(UTC))
        self._locale = locale
        self._consent_loader = consent_loader or (lambda _subject, _purpose: ())
        self._actions: dict[str, ActionFact] = {}
        self._reviews: dict[str, ChallengeReview] = {}
        self._outcomes: dict[str, OutcomeRecord] = {}
        self._stories: dict[str, FamilyStory] = {}
        self._recommendations: dict[str, RecommendationDraft] = {}
        self._case_commands: dict[str, ServiceCaseCommand] = {}
        self._deliveries: dict[str, ServiceDeliveryReceipt] = {}
        self._annual: dict[str, AnnualReviewProjection] = {}
        self._renewals: dict[str, RenewalIntent] = {}
        self._idempotency: dict[tuple[str, str, str, str], tuple[tuple[object, ...], object]] = {}

    def record_action(
        self,
        *,
        tenant_id: str,
        family_id: str,
        plan_id: str,
        task_id: str,
        day_number: int,
        status: ActionFactStatus,
        actor_id: str,
        idempotency_key: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> ActionFact:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        self._assert_human_actor(actor_id)
        if not 1 <= day_number <= 21:
            raise JourneyValidationError("action_day_must_be_between_1_and_21")
        if not plan_id.strip() or not task_id.strip():
            raise JourneyValidationError("action_plan_and_task_required")
        action_id = f"action:{tenant_id}:{family_id}:{task_id}"
        fingerprint = (
            action_id,
            plan_id,
            task_id,
            day_number,
            status.value,
            actor_id,
            tuple(evidence_refs),
        )
        replay = self._replay("record_action", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        existing = self._actions.get(action_id)
        if existing is not None:
            if not self._action_matches(
                existing,
                plan_id=plan_id,
                day_number=day_number,
                status=status,
                actor_id=actor_id,
                evidence_refs=evidence_refs,
            ):
                raise JourneyConflictError("action_already_recorded_with_different_fact")
            self._remember(
                "record_action", tenant_id, family_id, idempotency_key, fingerprint, existing
            )
            return existing
        action = self._new_action(
            action_id,
            tenant_id,
            family_id,
            plan_id,
            task_id,
            day_number,
            status,
            actor_id,
            evidence_refs,
        )
        self._actions[action.action_id] = action
        self._remember("record_action", tenant_id, family_id, idempotency_key, fingerprint, action)
        return action

    def close_challenge(
        self,
        *,
        tenant_id: str,
        family_id: str,
        plan_id: str,
        decision: ChallengeDecision,
        actor_id: str,
        idempotency_key: str,
    ) -> ChallengeReview:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        self._assert_human_actor(actor_id)
        if not plan_id.strip():
            raise JourneyValidationError("challenge_plan_required")
        action_ids = tuple(
            sorted(
                action.action_id
                for action in self._actions.values()
                if action.tenant_id == tenant_id
                and action.family_id == family_id
                and action.plan_id == plan_id
            )
        )
        observed_days = tuple(
            sorted(
                {
                    action.day_number
                    for action in self._actions.values()
                    if action.action_id in action_ids
                }
            )
        )
        missing_days = tuple(day for day in range(1, 22) if day not in observed_days)
        limitations = ("MISSING_ACTION_DAYS_EXPLICIT",) if missing_days else ()
        fingerprint = (plan_id, action_ids, decision.value, actor_id)
        replay = self._replay("close_challenge", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        review = ChallengeReview(
            review_id=str(uuid4()),
            tenant_id=tenant_id,
            family_id=family_id,
            plan_id=plan_id,
            action_ids=action_ids,
            observed_days=observed_days,
            missing_days=missing_days,
            decision=decision,
            status={
                ChallengeDecision.CONTINUE: ChallengeReviewStatus.ACCEPTED,
                ChallengeDecision.ADJUST: ChallengeReviewStatus.ADJUSTMENT_REQUESTED,
                ChallengeDecision.PAUSE: ChallengeReviewStatus.PAUSED,
            }[decision],
            limitations=limitations,
            decided_by=actor_id,
            decided_at=self._timestamp(),
            locale=self._locale,
            deletion_ref=f"challenge-review:{tenant_id}:{family_id}:{plan_id}",
        )
        self._reviews[review.review_id] = review
        self._remember(
            "close_challenge", tenant_id, family_id, idempotency_key, fingerprint, review
        )
        return review

    def propose_outcome(
        self,
        *,
        tenant_id: str,
        family_id: str,
        review_id: str,
        subject_ref: str,
        statement: str,
        evidence_refs: tuple[str, ...],
        actor_id: str,
        idempotency_key: str,
    ) -> OutcomeRecord:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        review = self._required(self._reviews, review_id, "challenge_review_not_found")
        self._assert_record_scope(review, tenant_id, family_id)
        if review.status is ChallengeReviewStatus.PAUSED:
            raise JourneyConflictError("paused_challenge_cannot_propose_outcome")
        if not subject_ref.strip() or not statement.strip():
            raise JourneyValidationError("outcome_subject_and_statement_required")
        if not evidence_refs:
            raise JourneyValidationError("outcome_evidence_required")
        fingerprint = (review_id, subject_ref, statement, tuple(evidence_refs), actor_id)
        replay = self._replay("propose_outcome", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        outcome = OutcomeRecord(
            outcome_id=str(uuid4()),
            tenant_id=tenant_id,
            family_id=family_id,
            review_id=review_id,
            subject_ref=subject_ref,
            statement=statement,
            evidence_refs=tuple(evidence_refs),
            status=OutcomeStatus.PENDING,
            proposed_by=actor_id,
            confirmed_by=None,
            confirmed_at=None,
            deletion_ref=f"outcome:{tenant_id}:{family_id}",
            locale=self._locale,
        )
        self._outcomes[outcome.outcome_id] = outcome
        self._remember(
            "propose_outcome", tenant_id, family_id, idempotency_key, fingerprint, outcome
        )
        return outcome

    def confirm_outcome(
        self,
        *,
        tenant_id: str,
        family_id: str,
        outcome_id: str,
        actor_id: str,
        idempotency_key: str,
    ) -> OutcomeRecord:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        self._assert_human_actor(actor_id)
        outcome = self._required(self._outcomes, outcome_id, "outcome_not_found")
        self._assert_record_scope(outcome, tenant_id, family_id)
        fingerprint = (outcome_id, actor_id)
        replay = self._replay("confirm_outcome", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        if outcome.status is OutcomeStatus.WITHDRAWN:
            raise JourneyConflictError("withdrawn_outcome_cannot_be_confirmed")
        if outcome.status is OutcomeStatus.CONFIRMED:
            if outcome.confirmed_by == actor_id:
                self._remember(
                    "confirm_outcome", tenant_id, family_id, idempotency_key, fingerprint, outcome
                )
                return outcome
            raise JourneyConflictError("outcome_already_confirmed")
        confirmed = OutcomeRecord(
            **{
                **outcome.__dict__,
                "status": OutcomeStatus.CONFIRMED,
                "confirmed_by": actor_id,
                "confirmed_at": self._timestamp(),
            }
        )
        self._outcomes[outcome_id] = confirmed
        self._remember(
            "confirm_outcome", tenant_id, family_id, idempotency_key, fingerprint, confirmed
        )
        return confirmed

    def create_story(
        self,
        *,
        tenant_id: str,
        family_id: str,
        outcome_ids: tuple[str, ...],
        title: str,
        body: str,
        actor_id: str,
        idempotency_key: str,
        visibility: StoryVisibility = StoryVisibility.PRIVATE,
        story_consent_ref: str | None = None,
        media_refs: tuple[str, ...] = (),
    ) -> FamilyStory:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        self._assert_human_actor(actor_id)
        if not outcome_ids or not title.strip() or not body.strip():
            raise JourneyValidationError("story_title_body_and_outcomes_required")
        if visibility is StoryVisibility.SHARED and not (story_consent_ref or "").strip():
            raise JourneyForbiddenError("shared_story_requires_explicit_consent")
        outcomes = tuple(
            self._required(self._outcomes, item, "outcome_not_found") for item in outcome_ids
        )
        for outcome in outcomes:
            self._assert_record_scope(outcome, tenant_id, family_id)
            if outcome.status is not OutcomeStatus.CONFIRMED:
                raise JourneyConflictError("story_requires_confirmed_outcomes")
        if visibility is StoryVisibility.SHARED:
            self._assert_live_consent(
                tuple(sorted({outcome.subject_ref for outcome in outcomes})),
                ConsentPurpose.GROWTH_TRACKING,
                required_consent_id=story_consent_ref,
            )
        fingerprint = (
            outcome_ids,
            title,
            body,
            actor_id,
            visibility.value,
            story_consent_ref,
            tuple(media_refs),
        )
        replay = self._replay("create_story", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        story = FamilyStory(
            story_id=str(uuid4()),
            tenant_id=tenant_id,
            family_id=family_id,
            outcome_ids=tuple(outcome_ids),
            title=title,
            body=body,
            media_refs=tuple(media_refs),
            visibility=visibility,
            story_consent_ref=story_consent_ref,
            created_by=actor_id,
            withdrawn_at=None,
            deletion_ref=f"story:{tenant_id}:{family_id}",
            locale=self._locale,
        )
        self._stories[story.story_id] = story
        self._remember("create_story", tenant_id, family_id, idempotency_key, fingerprint, story)
        return story

    def withdraw_story(
        self,
        *,
        tenant_id: str,
        family_id: str,
        story_id: str,
        actor_id: str,
        idempotency_key: str,
    ) -> FamilyStory:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        self._assert_human_actor(actor_id)
        story = self._required(self._stories, story_id, "story_not_found")
        self._assert_record_scope(story, tenant_id, family_id)
        fingerprint = (story_id, actor_id)
        replay = self._replay("withdraw_story", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        if story.withdrawn_at is not None:
            self._remember(
                "withdraw_story", tenant_id, family_id, idempotency_key, fingerprint, story
            )
            return story
        withdrawn = FamilyStory(**{**story.__dict__, "withdrawn_at": self._timestamp()})
        self._stories[story_id] = withdrawn
        self._remember(
            "withdraw_story", tenant_id, family_id, idempotency_key, fingerprint, withdrawn
        )
        return withdrawn

    def draft_recommendation(
        self,
        *,
        tenant_id: str,
        family_id: str,
        outcome_ids: tuple[str, ...],
        candidate_refs: tuple[str, ...],
        purpose: str,
        rationale: str,
        actor_id: str,
        idempotency_key: str,
        limitations: tuple[str, ...] = (),
    ) -> RecommendationDraft:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        if not outcome_ids or not candidate_refs or not purpose.strip() or not rationale.strip():
            raise JourneyValidationError("recommendation_inputs_required")
        outcomes = tuple(
            self._required(self._outcomes, item, "outcome_not_found") for item in outcome_ids
        )
        for outcome in outcomes:
            self._assert_record_scope(outcome, tenant_id, family_id)
            if outcome.status is not OutcomeStatus.CONFIRMED:
                raise JourneyConflictError("recommendation_requires_confirmed_outcomes")
        self._assert_live_consent(
            tuple(sorted({outcome.subject_ref for outcome in outcomes})),
            ConsentPurpose.AI_PERSONALIZATION,
        )
        fingerprint = (
            outcome_ids,
            candidate_refs,
            purpose,
            rationale,
            actor_id,
            tuple(limitations),
        )
        replay = self._replay(
            "draft_recommendation", tenant_id, family_id, idempotency_key, fingerprint
        )
        if replay is not None:
            return replay  # type: ignore[return-value]
        recommendation = RecommendationDraft(
            recommendation_id=str(uuid4()),
            tenant_id=tenant_id,
            family_id=family_id,
            outcome_ids=tuple(outcome_ids),
            candidate_refs=tuple(candidate_refs),
            purpose=purpose,
            rationale=rationale,
            limitations=tuple(limitations),
            status=RecommendationStatus.DRAFT,
            created_by=actor_id,
            deletion_ref=f"recommendation:{tenant_id}:{family_id}",
            locale=self._locale,
        )
        self._recommendations[recommendation.recommendation_id] = recommendation
        self._remember(
            "draft_recommendation",
            tenant_id,
            family_id,
            idempotency_key,
            fingerprint,
            recommendation,
        )
        return recommendation

    def accept_recommendation(
        self,
        *,
        tenant_id: str,
        family_id: str,
        recommendation_id: str,
        candidate_ref: str,
        actor_id: str,
        idempotency_key: str,
    ) -> ServiceCaseCommand:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        self._assert_human_actor(actor_id)
        recommendation = self._required(
            self._recommendations, recommendation_id, "recommendation_not_found"
        )
        self._assert_record_scope(recommendation, tenant_id, family_id)
        if candidate_ref not in recommendation.candidate_refs:
            raise JourneyValidationError("recommendation_candidate_not_found")
        fingerprint = (recommendation_id, candidate_ref, actor_id)
        replay = self._replay(
            "accept_recommendation", tenant_id, family_id, idempotency_key, fingerprint
        )
        if replay is not None:
            return replay  # type: ignore[return-value]
        if recommendation.status is not RecommendationStatus.DRAFT:
            raise JourneyConflictError("recommendation_is_not_open")
        accepted = RecommendationDraft(
            **{**recommendation.__dict__, "status": RecommendationStatus.ACCEPTED}
        )
        self._recommendations[recommendation_id] = accepted
        command = ServiceCaseCommand(
            command_id=str(uuid4()),
            service_case_ref=f"service-request:{uuid4()}",
            tenant_id=tenant_id,
            family_id=family_id,
            recommendation_id=recommendation_id,
            selected_candidate_ref=candidate_ref,
            subject_refs=tuple(
                sorted(
                    {
                        outcome.subject_ref
                        for outcome in (
                            self._required(self._outcomes, outcome_id, "outcome_not_found")
                            for outcome_id in recommendation.outcome_ids
                        )
                    }
                )
            ),
            status=ServiceCaseCommandStatus.REQUESTED,
            issued_by=actor_id,
            issued_at=self._timestamp(),
            deletion_ref=f"service-case:{tenant_id}:{family_id}",
            locale=self._locale,
        )
        self._case_commands[command.service_case_ref] = command
        self._remember(
            "accept_recommendation", tenant_id, family_id, idempotency_key, fingerprint, command
        )
        return command

    def record_delivery(
        self,
        *,
        tenant_id: str,
        family_id: str,
        case_id: str,
        evidence_refs: tuple[str, ...],
        actor_id: str,
        idempotency_key: str,
    ) -> ServiceDeliveryReceipt:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        self._assert_human_actor(actor_id)
        command = self._required(self._case_commands, case_id, "service_case_command_not_found")
        self._assert_record_scope(command, tenant_id, family_id)
        self._assert_live_consent(command.subject_refs, ConsentPurpose.SERVICE)
        if not evidence_refs:
            raise JourneyValidationError("service_delivery_evidence_required")
        fingerprint = (case_id, tuple(evidence_refs), actor_id)
        replay = self._replay("record_delivery", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        if case_id in self._deliveries:
            existing = self._deliveries[case_id]
            if existing.evidence_refs == tuple(evidence_refs):
                self._remember(
                    "record_delivery",
                    tenant_id,
                    family_id,
                    idempotency_key,
                    fingerprint,
                    existing,
                )
                return existing
            raise JourneyConflictError("service_delivery_already_recorded")
        delivered = ServiceDeliveryReceipt(
            service_case_ref=case_id,
            tenant_id=tenant_id,
            family_id=family_id,
            evidence_refs=tuple(evidence_refs),
            delivered_by=actor_id,
            delivered_at=self._timestamp(),
            status=ServiceDeliveryStatus.DELIVERED,
            deletion_ref=f"service-delivery:{tenant_id}:{family_id}:{case_id}",
            locale=self._locale,
        )
        self._deliveries[case_id] = delivered
        self._remember(
            "record_delivery", tenant_id, family_id, idempotency_key, fingerprint, delivered
        )
        return delivered

    def build_annual_review(
        self,
        *,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        idempotency_key: str,
        include_story_ids: tuple[str, ...] = (),
    ) -> AnnualReviewProjection:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        outcomes = tuple(
            sorted(
                (
                    outcome
                    for outcome in self._outcomes.values()
                    if outcome.tenant_id == tenant_id
                    and outcome.family_id == family_id
                    and outcome.status is OutcomeStatus.CONFIRMED
                ),
                key=lambda item: item.outcome_id,
            )
        )
        if outcomes:
            self._assert_live_consent(
                tuple(sorted({outcome.subject_ref for outcome in outcomes})),
                ConsentPurpose.GROWTH_TRACKING,
            )
        stories: list[FamilyStory] = []
        for story_id in include_story_ids:
            story = self._required(self._stories, story_id, "story_not_found")
            self._assert_record_scope(story, tenant_id, family_id)
            if story.withdrawn_at is None and (
                story.visibility is StoryVisibility.PRIVATE or story.story_consent_ref
            ):
                stories.append(story)
        limitations = ("ONLY_CONFIRMED_OUTCOMES",) if not outcomes else ()
        fingerprint = (
            tuple(item.outcome_id for item in outcomes),
            tuple(item.story_id for item in stories),
            actor_id,
        )
        replay = self._replay(
            "build_annual_review", tenant_id, family_id, idempotency_key, fingerprint
        )
        if replay is not None:
            return replay  # type: ignore[return-value]
        projection = AnnualReviewProjection(
            projection_id=str(uuid4()),
            tenant_id=tenant_id,
            family_id=family_id,
            outcome_ids=tuple(item.outcome_id for item in outcomes),
            story_ids=tuple(item.story_id for item in stories),
            limitations=limitations,
            generated_at=self._timestamp(),
            deletion_refs=tuple(
                [item.deletion_ref for item in outcomes] + [item.deletion_ref for item in stories]
            ),
            locale=self._locale,
            deletion_ref=f"annual-review:{tenant_id}:{family_id}",
        )
        self._annual[projection.projection_id] = projection
        self._remember(
            "build_annual_review", tenant_id, family_id, idempotency_key, fingerprint, projection
        )
        return projection

    def request_renewal(
        self,
        *,
        tenant_id: str,
        family_id: str,
        case_id: str,
        candidate_ref: str,
        actor_id: str,
        idempotency_key: str,
        annual_projection_id: str | None = None,
    ) -> RenewalIntent:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key)
        self._assert_human_actor(actor_id)
        command = self._required(self._case_commands, case_id, "service_case_command_not_found")
        self._assert_record_scope(command, tenant_id, family_id)
        receipt = self._deliveries.get(case_id)
        if receipt is None or receipt.status is not ServiceDeliveryStatus.DELIVERED:
            raise JourneyConflictError("renewal_requires_delivered_service")
        if candidate_ref != command.selected_candidate_ref:
            raise JourneyValidationError("renewal_candidate_must_match_delivered_case")
        if annual_projection_id is not None:
            projection = self._required(
                self._annual, annual_projection_id, "annual_review_not_found"
            )
            self._assert_record_scope(projection, tenant_id, family_id)
        fingerprint = (case_id, candidate_ref, annual_projection_id, actor_id)
        replay = self._replay("request_renewal", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        renewal = RenewalIntent(
            renewal_id=str(uuid4()),
            tenant_id=tenant_id,
            family_id=family_id,
            case_id=case_id,
            annual_projection_id=annual_projection_id,
            candidate_ref=candidate_ref,
            status=RenewalStatus.REQUESTED,
            requested_by=actor_id,
            deletion_ref=f"renewal:{tenant_id}:{family_id}",
            locale=self._locale,
        )
        self._renewals[renewal.renewal_id] = renewal
        self._remember(
            "request_renewal", tenant_id, family_id, idempotency_key, fingerprint, renewal
        )
        return renewal

    def snapshot(self, *, tenant_id: str, family_id: str) -> OutcomeLoopSnapshot:
        if not tenant_id.strip() or not family_id.strip():
            raise JourneyValidationError("tenant_and_family_required")
        return OutcomeLoopSnapshot(
            tenant_id=tenant_id,
            family_id=family_id,
            actions=tuple(
                item
                for item in self._actions.values()
                if self._in_scope(item, tenant_id, family_id)
            ),
            reviews=tuple(
                item
                for item in self._reviews.values()
                if self._in_scope(item, tenant_id, family_id)
            ),
            outcomes=tuple(
                item
                for item in self._outcomes.values()
                if self._in_scope(item, tenant_id, family_id)
            ),
            stories=tuple(
                item
                for item in self._stories.values()
                if self._in_scope(item, tenant_id, family_id)
            ),
            recommendations=tuple(
                item
                for item in self._recommendations.values()
                if self._in_scope(item, tenant_id, family_id)
            ),
            service_case_commands=tuple(
                item
                for item in self._case_commands.values()
                if self._in_scope(item, tenant_id, family_id)
            ),
            delivery_receipts=tuple(
                item
                for item in self._deliveries.values()
                if self._in_scope(item, tenant_id, family_id)
            ),
            annual_projections=tuple(
                item for item in self._annual.values() if self._in_scope(item, tenant_id, family_id)
            ),
            renewals=tuple(
                item
                for item in self._renewals.values()
                if self._in_scope(item, tenant_id, family_id)
            ),
            locale=self._locale,
        )

    def deletion_refs(self, *, tenant_id: str, family_id: str) -> tuple[str, ...]:
        """Return references for the future durable deletion cascade."""
        snapshot = self.snapshot(tenant_id=tenant_id, family_id=family_id)
        refs = [item.deletion_ref for item in snapshot.actions]
        refs.extend(item.deletion_ref for item in snapshot.reviews)
        refs.extend(item.deletion_ref for item in snapshot.outcomes)
        refs.extend(item.deletion_ref for item in snapshot.stories)
        refs.extend(
            f"media:{media_ref}" for story in snapshot.stories for media_ref in story.media_refs
        )
        refs.extend(item.deletion_ref for item in snapshot.recommendations)
        refs.extend(item.deletion_ref for item in snapshot.service_case_commands)
        refs.extend(item.deletion_ref for item in snapshot.delivery_receipts)
        refs.extend(item.deletion_ref for item in snapshot.annual_projections)
        refs.extend(item.deletion_ref for item in snapshot.renewals)
        return tuple(sorted(set(refs)))

    def _timestamp(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise JourneyValidationError("timestamp_must_be_timezone_aware")
        return value.astimezone(UTC)

    def _new_action(
        self,
        action_id: str,
        tenant_id: str,
        family_id: str,
        plan_id: str,
        task_id: str,
        day_number: int,
        status: ActionFactStatus,
        actor_id: str,
        evidence_refs: tuple[str, ...],
    ) -> ActionFact:
        return ActionFact(
            action_id=action_id,
            tenant_id=tenant_id,
            family_id=family_id,
            plan_id=plan_id,
            task_id=task_id,
            day_number=day_number,
            status=status,
            recorded_by=actor_id,
            evidence_refs=tuple(evidence_refs),
            recorded_at=self._timestamp(),
            locale=self._locale,
            deletion_ref=f"action:{tenant_id}:{family_id}:{task_id}",
        )

    @staticmethod
    def _action_matches(
        action: ActionFact,
        *,
        plan_id: str,
        day_number: int,
        status: ActionFactStatus,
        actor_id: str,
        evidence_refs: tuple[str, ...],
    ) -> bool:
        return (
            action.plan_id == plan_id
            and action.day_number == day_number
            and action.status is status
            and action.recorded_by == actor_id
            and action.evidence_refs == tuple(evidence_refs)
        )

    def _validate_scope(self, tenant_id: str, family_id: str, actor_id: str, key: str) -> None:
        if not tenant_id.strip() or not family_id.strip() or not actor_id.strip():
            raise JourneyValidationError("tenant_family_and_actor_required")
        if not key.strip() or len(key) > 128:
            raise JourneyValidationError("invalid_idempotency_key")

    @staticmethod
    def _assert_human_actor(actor_id: str) -> None:
        if actor_id.lower().startswith("ai:") or actor_id.upper() in {"AI", "SYSTEM"}:
            raise JourneyForbiddenError("human_confirmation_required")

    def _assert_live_consent(
        self,
        subject_refs: tuple[str, ...],
        purpose: ConsentPurpose,
        *,
        required_consent_id: str | None = None,
    ) -> None:
        if not subject_refs:
            raise JourneyForbiddenError("subject_binding_required")
        for subject_ref in subject_refs:
            grants = tuple(self._consent_loader(subject_ref, purpose))
            if required_consent_id is not None:
                grants = tuple(grant for grant in grants if grant.consent_id == required_consent_id)
            if not ConsentGate.check(subject_ref, purpose, grants, at=self._timestamp()):
                raise JourneyForbiddenError("live_consent_required")

    @staticmethod
    def _required(mapping: dict[str, object], key: str, code: str):
        value = mapping.get(key)
        if value is None:
            raise JourneyNotFoundError(code)
        return value

    @staticmethod
    def _in_scope(value: object, tenant_id: str, family_id: str) -> bool:
        return (
            getattr(value, "tenant_id", None) == tenant_id
            and getattr(value, "family_id", None) == family_id
        )

    @staticmethod
    def _assert_record_scope(value: object, tenant_id: str, family_id: str) -> None:
        if not GrowthOutcomeLoop._in_scope(value, tenant_id, family_id):
            raise JourneyForbiddenError("family_tenant_scope_violation")

    def _replay(
        self,
        operation: str,
        tenant_id: str,
        family_id: str,
        key: str,
        fingerprint: tuple[object, ...],
    ) -> object | None:
        stored = self._idempotency.get((tenant_id, family_id, operation, key))
        if stored is None:
            return None
        if stored[0] != fingerprint:
            raise JourneyConflictError("idempotency_conflict")
        return stored[1]

    def _remember(
        self,
        operation: str,
        tenant_id: str,
        family_id: str,
        key: str,
        fingerprint: tuple[object, ...],
        value: object,
    ) -> None:
        self._idempotency[(tenant_id, family_id, operation, key)] = (fingerprint, value)


__all__ = [
    "ActionFact",
    "ActionFactStatus",
    "AnnualReviewProjection",
    "ChallengeDecision",
    "ChallengeReview",
    "ChallengeReviewStatus",
    "FamilyStory",
    "GrowthOutcomeLoop",
    "LoopNodeContract",
    "OutcomeLoopSnapshot",
    "OutcomeRecord",
    "OutcomeStatus",
    "RecommendationDraft",
    "RecommendationStatus",
    "RenewalIntent",
    "RenewalStatus",
    "ServiceCaseCommand",
    "ServiceCaseCommandStatus",
    "ServiceDeliveryReceipt",
    "ServiceDeliveryStatus",
    "S05_S08_NODE_CONTRACTS",
    "StoryVisibility",
]
