"""Explicit synthetic Engagement runtime for dev/test contract parity.

This adapter is intentionally separate from the production composition root.
It uses deterministic provider output and generated ExperienceEvent evidence so
the complete HTTP/application path remains callable in test environments while
the response is still marked synthetic and cannot be promoted as a business
achievement.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceNode,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)
from backend.intelligence.experience.engagement import (
    EngagementDraft,
    EngagementDraftApplication,
    EngagementDraftService,
)
from backend.intelligence.experience.engagement_review import (
    AchievementCandidateSubmissionService,
    InMemoryEngagementDraftReviewStore,
)
from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    HumanTask,
    InMemoryHumanGate,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import deterministic_provider
from backend.platform.audit import AuditRecorder
from backend.platform.idempotency.keys import IdempotencyKey

SYNTHETIC_ENVIRONMENTS = frozenset({"development", "dev", "test", "local"})


class _SyntheticReviewGate:
    """Adapt the in-memory gate to the audited SQL gate port used by the service."""

    def __init__(self, gate: InMemoryHumanGate) -> None:
        self._gate = gate

    async def submit(self, proposal, *, recorder, task_id=None):  # type: ignore[no-untyped-def]
        return self._gate.submit(proposal, task_id=task_id)


@dataclass(frozen=True, slots=True)
class SyntheticEngagementRuntime:
    scope: ExperienceScope
    gateway: ModelGateway
    provider_id: str
    review_store: InMemoryEngagementDraftReviewStore
    human_gate: InMemoryHumanGate

    async def generate_draft(
        self,
        *,
        request_id: str,
        event_ids: tuple[str, ...],
        payload: Mapping[str, Any] | None = None,
    ) -> EngagementDraft:
        events = tuple(_event(scope=self.scope, event_id=event_id) for event_id in event_ids)

        class _Reader:
            async def read(self, *, scope: ExperienceScope, event_ids: tuple[str, ...]):
                if scope != self_scope:
                    return ()
                by_id = {event.event_id: event for event in events}
                return tuple(by_id[event_id] for event_id in event_ids if event_id in by_id)

        self_scope = self.scope
        application = EngagementDraftApplication(
            EngagementDraftService(self.gateway), _Reader()
        )
        draft = await application.generate_draft(
            request_id=request_id,
            provider_id=self.provider_id,
            scope=self.scope,
            actor_id=self.scope.subject_ids[0],
            authorization_ref=f"synthetic-auth:{self.scope.family_id}",
            event_ids=event_ids,
            context_snapshot_ref=f"synthetic-context:{request_id}",
            payload=payload,
        )
        stored = await self.review_store.save(draft)
        return replace(draft, draft_id=stored.draft_id)

    async def submit_achievement_candidate(
        self,
        *,
        draft_id: str,
        candidate_id: str,
        idempotency_key: str,
    ) -> HumanTask:
        stored = await self.review_store.resolve(draft_id, scope=self.scope)
        events = tuple(
            _event(scope=self.scope, event_id=event_id)
            for event_id in stored.draft.evidence_event_ids
        )

        class _Reader:
            async def read(self, *, scope: ExperienceScope, event_ids: tuple[str, ...]):
                by_id = {event.event_id: event for event in events}
                return tuple(by_id[item] for item in event_ids if item in by_id)

        return await AchievementCandidateSubmissionService(
            self.review_store,
            _Reader(),
            _SyntheticReviewGate(self.human_gate),
            AuditRecorder(),
        ).submit(
            draft_id=draft_id,
            candidate_id=candidate_id,
            scope=self.scope,
            actor_id=self.scope.subject_ids[0],
            approval_ref=f"synthetic-auth:{self.scope.family_id}",
            idempotency_key=idempotency_key,
        )

    async def decide_achievement_task(
        self,
        *,
        task_id: str,
        outcome: DecisionOutcome | str,
        reason: str | None,
        idempotency_key: str,
    ) -> HumanTask:
        task = self.human_gate.get(task_id)
        if (
            task.proposal.scope.tenant_id != self.scope.tenant_id
            or task.proposal.scope.family_id != self.scope.family_id
        ):
            raise PermissionError("engagement human task is outside the current scope")
        digest = hashlib.sha256(
            f"{self.scope.tenant_id}\x1f{idempotency_key}".encode()
        ).hexdigest()
        decided, _ = self.human_gate.decide(
            task_id,
            actor_id=f"synthetic-guardian:{self.scope.family_id}",
            actor_type=ActorType.GUARDIAN,
            outcome=outcome,
            reason=reason,
            decision_id=f"engagement-decision:{digest}",
        )
        return decided


@dataclass(frozen=True, slots=True)
class SyntheticEngagementRuntimeResolver:
    tenant_id: str
    subject_ids: tuple[str, ...]
    environment: str = "test"
    review_store: InMemoryEngagementDraftReviewStore = field(
        default_factory=InMemoryEngagementDraftReviewStore
    )
    human_gate: InMemoryHumanGate = field(default_factory=InMemoryHumanGate)

    def __post_init__(self) -> None:
        if self.environment not in SYNTHETIC_ENVIRONMENTS:
            raise ValueError("synthetic engagement runtime requires a dev/test environment")
        if not self.tenant_id.strip() or not self.subject_ids:
            raise ValueError("synthetic engagement runtime requires tenant and subjects")
        if any(not subject_id.strip() for subject_id in self.subject_ids):
            raise ValueError("synthetic engagement subjects must be non-empty")

    async def resolve(self, family_id: str) -> SyntheticEngagementRuntime:
        if not isinstance(family_id, str) or not family_id.strip():
            raise ValueError("family_id is required")
        scope = ExperienceScope(
            global_id=f"synthetic-engagement:{self.tenant_id}:{family_id}",
            tenant_id=self.tenant_id,
            region_id="CN",
            family_id=family_id,
            subject_ids=self.subject_ids,
            purpose="family-engagement-draft",
            consent_version="synthetic-consent.v1",
            consent_granted=True,
            data_class="SYNTHETIC",
            locale="zh-CN",
            content_locale="zh-CN",
            model_locale="zh-CN",
            policy_locale="zh-CN",
            deletion_ref=DeletionRef(
                deletion_id=f"synthetic-delete:{family_id}",
                retention_policy="synthetic-test",
            ),
            correlation_id=f"synthetic-correlation:{family_id}",
            causation_id=f"synthetic-causation:{family_id}",
        )
        provider_id = "synthetic-engagement"

        def response(request):
            evidence = [item["event_id"] for item in request.payload["events"]]
            candidate = {
                "candidate_id": "synthetic-achievement-1",
                "text": "记录这次模拟尝试",
                "evidence_refs": evidence,
            }
            return {
                "pacing": [{"candidate_id": "synthetic-pace-1", "text": "保持轻量节奏"}],
                "instant_feedback": [
                    {"candidate_id": "synthetic-feedback-1", "text": "看见一次尝试"}
                ],
                "growth_narrative": [
                    {"candidate_id": "synthetic-story-1", "text": "形成一个模拟线索"}
                ],
                "difficulty_adjustment": [
                    {"candidate_id": "synthetic-difficulty-1", "text": "下一步减少一个变量"}
                ],
                "achievement_candidates": [candidate],
            }

        provider = deterministic_provider(response, provider_id=provider_id)
        record = ProviderRecord(
            provider_id=provider_id,
            vendor="synthetic-test",
            model="deterministic-engagement",
            model_version="1.0.0",
            status="INTERNAL_APPROVED",
            approved_environments=("test",),
            sub_delegates=False,
            security_assessment_ref="synthetic-test",
            processing_agreement_ref="synthetic-test",
            deletion_on_termination_committed=True,
        )
        gateway = ModelGateway(
            {provider_id: provider},
            environment="test",
            registry=ProviderRegistry((record,)),
        )
        return SyntheticEngagementRuntime(
            scope,
            gateway,
            provider_id,
            self.review_store,
            self.human_gate,
        )


def _event(*, scope: ExperienceScope, event_id: str) -> ExperienceEvent:
    return ExperienceEvent(
        event_id=event_id,
        event_type=ExperienceEventType.ACTION_COMPLETED,
        node=ExperienceNode.N1,
        scope=scope,
        idempotency_key=IdempotencyKey(scope.tenant_id, event_id),
        provenance=ExperienceProvenance(
            provenance_ref=f"synthetic-provenance:{event_id}",
            source_refs=(f"synthetic-ui:{scope.family_id}",),
            kind=ProvenanceKind.SYNTHETIC_TEST,
            policy_version="synthetic-experience.v1",
        ),
        actor_id=scope.subject_ids[0],
        occurred_at=datetime.now(UTC),
    )


__all__ = ["SyntheticEngagementRuntime", "SyntheticEngagementRuntimeResolver"]
