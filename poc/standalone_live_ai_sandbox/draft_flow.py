"""Synthetic H-LIVE-07 AI draft flow and replay evaluation.

This module is a disposable research sandbox.  It does not implement or
replace AiFamily's Model Gateway, Provenance, Human Gate, audit store, or
canonical facts.  Those dependencies are explicit ports so the experiment can
be replayed without inventing a second AI runtime or writing production data.

The only behavior covered is: a synthetic live transcript becomes a summary
draft, a human reviews it, and the review remains a sandbox decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"
PROMPT_VERSION = "xiaojudeng-summary-v1"


class AISandboxBoundaryError(ValueError):
    """A synthetic AI input/output violates an explicit boundary."""


class AISandboxStopped(RuntimeError):
    """The AI experiment failed closed and produced no draft."""


class HumanGateRejected(RuntimeError):
    """A review was attempted by an unauthorised actor or with bad scope."""


class DraftStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED_DRAFT = "APPROVED_DRAFT"
    EDITED_DRAFT = "EDITED_DRAFT"
    REJECTED_DRAFT = "REJECTED_DRAFT"


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    EDIT = "EDIT"


@dataclass(frozen=True, slots=True)
class SyntheticTranscript:
    tenant_id: str
    family_id: str
    session_ref: str
    transcript_ref: str
    text: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.fixture_only or self.source != SANDBOX_SOURCE:
            raise AISandboxBoundaryError("AI input must be explicitly synthetic")
        if not all(
            (
                self.tenant_id,
                self.family_id,
                self.session_ref,
                self.transcript_ref,
                self.text.strip(),
            )
        ):
            raise ValueError("synthetic transcript identity and text are required")


@dataclass(frozen=True, slots=True)
class GatewayResult:
    text: str
    provider: str
    model: str
    model_version: str
    prompt_version: str


class ModelGatewayPort(Protocol):
    """AiFamily-owned model boundary; providers never leak into this flow."""

    def generate_summary(self, transcript: SyntheticTranscript) -> GatewayResult: ...


class ProvenancePort(Protocol):
    """AiFamily-owned provenance boundary for every generated draft."""

    def record_draft(
        self,
        *,
        transcript: SyntheticTranscript,
        result: GatewayResult,
        draft_hash: str,
    ) -> str: ...

    def record_failure(
        self, *, transcript: SyntheticTranscript, reason: str, occurred_at: datetime
    ) -> None: ...


class HumanGatePort(Protocol):
    """AiFamily-owned human review boundary; approval is not a Fact write."""

    def review(
        self,
        *,
        draft: DraftSummary,
        reviewer_id: str,
        tenant_id: str,
        family_id: str,
        decision: ReviewDecision,
        reason: str,
        edited_text: str | None,
        occurred_at: datetime,
    ) -> DraftSummary: ...


@dataclass(frozen=True, slots=True)
class DraftSummary:
    draft_ref: str
    transcript_ref: str
    tenant_id: str
    family_id: str
    text: str
    provenance_ref: str
    draft_hash: str
    status: DraftStatus = DraftStatus.DRAFT
    model: str = ""
    model_version: str = ""
    provider: str = ""
    prompt_version: str = PROMPT_VERSION
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.fixture_only or self.source != SANDBOX_SOURCE:
            raise AISandboxBoundaryError("AI output must remain explicitly synthetic")
        if self.status is not DraftStatus.DRAFT and not self.text.strip():
            raise ValueError("reviewed draft text must not be empty")


@dataclass(frozen=True, slots=True)
class SandboxAuditEntry:
    action: str
    draft_ref: str
    actor_id: str
    tenant_id: str
    family_id: str
    input_ref: str
    draft_hash: str
    decision: str
    reason: str
    occurred_at: datetime
    expiry: datetime | None
    model: str
    provider: str
    failure_stop: bool


class InMemoryProvenanceFixture:
    """Sandbox test double, not a canonical provenance or audit store."""

    def __init__(self) -> None:
        self.records: list[tuple[DraftSummary, SyntheticTranscript]] = []
        self.audit: list[SandboxAuditEntry] = []
        self.failure_audit: list[SandboxAuditEntry] = []

    def record_draft(
        self,
        *,
        transcript: SyntheticTranscript,
        result: GatewayResult,
        draft_hash: str,
    ) -> str:
        draft_ref = f"draft.synthetic.{len(self.records) + 1}"
        draft = DraftSummary(
            draft_ref=draft_ref,
            transcript_ref=transcript.transcript_ref,
            tenant_id=transcript.tenant_id,
            family_id=transcript.family_id,
            text=result.text,
            provenance_ref=f"provenance.synthetic.{draft_hash[:12]}",
            draft_hash=draft_hash,
            provider=result.provider,
            model=result.model,
            model_version=result.model_version,
            prompt_version=result.prompt_version,
        )
        self.records.append((draft, transcript))
        return draft_ref

    def record_review(self, entry: SandboxAuditEntry) -> None:
        self.audit.append(entry)

    def record_failure(
        self, *, transcript: SyntheticTranscript, reason: str, occurred_at: datetime
    ) -> None:
        self.failure_audit.append(
            SandboxAuditEntry(
                action="ai.failure_stop",
                draft_ref="",
                actor_id="system:sandbox",
                tenant_id=transcript.tenant_id,
                family_id=transcript.family_id,
                input_ref=transcript.transcript_ref,
                draft_hash="",
                decision="STOP",
                reason=reason,
                occurred_at=occurred_at,
                expiry=None,
                model="",
                provider="fake-gateway",
                failure_stop=True,
            )
        )


class InMemoryHumanGateFixture:
    """Synthetic reviewer; it never promotes a draft to a canonical Fact."""

    def __init__(self, *, audit: InMemoryProvenanceFixture) -> None:
        self.audit = audit

    def review(
        self,
        *,
        draft: DraftSummary,
        reviewer_id: str,
        tenant_id: str,
        family_id: str,
        decision: ReviewDecision,
        reason: str,
        edited_text: str | None,
        occurred_at: datetime,
    ) -> DraftSummary:
        if not reviewer_id.startswith("human:"):
            raise HumanGateRejected("AI or anonymous actor cannot review a draft")
        if draft.tenant_id != tenant_id or draft.family_id != family_id:
            raise HumanGateRejected("human review crossed tenant/family scope")
        if not reason.strip():
            raise ValueError("human review reason is required")
        if decision is ReviewDecision.EDIT and not edited_text:
            raise ValueError("edited draft requires edited text")
        if decision is ReviewDecision.APPROVE:
            status = DraftStatus.APPROVED_DRAFT
            text = draft.text
        elif decision is ReviewDecision.EDIT:
            status = DraftStatus.EDITED_DRAFT
            text = edited_text or ""
        else:
            status = DraftStatus.REJECTED_DRAFT
            text = draft.text
        reviewed = DraftSummary(
            draft_ref=draft.draft_ref,
            transcript_ref=draft.transcript_ref,
            tenant_id=draft.tenant_id,
            family_id=draft.family_id,
            text=text,
            provenance_ref=draft.provenance_ref,
            draft_hash=draft.draft_hash,
            status=status,
            model=draft.model,
            model_version=draft.model_version,
            provider=draft.provider,
            prompt_version=draft.prompt_version,
        )
        self.audit.record_review(
            SandboxAuditEntry(
                action="human_gate.review_draft",
                draft_ref=draft.draft_ref,
                actor_id=reviewer_id,
                tenant_id=tenant_id,
                family_id=family_id,
                input_ref=draft.transcript_ref,
                draft_hash=draft.draft_hash,
                decision=decision.value,
                reason=reason,
                occurred_at=occurred_at,
                expiry=None,
                model=draft.model,
                provider=draft.provider,
                failure_stop=False,
            )
        )
        return reviewed


class FakeModelGateway:
    """Deterministic fake provider with explicit injection points."""

    def __init__(self, *, timeout: bool = False, prompt_injection: bool = False) -> None:
        self.timeout = timeout
        self.prompt_injection = prompt_injection
        self.calls = 0

    def generate_summary(self, transcript: SyntheticTranscript) -> GatewayResult:
        self.calls += 1
        if self.timeout:
            raise TimeoutError("synthetic model timeout")
        if self.prompt_injection or "ignore previous instructions" in transcript.text.lower():
            raise ValueError("prompt injection detected")
        return GatewayResult(
            text=f"摘要草案：{transcript.text[:80]}",
            provider="fake-gateway",
            model="fake-gateway",
            model_version="synthetic-1",
            prompt_version=PROMPT_VERSION,
        )


class AISandboxFlow:
    """Generate and review drafts without any canonical business mutation."""

    def __init__(
        self,
        *,
        gateway: ModelGatewayPort,
        provenance: ProvenancePort,
        human_gate: HumanGatePort,
    ) -> None:
        self.gateway = gateway
        self.provenance = provenance
        self.human_gate = human_gate

    def generate(self, transcript: SyntheticTranscript) -> DraftSummary:
        try:
            result = self.gateway.generate_summary(transcript)
        except (TimeoutError, ValueError) as exc:
            self.provenance.record_failure(
                transcript=transcript,
                reason=str(exc),
                occurred_at=datetime.now(UTC),
            )
            raise AISandboxStopped("AI generation stopped closed") from exc
        draft_hash = sha256(
            f"{transcript.transcript_ref}:{result.text}:{result.prompt_version}".encode()
        ).hexdigest()
        draft_ref = self.provenance.record_draft(
            transcript=transcript,
            result=result,
            draft_hash=draft_hash,
        )
        return DraftSummary(
            draft_ref=draft_ref,
            transcript_ref=transcript.transcript_ref,
            tenant_id=transcript.tenant_id,
            family_id=transcript.family_id,
            text=result.text,
            provenance_ref=f"provenance.synthetic.{draft_hash[:12]}",
            draft_hash=draft_hash,
            provider=result.provider,
            model=result.model,
            model_version=result.model_version,
            prompt_version=result.prompt_version,
        )

    def review(
        self,
        *,
        draft: DraftSummary,
        reviewer_id: str,
        decision: ReviewDecision,
        reason: str,
        edited_text: str | None = None,
        occurred_at: datetime | None = None,
    ) -> DraftSummary:
        return self.human_gate.review(
            draft=draft,
            reviewer_id=reviewer_id,
            tenant_id=draft.tenant_id,
            family_id=draft.family_id,
            decision=decision,
            reason=reason,
            edited_text=edited_text,
            occurred_at=occurred_at or datetime.now(UTC),
        )
