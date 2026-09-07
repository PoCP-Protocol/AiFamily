"""Context-driven, read-only path drafting for Slice C-01."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime

from backend.intelligence.context_engine.contracts import ContextScope

from .contracts import (
    CapabilityCandidate,
    CapabilityCandidatePort,
    FamilyPathContext,
    FamilyPathContextPort,
    PathDraft,
    PathDraftError,
    PathDraftScopeError,
)


class ContextDrivenPathDraftPlanner:
    """Compose a path from server-owned context and capability ports.

    This is intentionally the smallest useful Slice C implementation: it does
    not pretend to be the final autonomous Agent Runtime.  The planner proves
    that candidate selection is driven by a read-only family context rather
    than by a fixed screen sequence, while leaving model generation and human
    acceptance as explicit later seams.
    """

    def __init__(
        self,
        context_port: FamilyPathContextPort,
        capability_port: CapabilityCandidatePort,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(getattr(context_port, "read", None)):
            raise TypeError("context_port must implement read")
        if not callable(getattr(capability_port, "list_candidates", None)):
            raise TypeError("capability_port must implement list_candidates")
        self._context_port = context_port
        self._capability_port = capability_port
        self._clock = clock or (lambda: datetime.now(UTC))

    async def draft(self, *, scope: ContextScope, need_id: str) -> PathDraft:
        scope.assert_active()
        context = await self._context_port.read(scope=scope, need_id=need_id)
        _assert_context_scope(scope, context, requested_need_id=need_id)
        candidates = await self._capability_port.list_candidates(scope=scope, context=context)
        if any(candidate is None for candidate in candidates):
            raise PathDraftError("capability candidate port returned null")

        ranked = sorted(
            candidates,
            key=lambda candidate: _candidate_score(candidate, context),
            reverse=True,
        )
        selected = tuple(
            candidate for candidate in ranked if _candidate_score(candidate, context) > 0
        )[:3]
        reasons = {
            candidate.capability_ref: _reasons(candidate, context)
            for candidate in selected
        }
        questions = _clarifying_questions(context, selected)
        draft_id = _draft_id(context, selected)
        generated_at = self._clock()
        if generated_at.tzinfo is None:
            raise PathDraftError("path planner clock must return timezone-aware datetime")
        return PathDraft(
            draft_id=draft_id,
            version=1,
            tenant_id=context.tenant_id,
            family_id=context.family_id,
            need_id=context.need_id,
            context_snapshot_ref=context.context_snapshot_ref,
            nodes=selected,
            selected_reasons=reasons,
            clarifying_questions=questions,
            feedback_refs=context.feedback_refs,
            generated_at=generated_at,
        )


def _assert_context_scope(
    scope: ContextScope,
    context: FamilyPathContext,
    *,
    requested_need_id: str,
) -> None:
    if context.tenant_id != scope.tenant_id or context.family_id != scope.family_id:
        raise PathDraftScopeError("path context scope mismatch")
    if scope.subject_ids != tuple(context.subject_ids):
        raise PathDraftScopeError("path context subject scope mismatch")
    if context.need_id.strip() == "":
        raise PathDraftError("path context need id is required")
    if context.need_id != requested_need_id:
        raise PathDraftScopeError("path context need mismatch")


def _candidate_score(candidate: CapabilityCandidate, context: FamilyPathContext) -> int:
    return len(candidate.fit_tags & context.fit_tags) * 10 + len(
        candidate.prerequisite_tags & context.fit_tags
    )


def _reasons(candidate: CapabilityCandidate, context: FamilyPathContext) -> tuple[str, ...]:
    matched = sorted(candidate.fit_tags & context.fit_tags)
    reasons = [f"context_fit:{tag}" for tag in matched]
    reasons.append(f"evidence:{context.evidence[0].ref}")
    reasons.extend(f"candidate_evidence:{item.ref}" for item in candidate.evidence)
    return tuple(reasons)


def _clarifying_questions(
    context: FamilyPathContext, selected: tuple[CapabilityCandidate, ...]
) -> tuple[str, ...]:
    questions = list(context.unknowns)
    if not selected:
        questions.append("这件事最希望先看到哪一种变化？")
    return tuple(dict.fromkeys(question for question in questions if question.strip()))


def _draft_id(context: FamilyPathContext, selected: tuple[CapabilityCandidate, ...]) -> str:
    material = "|".join(
        (context.tenant_id, context.family_id, context.need_id, context.context_snapshot_ref)
        + tuple(candidate.capability_ref for candidate in selected)
    )
    return "path-draft:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


__all__ = ["ContextDrivenPathDraftPlanner"]
