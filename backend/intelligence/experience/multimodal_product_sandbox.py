"""A replayable text + synthetic-voice multimodal product sandbox.

This module is a scenario adapter, not another AI runtime.  It composes the
existing Model Gateway, FakeProvider, Human Gate, and in-memory AuditRecorder
for one dev/test path:

    synthetic family expression + audio ref
        -> editable structured preview
        -> Perspective/Hypothesis DraftInsight
        -> human approve/reject/edit
        -> sandbox audit and deterministic replay

The adapter never writes a canonical fact, growth profile, plan, outcome, or
external resource.  The synthetic transcript is an explicit fixture, not a
claim that ASR or a production media pipeline is available.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import ceil
from typing import Any, Literal

from backend.intelligence.human_gate import (
    ActorType,
    DecisionOutcome,
    GateScope,
    HumanGateError,
    InMemoryHumanGate,
)
from backend.intelligence.model_gateway.contracts import (
    AiProvenance,
    MediaInput,
    ModelDraft,
    PolicyContext,
    StructuredRequest,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider, deterministic_provider
from backend.platform.audit.models import AuditEvent
from backend.platform.audit.recorder import AuditRecorder

SANDBOX_SOURCE = "synthetic/sandbox"
PURPOSE = "multimodal_family_understanding_sandbox"
PROMPT_VERSION = "multimodal-family-understanding.v1"
SCHEMA_VERSION = "multimodal-family-draft-insight.v1"
DRAFT_VERSION = "multimodal-family-draft-insight.v1"
KNOWLEDGE_REF = "synthetic:knowledge:family-coordination.v1"
PLAN_PURPOSE = "multimodal_family_plan_draft_sandbox"
PLAN_PROMPT_VERSION = "multimodal-family-plan-draft.v1"
PLAN_SCHEMA_VERSION = "multimodal-family-plan-draft.v1"
EXPECTED_MODEL = "fake-deterministic"
EXPECTED_MODEL_VERSION = "1.0.0"
DEFAULT_PROVIDER_ID = "multimodal-sandbox-fake"
MAX_INPUT_CHARS = 4_000
MAX_OUTPUT_CHARS = 2_000
MAX_HYPOTHESES = 5
DEFAULT_REVIEW_TTL = timedelta(minutes=15)

_EMAIL_RE = re.compile(r"(?i)\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_CN_ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all previous",
    "reveal the system prompt",
    "忽略之前的指令",
    "忽略系统提示",
    "泄露系统提示",
)
_DRAFT_KEYS = frozenset({"perspective", "hypotheses", "support_card", "limitations"})
_PERSPECTIVE_KEYS = frozenset({"text", "evidence_refs"})
_HYPOTHESIS_KEYS = frozenset({"text", "uncertainty", "evidence_refs"})
_DENIED_TOOLS = frozenset(
    {
        "FACT_WRITE",
        "GROWTH_PROFILE_WRITE",
        "PLAN_WRITE",
        "OUTCOME_WRITE",
        "DIAGNOSE",
        "DISPATCH",
        "REFUND",
        "SETTLEMENT",
        "MEDIA_MODERATION",
        "UPSELL",
    }
)


class SandboxPolicyError(ValueError):
    """A policy failure that never includes family payload data."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EDIT = "EDIT"


@dataclass(frozen=True, slots=True)
class SandboxContextPolicy:
    """Explicit context/tool policy for this one experiment."""

    purpose: str = PURPOSE
    consent_version: str = "synthetic:consent:multimodal.v1"
    allowed_tools: tuple[str, ...] = ()
    denied_tools: frozenset[str] = _DENIED_TOOLS
    may_mutate_business_state: Literal[False] = False

    def __post_init__(self) -> None:
        if self.purpose != PURPOSE or not self.consent_version.startswith("synthetic:"):
            raise SandboxPolicyError("CONTEXT_POLICY_INVALID")
        if self.allowed_tools or self.may_mutate_business_state is not False:
            raise SandboxPolicyError("TOOL_POLICY_NOT_FAIL_CLOSED")
        if not _DENIED_TOOLS.issubset(self.denied_tools):
            raise SandboxPolicyError("TOOL_DENY_LIST_INCOMPLETE")


@dataclass(frozen=True, slots=True)
class SyntheticFamilyInput:
    """Text plus a synthetic audio/transcript reference; no media bytes."""

    input_id: str
    tenant_id: str
    family_id: str
    guardian_id: str
    text: str
    audio_ref: str
    audio_sha256: str
    transcript_ref: str
    image_ref: str | None = None
    image_sha256: str | None = None
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True
    consent_granted: bool = True
    consent_ref: str = "synthetic:consent:multimodal.v1"

    def __post_init__(self) -> None:
        required = (
            self.input_id,
            self.tenant_id,
            self.family_id,
            self.guardian_id,
            self.text,
            self.audio_ref,
            self.audio_sha256,
            self.transcript_ref,
            self.consent_ref,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required):
            raise SandboxPolicyError("FIXTURE_REQUIRED_FIELD_MISSING")
        if self.source != SANDBOX_SOURCE or self.fixture_only is not True:
            raise SandboxPolicyError("SYNTHETIC_FIXTURE_REQUIRED")
        if self.consent_granted is not True or not self.consent_ref.startswith("synthetic:"):
            raise SandboxPolicyError("SYNTHETIC_CONSENT_REQUIRED")
        if (self.image_ref is None) != (self.image_sha256 is None):
            raise SandboxPolicyError("IMAGE_FIXTURE_INCOMPLETE")
        for value in (
            self.input_id,
            self.tenant_id,
            self.family_id,
            self.guardian_id,
            self.audio_ref,
            self.audio_sha256,
            self.transcript_ref,
        ):
            if not value.startswith("synthetic:"):
                raise SandboxPolicyError("NON_SYNTHETIC_INPUT_REJECTED")
        for value in (self.image_ref, self.image_sha256):
            if value is not None and not value.startswith("synthetic:"):
                raise SandboxPolicyError("NON_SYNTHETIC_INPUT_REJECTED")

    @property
    def source_refs(self) -> tuple[str, ...]:
        refs = [self.audio_ref, self.transcript_ref]
        if self.image_ref is not None:
            refs.append(self.image_ref)
        return tuple(refs)


@dataclass(frozen=True, slots=True)
class StructuredPreview:
    """A family-editable, non-canonical preview before model generation."""

    input_id: str
    tenant_id: str
    family_id: str
    guardian_id: str
    normalized_text: str
    source_refs: tuple[str, ...]
    media_sha256: str
    image_ref: str | None
    image_sha256: str | None
    preview_hash: str
    source: str
    fixture_only: bool
    human_edited: bool = False


@dataclass(frozen=True, slots=True)
class HypothesisDraft:
    text: str
    uncertainty: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DraftInsight:
    """An explainable, immutable DraftInsight; never a canonical fact."""

    run_id: str
    input_id: str
    tenant_id: str
    family_id: str
    guardian_id: str
    preview_hash: str
    source_refs: tuple[str, ...]
    perspective: str
    perspective_evidence_refs: tuple[str, ...]
    hypotheses: tuple[HypothesisDraft, ...]
    support_card: str
    limitations: tuple[str, ...]
    provenance: AiProvenance
    draft_hash: str
    draft_version: str
    human_gate_task_id: str
    scope: GateScope
    context_policy: SandboxContextPolicy
    created_at: datetime
    expires_at: datetime
    knowledge_refs: tuple[str, ...] = ()

    @property
    def status(self) -> Literal["DRAFT"]:
        return "DRAFT"

    @property
    def may_mutate_business_state(self) -> Literal[False]:
        return False

    @property
    def requires_human_confirmation(self) -> Literal[True]:
        return True


@dataclass(frozen=True, slots=True)
class PlanDraft:
    """A non-canonical plan proposal produced only after human approval."""

    run_id: str
    source_draft_hash: str
    tenant_id: str
    family_id: str
    title: str
    steps: tuple[str, ...]
    limitations: tuple[str, ...]
    knowledge_refs: tuple[str, ...]
    provenance: AiProvenance
    draft_hash: str

    @property
    def status(self) -> Literal["DRAFT"]:
        return "DRAFT"

    @property
    def may_mutate_business_state(self) -> Literal[False]:
        return False


@dataclass(frozen=True, slots=True)
class ReviewResult:
    run_id: str
    task_id: str
    decision_id: str
    decision: ReviewDecision
    human_gate_outcome: DecisionOutcome
    actor_id: str
    tenant_id: str
    family_id: str
    draft_hash: str
    reason: str | None
    edited_perspective: str | None
    audit_event: AuditEvent
    action_request_executed: Literal[False] = False


def _assert_safe_text(value: str, *, code: str) -> None:
    if _EMAIL_RE.search(value) or _PHONE_RE.search(value) or _CN_ID_RE.search(value):
        raise SandboxPolicyError("PII_DETECTED")
    lowered = value.casefold()
    if any(marker in lowered for marker in _INJECTION_MARKERS):
        raise SandboxPolicyError(code)


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_synthetic_run(run_id: str) -> None:
    if not isinstance(run_id, str) or not run_id.startswith("synthetic-run:"):
        raise SandboxPolicyError("SYNTHETIC_RUN_ID_REQUIRED")


def _default_response(request: StructuredRequest) -> dict[str, Any]:
    """Deterministic provider output; it never echoes family text."""

    refs = list(request.input_refs)
    if request.use_case == PLAN_PURPOSE:
        return {
            "title": "晚间学习启动协作草案",
            "steps": ["成人确认一个五分钟启动时段。", "家庭执行后记录是否更容易协作。"],
            "limitations": ["这是待家庭确认的计划草案，不是 canonical Plan。"],
        }
    return {
        "perspective": {
            "text": "待家庭确认的视角：这段表达可能与晚间学习协作有关。",
            "evidence_refs": refs,
        },
        "hypotheses": [
            {
                "text": "一个待验证的解释是，家庭可能需要把学习启动拆成更小的协作步骤。",
                "uncertainty": "仅依据合成输入，未验证家庭事实。",
                "evidence_refs": refs,
            }
        ],
        "support_card": "可供成人修改或拒绝的理解草案，不是诊断、事实或行动指令。",
        "limitations": [
            "输入来自 synthetic fixture；未连接真实 ASR、知识库或家庭记录。",
            "Draft 必须经成人确认，不能直接写入 canonical state。",
        ],
    }


def _draft_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "perspective": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "evidence_refs"],
            },
            "hypotheses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "uncertainty": {"type": "string"},
                        "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["text", "uncertainty", "evidence_refs"],
                },
            },
            "support_card": {"type": "string"},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["perspective", "hypotheses", "support_card", "limitations"],
    }


def _plan_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "steps", "limitations"],
    }


class MultimodalProductSandbox:
    """One text + synthetic-voice DraftInsight experiment."""

    def __init__(
        self,
        provider: FakeProvider | None = None,
        *,
        max_cost_microusd: int = 100,
        review_ttl: timedelta = DEFAULT_REVIEW_TTL,
    ) -> None:
        if max_cost_microusd < 0 or review_ttl <= timedelta(0):
            raise SandboxPolicyError("SANDBOX_LIMIT_INVALID")
        resolved_provider = provider or deterministic_provider(
            _default_response, provider_id=DEFAULT_PROVIDER_ID
        )
        if not isinstance(resolved_provider, FakeProvider):
            raise SandboxPolicyError("FAKE_PROVIDER_REQUIRED")
        if not resolved_provider.provider_id:
            raise SandboxPolicyError("FAKE_PROVIDER_ID_REQUIRED")
        self._provider = resolved_provider
        self._max_cost_microusd = max_cost_microusd
        self._review_ttl = review_ttl
        self._policy = SandboxContextPolicy()
        self._gateway = ModelGateway(
            {resolved_provider.provider_id: resolved_provider},
            environment="sandbox",
            registry=ProviderRegistry(
                (
                    ProviderRecord(
                        provider_id=resolved_provider.provider_id,
                        vendor="aifamily-test",
                        model=EXPECTED_MODEL,
                        model_version=EXPECTED_MODEL_VERSION,
                        status="INTERNAL_APPROVED",
                        approved_environments=("sandbox",),
                        sub_delegates=False,
                        security_assessment_ref="synthetic-sandbox-only",
                        processing_agreement_ref="synthetic-sandbox-only",
                        deletion_on_termination_committed=True,
                        processing_region="local-sandbox",
                        timeout_seconds=0.05,
                    ),
                )
            ),
            default_timeout_seconds=0.05,
        )
        self._gate = InMemoryHumanGate()
        self._audit = AuditRecorder()
        self._previews: dict[str, StructuredPreview] = {}
        self._drafts: dict[str, DraftInsight] = {}
        self._plan_drafts: dict[str, PlanDraft] = {}
        self._gateway_drafts: dict[str, ModelDraft] = {}
        self._tasks: dict[str, Any] = {}
        self._reviews: dict[str, ReviewResult] = {}
        self._run_fingerprints: dict[str, str] = {}
        self._review_fingerprints: dict[str, str] = {}

    @property
    def provider(self) -> FakeProvider:
        return self._provider

    @property
    def context_policy(self) -> SandboxContextPolicy:
        return self._policy

    @property
    def audit_events(self) -> tuple[AuditEvent, ...]:
        return self._audit.all_events()

    def build_preview(self, input_data: SyntheticFamilyInput) -> StructuredPreview:
        """Normalize an explicitly synthetic input before any model call."""

        if not isinstance(input_data, SyntheticFamilyInput):
            raise SandboxPolicyError("SYNTHETIC_FIXTURE_REQUIRED")
        normalized = " ".join(input_data.text.split())
        try:
            if len(normalized) > MAX_INPUT_CHARS:
                raise SandboxPolicyError("INPUT_CAPACITY_EXCEEDED")
            _assert_safe_text(normalized, code="UNSAFE_INPUT")
        except SandboxPolicyError as error:
            self._record_preview_failure(input_data, error)
            raise
        preview_hash = _canonical_hash(
            {
                "input_id": input_data.input_id,
                "tenant_id": input_data.tenant_id,
                "family_id": input_data.family_id,
                "guardian_id": input_data.guardian_id,
                "normalized_text": normalized,
                "source_refs": input_data.source_refs,
                "media_sha256": input_data.audio_sha256,
                "image_sha256": input_data.image_sha256,
            }
        )
        preview = StructuredPreview(
            input_id=input_data.input_id,
            tenant_id=input_data.tenant_id,
            family_id=input_data.family_id,
            guardian_id=input_data.guardian_id,
            normalized_text=normalized,
            source_refs=input_data.source_refs,
            media_sha256=input_data.audio_sha256,
            image_ref=input_data.image_ref,
            image_sha256=input_data.image_sha256,
            preview_hash=preview_hash,
            source=input_data.source,
            fixture_only=input_data.fixture_only,
        )
        self._previews[preview_hash] = preview
        return preview

    def edit_preview(
        self,
        preview: StructuredPreview,
        *,
        tenant_id: str,
        family_id: str,
        guardian_id: str,
        addition: str,
    ) -> StructuredPreview:
        """Apply an adult edit to the preview, still without canonical writes."""

        self._assert_preview_scope(preview, tenant_id, family_id, guardian_id)
        if not isinstance(addition, str) or not addition.strip():
            raise SandboxPolicyError("PREVIEW_EDIT_REQUIRED")
        if len(addition) > MAX_INPUT_CHARS:
            raise SandboxPolicyError("INPUT_CAPACITY_EXCEEDED")
        _assert_safe_text(addition, code="UNSAFE_PREVIEW_EDIT")
        normalized = " ".join(f"{preview.normalized_text} {addition}".split())
        if len(normalized) > MAX_INPUT_CHARS:
            raise SandboxPolicyError("INPUT_CAPACITY_EXCEEDED")
        edited = StructuredPreview(
            input_id=preview.input_id,
            tenant_id=preview.tenant_id,
            family_id=preview.family_id,
            guardian_id=preview.guardian_id,
            normalized_text=normalized,
            source_refs=preview.source_refs,
            preview_hash=_canonical_hash(
                {
                    "input_id": preview.input_id,
                    "tenant_id": preview.tenant_id,
                    "family_id": preview.family_id,
                    "guardian_id": preview.guardian_id,
                    "normalized_text": normalized,
                    "source_refs": preview.source_refs,
                    "media_sha256": preview.media_sha256,
                    "image_sha256": preview.image_sha256,
                }
            ),
            media_sha256=preview.media_sha256,
            image_ref=preview.image_ref,
            image_sha256=preview.image_sha256,
            source=SANDBOX_SOURCE,
            fixture_only=True,
            human_edited=True,
        )
        self._previews[edited.preview_hash] = edited
        return edited

    async def generate_draft(
        self,
        preview: StructuredPreview,
        *,
        run_id: str,
        now: datetime | None = None,
    ) -> DraftInsight:
        """Generate a DraftInsight and open its existing Human Gate task."""

        _require_synthetic_run(run_id)
        timestamp = _aware_now(now)
        if self._previews.get(preview.preview_hash) is not preview:
            raise SandboxPolicyError("PREVIEW_NOT_OWNED_BY_SANDBOX")
        fingerprint = _canonical_hash(
            {
                "run_id": run_id,
                "preview_hash": preview.preview_hash,
                "source_refs": preview.source_refs,
                "human_edited": preview.human_edited,
            }
        )
        existing = self._drafts.get(run_id)
        if existing is not None:
            if self._run_fingerprints[run_id] != fingerprint:
                raise SandboxPolicyError("REPLAY_MISMATCH")
            return existing

        estimated_tokens = max(1, ceil(len(preview.normalized_text) / 4))
        estimated_cost_microusd = max(1, ceil(estimated_tokens / 1_000))
        if estimated_cost_microusd > self._max_cost_microusd:
            error = SandboxPolicyError("COST_LIMIT_EXCEEDED")
            self._record_generation_failure(preview, run_id, timestamp, error)
            raise error

        context_ref = (
            f"synthetic-context:{preview.tenant_id}:{preview.family_id}:{preview.preview_hash}"
        )
        request = StructuredRequest(
            use_case=PURPOSE,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            data_class="SYNTHETIC",
            payload={
                "source": SANDBOX_SOURCE,
                "fixture_only": True,
                "input_id": preview.input_id,
                "normalized_text": preview.normalized_text,
                "source_refs": list(preview.source_refs),
                "knowledge_refs": [KNOWLEDGE_REF],
                "context_policy": {
                    "purpose": self._policy.purpose,
                    "consent_version": self._policy.consent_version,
                    "allowed_tools": list(self._policy.allowed_tools),
                    "denied_tools": sorted(self._policy.denied_tools),
                    "may_mutate_business_state": False,
                },
            },
            output_schema=_draft_schema(),
            context_snapshot_ref=context_ref,
            input_refs=preview.source_refs,
            media_inputs=self._media_inputs(preview),
            request_id=run_id,
            policy_context=PolicyContext(),
        )
        try:
            gateway_draft = await self._gateway.generate_structured(
                request, provider_id=self._provider.provider_id
            )
            self._assert_provenance(
                gateway_draft.provenance,
                request,
                provider_id=self._provider.provider_id,
            )
            perspective, hypotheses, support_card, limitations = self._parse_draft_output(
                gateway_draft.output,
                source_refs=preview.source_refs,
            )
            scope = GateScope(
                tenant_id=preview.tenant_id,
                family_id=preview.family_id,
                subject_ids=(preview.guardian_id,),
                purpose=PURPOSE,
                consent_version=self._policy.consent_version,
                correlation_id=f"synthetic-correlation:{run_id}",
            )
            draft_hash = _canonical_hash(
                {
                    "run_id": run_id,
                    "input_id": preview.input_id,
                    "preview_hash": preview.preview_hash,
                    "source_refs": preview.source_refs,
                    "perspective": perspective,
                    "hypotheses": [
                        {
                            "text": item.text,
                            "uncertainty": item.uncertainty,
                            "evidence_refs": item.evidence_refs,
                        }
                        for item in hypotheses
                    ],
                    "support_card": support_card,
                    "limitations": limitations,
                    "provenance": _stable_provenance(gateway_draft.provenance),
                    "knowledge_refs": (KNOWLEDGE_REF,),
                }
            )
            task = self._gate.submit_model_draft(
                gateway_draft,
                draft_id=f"draft:{run_id}",
                proposal_id=f"proposal:{run_id}",
                action_name="REVIEW_MULTIMODAL_DRAFT_INSIGHT",
                action_arguments={
                    "draft_hash": draft_hash,
                    "draft_version": DRAFT_VERSION,
                    "source_refs": preview.source_refs,
                    "human_confirmation_required": True,
                    "may_mutate_business_state": False,
                },
                scope=scope,
                allowed_actor_types=(ActorType.GUARDIAN,),
                risk_level="LOW_SANDBOX",
                provenance_ref=f"model-draft:{run_id}",
                now=timestamp,
                ttl=self._review_ttl,
            )
            draft = DraftInsight(
                run_id=run_id,
                input_id=preview.input_id,
                tenant_id=preview.tenant_id,
                family_id=preview.family_id,
                guardian_id=preview.guardian_id,
                preview_hash=preview.preview_hash,
                source_refs=preview.source_refs,
                perspective=perspective["text"],
                perspective_evidence_refs=tuple(perspective["evidence_refs"]),
                hypotheses=tuple(hypotheses),
                support_card=support_card,
                limitations=tuple(limitations),
                provenance=gateway_draft.provenance,
                draft_hash=draft_hash,
                draft_version=DRAFT_VERSION,
                human_gate_task_id=task.task_id,
                scope=scope,
                context_policy=self._policy,
                created_at=timestamp,
                expires_at=timestamp + self._review_ttl,
                knowledge_refs=(KNOWLEDGE_REF,),
            )
            self._record_event(
                tenant_id=draft.tenant_id,
                family_id=draft.family_id,
                run_id=run_id,
                correlation_id=scope.correlation_id,
                action="sandbox.multimodal.draft_created",
                reason="Synthetic DraftInsight created; Human Gate is required.",
                timestamp=timestamp,
                metadata=self._metadata(
                    draft=draft,
                    decision="DRAFT_CREATED",
                    reviewer=None,
                    task_id=task.task_id,
                    decision_id=None,
                    expiry=task.proposal.expires_at,
                    failure_stop=False,
                    timestamp=timestamp,
                ),
            )
        except Exception as exc:
            self._record_generation_failure(preview, run_id, timestamp, exc)
            raise

        self._run_fingerprints[run_id] = fingerprint
        self._drafts[run_id] = draft
        self._gateway_drafts[run_id] = gateway_draft
        self._tasks[run_id] = task
        return draft

    async def generate_plan_draft(
        self,
        draft: DraftInsight,
        review: ReviewResult,
        *,
        now: datetime | None = None,
    ) -> PlanDraft:
        """Create a non-canonical plan draft only after human acceptance."""

        timestamp = _aware_now(now)
        if self._drafts.get(draft.run_id) is not draft or review.run_id != draft.run_id:
            raise SandboxPolicyError("DRAFT_REVIEW_SCOPE_MISMATCH")
        if review.draft_hash != draft.draft_hash:
            raise SandboxPolicyError("DRAFT_REVIEW_HASH_MISMATCH")
        if review.human_gate_outcome is not DecisionOutcome.ACCEPT:
            raise SandboxPolicyError("PLAN_REQUIRES_HUMAN_APPROVAL")
        existing = self._plan_drafts.get(draft.run_id)
        if existing is not None:
            return existing

        context_ref = (
            f"synthetic-plan-context:{draft.tenant_id}:{draft.family_id}:{draft.draft_hash}"
        )
        request = StructuredRequest(
            use_case=PLAN_PURPOSE,
            prompt_version=PLAN_PROMPT_VERSION,
            schema_version=PLAN_SCHEMA_VERSION,
            data_class="SYNTHETIC",
            payload={
                "source": SANDBOX_SOURCE,
                "fixture_only": True,
                "source_draft_hash": draft.draft_hash,
                "knowledge_refs": [KNOWLEDGE_REF],
                "source_refs": list(draft.source_refs),
                "context_policy": {
                    "purpose": self._policy.purpose,
                    "consent_version": self._policy.consent_version,
                    "allowed_tools": [],
                    "denied_tools": sorted(self._policy.denied_tools),
                    "may_mutate_business_state": False,
                },
            },
            output_schema=_plan_schema(),
            context_snapshot_ref=context_ref,
            input_refs=draft.source_refs,
            request_id=f"{review.task_id}:plan",
            policy_context=PolicyContext(),
        )
        try:
            gateway_draft = await self._gateway.generate_structured(
                request, provider_id=self._provider.provider_id
            )
            if (
                gateway_draft.provenance.provider_id != self._provider.provider_id
                or gateway_draft.provenance.model != EXPECTED_MODEL
                or gateway_draft.provenance.model_version != EXPECTED_MODEL_VERSION
                or gateway_draft.provenance.prompt_version != PLAN_PROMPT_VERSION
                or gateway_draft.provenance.schema_version != PLAN_SCHEMA_VERSION
                or gateway_draft.provenance.context_snapshot_ref != context_ref
                or gateway_draft.provenance.use_case != PLAN_PURPOSE
                or gateway_draft.provenance.data_class != "SYNTHETIC"
            ):
                raise SandboxPolicyError("PLAN_PROVENANCE_MISMATCH")
            title, steps, limitations = self._parse_plan_output(gateway_draft.output)
            plan_hash = _canonical_hash(
                {
                    "source_draft_hash": draft.draft_hash,
                    "tenant_id": draft.tenant_id,
                    "family_id": draft.family_id,
                    "title": title,
                    "steps": steps,
                    "limitations": limitations,
                    "provenance": _stable_provenance(gateway_draft.provenance),
                }
            )
            plan = PlanDraft(
                run_id=draft.run_id,
                source_draft_hash=draft.draft_hash,
                tenant_id=draft.tenant_id,
                family_id=draft.family_id,
                title=title,
                steps=steps,
                limitations=limitations,
                knowledge_refs=(KNOWLEDGE_REF,),
                provenance=gateway_draft.provenance,
                draft_hash=plan_hash,
            )
            self._record_event(
                tenant_id=draft.tenant_id,
                family_id=draft.family_id,
                run_id=draft.run_id,
                correlation_id=draft.scope.correlation_id,
                action="sandbox.multimodal.plan_draft_created",
                reason=(
                    "Synthetic plan draft created after human approval; "
                    "canonical Plan is unchanged."
                ),
                timestamp=timestamp,
                metadata={
                    "source": SANDBOX_SOURCE,
                    "fixture_only": True,
                    "tenant_id": draft.tenant_id,
                    "family_id": draft.family_id,
                    "source_draft_hash": draft.draft_hash,
                    "draft_hash": plan_hash,
                    "draft_version": PLAN_SCHEMA_VERSION,
                    "knowledge_refs": (KNOWLEDGE_REF,),
                    "decision": "DRAFT_CREATED",
                    "failure_stop": False,
                    "failure_requires_manual_takeover": False,
                    "may_mutate_business_state": False,
                    "sandbox_only": True,
                },
            )
        except Exception as exc:
            self._record_event(
                tenant_id=draft.tenant_id,
                family_id=draft.family_id,
                run_id=draft.run_id,
                correlation_id=draft.scope.correlation_id,
                action="sandbox.multimodal.plan_generation_failed",
                reason="Synthetic plan generation stopped; manual takeover is required.",
                timestamp=timestamp,
                metadata={
                    "source": SANDBOX_SOURCE,
                    "fixture_only": True,
                    "tenant_id": draft.tenant_id,
                    "family_id": draft.family_id,
                    "source_draft_hash": draft.draft_hash,
                    "draft_hash": None,
                    "draft_version": PLAN_SCHEMA_VERSION,
                    "knowledge_refs": (KNOWLEDGE_REF,),
                    "decision": "STOPPED",
                    "failure_stop": True,
                    "failure_kind": _failure_code(exc),
                    "failure_requires_manual_takeover": True,
                    "may_mutate_business_state": False,
                    "sandbox_only": True,
                },
            )
            raise

        self._plan_drafts[draft.run_id] = plan
        return plan

    async def review_draft(
        self,
        draft: DraftInsight,
        *,
        tenant_id: str,
        family_id: str,
        guardian_id: str,
        decision: ReviewDecision | str,
        reason: str | None = None,
        edited_perspective: str | None = None,
        now: datetime | None = None,
    ) -> ReviewResult:
        """Accept/reject/edit through Human Gate; never execute the action request."""

        timestamp = _aware_now(now)
        if self._drafts.get(draft.run_id) is not draft:
            raise SandboxPolicyError("DRAFT_NOT_OWNED_BY_SANDBOX")
        try:
            resolved = ReviewDecision(decision)
        except ValueError as exc:
            self._record_review_failure(draft, timestamp, "INVALID_REVIEW_DECISION", guardian_id)
            raise SandboxPolicyError("INVALID_REVIEW_DECISION") from exc
        if tenant_id != draft.tenant_id:
            self._record_review_failure(draft, timestamp, "CROSS_TENANT_SCOPE", guardian_id)
            raise SandboxPolicyError("CROSS_TENANT_SCOPE")
        if family_id != draft.family_id:
            self._record_review_failure(draft, timestamp, "CROSS_FAMILY_SCOPE", guardian_id)
            raise SandboxPolicyError("CROSS_FAMILY_SCOPE")
        if guardian_id != draft.guardian_id:
            self._record_review_failure(draft, timestamp, "REVIEWER_SCOPE_MISMATCH", guardian_id)
            raise SandboxPolicyError("REVIEWER_SCOPE_MISMATCH")
        if resolved is ReviewDecision.EDIT:
            if not isinstance(edited_perspective, str) or not edited_perspective.strip():
                self._record_review_failure(draft, timestamp, "EDIT_CONTENT_REQUIRED", guardian_id)
                raise SandboxPolicyError("EDIT_CONTENT_REQUIRED")
            if not reason or not reason.strip():
                self._record_review_failure(draft, timestamp, "EDIT_REASON_REQUIRED", guardian_id)
                raise SandboxPolicyError("EDIT_REASON_REQUIRED")
            if len(edited_perspective) > MAX_OUTPUT_CHARS:
                self._record_review_failure(draft, timestamp, "EDIT_CAPACITY_EXCEEDED", guardian_id)
                raise SandboxPolicyError("EDIT_CAPACITY_EXCEEDED")
            _assert_safe_text(edited_perspective, code="UNSAFE_EDIT")
            _assert_safe_text(reason, code="UNSAFE_REVIEW_REASON")
        elif resolved is ReviewDecision.REJECT:
            if not reason or not reason.strip():
                self._record_review_failure(draft, timestamp, "REJECT_REASON_REQUIRED", guardian_id)
                raise SandboxPolicyError("REJECT_REASON_REQUIRED")
            _assert_safe_text(reason, code="UNSAFE_REVIEW_REASON")
        elif reason:
            _assert_safe_text(reason, code="UNSAFE_REVIEW_REASON")

        task = self._tasks[draft.run_id]
        fingerprint = _canonical_hash(
            {
                "decision": resolved.value,
                "guardian_id": guardian_id,
                "reason": reason or "",
                "edited_perspective": edited_perspective or "",
            }
        )
        existing = self._reviews.get(task.task_id)
        if existing is not None:
            if self._review_fingerprints[task.task_id] != fingerprint:
                raise SandboxPolicyError("REVIEW_REPLAY_MISMATCH")
            return existing

        outcome = (
            DecisionOutcome.REJECT if resolved is ReviewDecision.REJECT else DecisionOutcome.ACCEPT
        )
        try:
            decided, _named_action_request = self._gate.decide(
                task.task_id,
                actor_id=guardian_id,
                actor_type=ActorType.GUARDIAN,
                outcome=outcome,
                reason=reason,
                decision_id=f"decision:{task.task_id}",
                now=timestamp,
            )
            if decided.decision is None:
                raise SandboxPolicyError("HUMAN_GATE_DECISION_MISSING")
            event = self._record_event(
                tenant_id=draft.tenant_id,
                family_id=draft.family_id,
                run_id=draft.run_id,
                correlation_id=draft.scope.correlation_id,
                action="sandbox.multimodal.draft_reviewed",
                reason=reason or "Synthetic guardian approved the DraftInsight.",
                timestamp=timestamp,
                metadata=self._metadata(
                    draft=draft,
                    decision=resolved.value,
                    reviewer=guardian_id,
                    task_id=task.task_id,
                    decision_id=decided.decision.decision_id,
                    expiry=task.proposal.expires_at,
                    failure_stop=False,
                    timestamp=timestamp,
                    extra={
                        "knowledge_refs": draft.knowledge_refs,
                        "human_gate_outcome": outcome.value,
                        "edited_perspective_sha256": (
                            hashlib.sha256(edited_perspective.encode("utf-8")).hexdigest()
                            if edited_perspective is not None
                            else None
                        ),
                    },
                ),
            )
        except Exception as exc:
            self._record_review_failure(draft, timestamp, _failure_code(exc), guardian_id)
            raise

        result = ReviewResult(
            run_id=draft.run_id,
            task_id=task.task_id,
            decision_id=decided.decision.decision_id,
            decision=resolved,
            human_gate_outcome=outcome,
            actor_id=guardian_id,
            tenant_id=draft.tenant_id,
            family_id=draft.family_id,
            draft_hash=draft.draft_hash,
            reason=reason,
            edited_perspective=edited_perspective if resolved is ReviewDecision.EDIT else None,
            audit_event=event,
        )
        self._reviews[task.task_id] = result
        self._review_fingerprints[task.task_id] = fingerprint
        return result

    @staticmethod
    def _media_inputs(preview: StructuredPreview) -> tuple[MediaInput, ...]:
        media = [
            MediaInput(
                media_type="AUDIO",
                uri=preview.source_refs[0],
                mime_type="audio/mpeg",
                sha256=preview.media_sha256,
            )
        ]
        if preview.image_ref is not None and preview.image_sha256 is not None:
            media.append(
                MediaInput(
                    media_type="IMAGE",
                    uri=preview.image_ref,
                    mime_type="image/png",
                    sha256=preview.image_sha256,
                )
            )
        return tuple(media)

    @staticmethod
    def _assert_preview_scope(
        preview: StructuredPreview,
        tenant_id: str,
        family_id: str,
        guardian_id: str,
    ) -> None:
        if tenant_id != preview.tenant_id:
            raise SandboxPolicyError("CROSS_TENANT_SCOPE")
        if family_id != preview.family_id:
            raise SandboxPolicyError("CROSS_FAMILY_SCOPE")
        if guardian_id != preview.guardian_id:
            raise SandboxPolicyError("REVIEWER_SCOPE_MISMATCH")

    @staticmethod
    def _assert_provenance(
        provenance: AiProvenance,
        request: StructuredRequest,
        *,
        provider_id: str,
    ) -> None:
        if provenance.provider_id != provider_id:
            raise SandboxPolicyError("PROVENANCE_PROVIDER_MISMATCH")
        if provenance.model != EXPECTED_MODEL or provenance.model_version != EXPECTED_MODEL_VERSION:
            raise SandboxPolicyError("MODEL_DRIFT")
        if (
            provenance.prompt_version != PROMPT_VERSION
            or provenance.schema_version != SCHEMA_VERSION
            or provenance.context_snapshot_ref != request.context_snapshot_ref
            or provenance.use_case != PURPOSE
            or provenance.data_class != "SYNTHETIC"
        ):
            raise SandboxPolicyError("PROVENANCE_MISMATCH")

    @staticmethod
    def _parse_plan_output(output: dict[str, Any]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        expected = {"title", "steps", "limitations"}
        if set(output) != expected:
            raise SandboxPolicyError("PLAN_SCHEMA_DRIFT")
        title = output.get("title")
        steps = output.get("steps")
        limitations = output.get("limitations")
        if (
            not isinstance(title, str)
            or not title.strip()
            or not isinstance(steps, list)
            or not steps
            or any(not isinstance(step, str) or not step.strip() for step in steps)
            or not isinstance(limitations, list)
            or any(not isinstance(item, str) or not item.strip() for item in limitations)
        ):
            raise SandboxPolicyError("PLAN_CONTRACT_INVALID")
        for value in (title, *steps, *limitations):
            _assert_safe_text(value, code="UNSAFE_PLAN_OUTPUT")
        return title, tuple(steps), tuple(limitations)

    @staticmethod
    def _parse_draft_output(
        output: dict[str, Any], *, source_refs: tuple[str, ...]
    ) -> tuple[dict[str, Any], tuple[HypothesisDraft, ...], str, tuple[str, ...]]:
        if set(output) != _DRAFT_KEYS:
            raise SandboxPolicyError("OUTPUT_SCHEMA_DRIFT_OR_TOOL_CALL")
        perspective = output.get("perspective")
        hypotheses = output.get("hypotheses")
        support_card = output.get("support_card")
        limitations = output.get("limitations")
        if (
            not isinstance(perspective, dict)
            or set(perspective) != _PERSPECTIVE_KEYS
            or not isinstance(perspective.get("text"), str)
            or not perspective["text"].strip()
            or not isinstance(perspective.get("evidence_refs"), list)
            or not perspective["evidence_refs"]
        ):
            raise SandboxPolicyError("PERSPECTIVE_CONTRACT_INVALID")
        _assert_safe_text(perspective["text"], code="UNSAFE_MODEL_OUTPUT")
        _assert_evidence_refs(perspective["evidence_refs"], source_refs)
        if not isinstance(hypotheses, list) or not hypotheses or len(hypotheses) > MAX_HYPOTHESES:
            raise SandboxPolicyError("HYPOTHESIS_CONTRACT_INVALID")
        parsed: list[HypothesisDraft] = []
        for hypothesis in hypotheses:
            if (
                not isinstance(hypothesis, dict)
                or set(hypothesis) != _HYPOTHESIS_KEYS
                or not isinstance(hypothesis.get("text"), str)
                or not hypothesis["text"].strip()
                or not isinstance(hypothesis.get("uncertainty"), str)
                or not hypothesis["uncertainty"].strip()
                or not isinstance(hypothesis.get("evidence_refs"), list)
                or not hypothesis["evidence_refs"]
            ):
                raise SandboxPolicyError("HYPOTHESIS_CONTRACT_INVALID")
            _assert_safe_text(hypothesis["text"], code="UNSAFE_MODEL_OUTPUT")
            _assert_safe_text(hypothesis["uncertainty"], code="UNSAFE_MODEL_OUTPUT")
            _assert_evidence_refs(hypothesis["evidence_refs"], source_refs)
            parsed.append(
                HypothesisDraft(
                    text=hypothesis["text"],
                    uncertainty=hypothesis["uncertainty"],
                    evidence_refs=tuple(hypothesis["evidence_refs"]),
                )
            )
        if not isinstance(support_card, str) or not support_card.strip():
            raise SandboxPolicyError("SUPPORT_CARD_REQUIRED")
        _assert_safe_text(support_card, code="UNSAFE_MODEL_OUTPUT")
        if len(support_card) > MAX_OUTPUT_CHARS:
            raise SandboxPolicyError("OUTPUT_CAPACITY_EXCEEDED")
        if not isinstance(limitations, list) or any(
            not isinstance(value, str) or not value.strip() for value in limitations
        ):
            raise SandboxPolicyError("LIMITATIONS_CONTRACT_INVALID")
        for value in limitations:
            _assert_safe_text(value, code="UNSAFE_MODEL_OUTPUT")
        return perspective, tuple(parsed), support_card, tuple(limitations)

    def _metadata(
        self,
        *,
        draft: DraftInsight,
        decision: str,
        reviewer: str | None,
        task_id: str | None,
        decision_id: str | None,
        expiry: datetime | None,
        failure_stop: bool,
        timestamp: datetime,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "source": SANDBOX_SOURCE,
            "fixture_only": True,
            "tenant_id": draft.tenant_id,
            "family_id": draft.family_id,
            "reviewer": reviewer,
            "actor_id": reviewer or "system:sandbox",
            "source_refs": draft.source_refs,
            "draft_hash": draft.draft_hash,
            "draft_version": draft.draft_version,
            "decision": decision,
            "timestamp": timestamp.isoformat(),
            "expiry": expiry.isoformat() if expiry else None,
            "model": draft.provenance.model,
            "model_version": draft.provenance.model_version,
            "provider": draft.provenance.provider_id,
            "prompt_version": draft.provenance.prompt_version,
            "context_snapshot_ref": draft.provenance.context_snapshot_ref,
            "human_gate_task_id": task_id,
            "human_gate_decision_id": decision_id,
            "failure_stop": failure_stop,
            "failure_requires_manual_takeover": failure_stop,
            "may_mutate_business_state": False,
            "allowed_tools": self._policy.allowed_tools,
            "denied_tools": tuple(sorted(self._policy.denied_tools)),
            "sandbox_only": True,
        }
        if extra:
            metadata.update(extra)
        return metadata

    def _record_event(
        self,
        *,
        tenant_id: str,
        family_id: str,
        run_id: str,
        correlation_id: str,
        action: str,
        reason: str,
        timestamp: datetime,
        metadata: dict[str, Any],
    ) -> AuditEvent:
        event = AuditEvent(
            actor_id=str(metadata.get("actor_id") or "system:sandbox"),
            tenant_id=tenant_id,
            action=action,
            resource_type="sandbox.multimodal.draft_insight",
            resource_id=run_id,
            reason=reason,
            correlation_id=correlation_id,
            after=metadata,
            timestamp=timestamp,
        )
        try:
            self._audit.record(event)
        except Exception as exc:
            raise SandboxPolicyError("AUDIT_FAILURE") from exc
        return event

    def _record_generation_failure(
        self,
        preview: StructuredPreview,
        run_id: str,
        timestamp: datetime,
        error: Exception,
    ) -> None:
        self._record_event(
            tenant_id=preview.tenant_id,
            family_id=preview.family_id,
            run_id=run_id,
            correlation_id=f"synthetic-correlation:{run_id}",
            action="sandbox.multimodal.generation_failed",
            reason="Sandbox generation stopped; manual takeover is required.",
            timestamp=timestamp,
            metadata={
                "source": SANDBOX_SOURCE,
                "fixture_only": True,
                "tenant_id": preview.tenant_id,
                "family_id": preview.family_id,
                "source_refs": preview.source_refs,
                "draft_hash": None,
                "draft_version": DRAFT_VERSION,
                "decision": "STOPPED",
                "timestamp": timestamp.isoformat(),
                "expiry": None,
                "model": EXPECTED_MODEL,
                "model_version": EXPECTED_MODEL_VERSION,
                "provider": self._provider.provider_id,
                "failure_stop": True,
                "failure_kind": _failure_code(error),
                "failure_requires_manual_takeover": True,
                "may_mutate_business_state": False,
                "allowed_tools": (),
                "denied_tools": tuple(sorted(self._policy.denied_tools)),
                "sandbox_only": True,
            },
        )

    def _record_preview_failure(
        self,
        input_data: SyntheticFamilyInput,
        error: SandboxPolicyError,
    ) -> None:
        timestamp = datetime.now(UTC)
        self._record_event(
            tenant_id=input_data.tenant_id,
            family_id=input_data.family_id,
            run_id=f"synthetic-preview:{input_data.input_id}",
            correlation_id=f"synthetic-correlation:preview:{input_data.input_id}",
            action="sandbox.multimodal.preview_failed",
            reason="Synthetic preview stopped before model access; manual takeover is required.",
            timestamp=timestamp,
            metadata={
                "source": SANDBOX_SOURCE,
                "fixture_only": True,
                "tenant_id": input_data.tenant_id,
                "family_id": input_data.family_id,
                "source_refs": input_data.source_refs,
                "draft_hash": None,
                "draft_version": DRAFT_VERSION,
                "decision": "STOPPED",
                "timestamp": timestamp.isoformat(),
                "expiry": None,
                "model": None,
                "model_version": None,
                "provider": None,
                "failure_stop": True,
                "failure_kind": _failure_code(error),
                "failure_requires_manual_takeover": True,
                "may_mutate_business_state": False,
                "allowed_tools": (),
                "denied_tools": tuple(sorted(self._policy.denied_tools)),
                "sandbox_only": True,
            },
        )

    def _record_review_failure(
        self,
        draft: DraftInsight,
        timestamp: datetime,
        failure_kind: str,
        reviewer: str,
    ) -> None:
        task = self._tasks[draft.run_id]
        self._record_event(
            tenant_id=draft.tenant_id,
            family_id=draft.family_id,
            run_id=draft.run_id,
            correlation_id=draft.scope.correlation_id,
            action="sandbox.multimodal.review_failed",
            reason="Sandbox review stopped; manual takeover is required.",
            timestamp=timestamp,
            metadata=self._metadata(
                draft=draft,
                decision="STOPPED",
                reviewer=reviewer,
                task_id=task.task_id,
                decision_id=None,
                expiry=task.proposal.expires_at,
                failure_stop=True,
                timestamp=timestamp,
                extra={"failure_kind": failure_kind},
            ),
        )


def _assert_evidence_refs(values: list[Any], source_refs: tuple[str, ...]) -> None:
    if any(not isinstance(value, str) for value in values) or not set(values).issubset(source_refs):
        raise SandboxPolicyError("EVIDENCE_SCOPE_MISMATCH")


def _stable_provenance(provenance: AiProvenance) -> dict[str, Any]:
    return {
        "provider_id": provenance.provider_id,
        "model": provenance.model,
        "model_version": provenance.model_version,
        "prompt_version": provenance.prompt_version,
        "schema_version": provenance.schema_version,
        "context_snapshot_ref": provenance.context_snapshot_ref,
        "use_case": provenance.use_case,
        "data_class": provenance.data_class,
    }


def _aware_now(value: datetime | None) -> datetime:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise SandboxPolicyError("TIMEZONE_REQUIRED")
    return resolved


def _failure_code(error: Exception) -> str:
    if isinstance(error, ModelGatewayError):
        return error.kind
    if isinstance(error, SandboxPolicyError):
        return error.code
    if isinstance(error, HumanGateError):
        return error.code
    return "UNEXPECTED_FAILURE"


def build_multimodal_product_sandbox(
    provider: FakeProvider | None = None,
    *,
    max_cost_microusd: int = 100,
) -> MultimodalProductSandbox:
    """Build only the sandbox composition root; no production environment exists."""

    return MultimodalProductSandbox(provider, max_cost_microusd=max_cost_microusd)


def _demo_input() -> SyntheticFamilyInput:
    return SyntheticFamilyInput(
        input_id="synthetic:input:multimodal-001",
        tenant_id="synthetic:tenant:001",
        family_id="synthetic:family:001",
        guardian_id="synthetic:guardian:001",
        text="合成语音转写：家庭希望把晚间学习启动变得更容易协作。",
        audio_ref="synthetic:audio:multimodal-001",
        audio_sha256="synthetic:sha256:multimodal-001",
        transcript_ref="synthetic:transcript:multimodal-001",
    )


async def _run_demo(
    decision: ReviewDecision,
    edited_perspective: str | None,
    *,
    with_plan: bool = False,
) -> dict[str, Any]:
    sandbox = build_multimodal_product_sandbox()
    input_data = _demo_input()
    preview = sandbox.build_preview(input_data)
    draft = await sandbox.generate_draft(
        preview,
        run_id="synthetic-run:multimodal-demo",
        now=datetime(2026, 8, 31, 10, tzinfo=UTC),
    )
    review = await sandbox.review_draft(
        draft,
        tenant_id=input_data.tenant_id,
        family_id=input_data.family_id,
        guardian_id=input_data.guardian_id,
        decision=decision,
        reason="合成人工审核：保留可校正的解释草案。",
        edited_perspective=edited_perspective,
        now=datetime(2026, 8, 31, 10, 1, tzinfo=UTC),
    )
    result: dict[str, Any] = {
        "source": SANDBOX_SOURCE,
        "fixture_only": True,
        "preview_hash": preview.preview_hash,
        "draft_hash": draft.draft_hash,
        "draft_version": draft.draft_version,
        "perspective": draft.perspective,
        "hypotheses": [item.text for item in draft.hypotheses],
        "review_decision": review.decision.value,
        "failure_stop": review.audit_event.after["failure_stop"]
        if review.audit_event.after
        else None,
        "may_mutate_business_state": draft.may_mutate_business_state,
    }
    if with_plan:
        plan = await sandbox.generate_plan_draft(
            draft, review, now=datetime(2026, 8, 31, 10, 2, tzinfo=UTC)
        )
        result.update(
            {
                "plan_draft_hash": plan.draft_hash,
                "plan_draft_status": plan.status,
                "plan_title": plan.title,
                "plan_knowledge_refs": plan.knowledge_refs,
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the synthetic multimodal DraftInsight sandbox"
    )
    parser.add_argument(
        "--decision",
        choices=tuple(decision.value for decision in ReviewDecision),
        default=ReviewDecision.APPROVE.value,
    )
    parser.add_argument("--edited-perspective", default=None)
    parser.add_argument("--with-plan", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(
        _run_demo(
            ReviewDecision(args.decision),
            args.edited_perspective,
            with_plan=args.with_plan,
        )
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()


__all__ = [
    "DraftInsight",
    "HypothesisDraft",
    "MultimodalProductSandbox",
    "PlanDraft",
    "ReviewDecision",
    "ReviewResult",
    "SandboxContextPolicy",
    "SandboxPolicyError",
    "StructuredPreview",
    "SyntheticFamilyInput",
    "build_multimodal_product_sandbox",
    "main",
]
