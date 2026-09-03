"""Evaluate one family-understanding revision from durable replayed interactions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass

from backend.intelligence.experience.family_problem_understanding_feedback import (
    project_family_understanding_feedback,
)
from backend.intelligence.experience.family_problem_understanding_preparation import (
    FamilyProblemUnderstandingPreparation,
)
from backend.intelligence.experience.run_http import RunReplaySnapshot


@dataclass(frozen=True, slots=True)
class ReplayedRevisionObservation:
    prior_run_id: str
    current_run_id: str
    prior_draft_hash: str
    current_draft_hash: str
    prior_hypotheses: tuple[str, ...]
    current_hypotheses: tuple[str, ...]
    hypotheses_changed: bool
    reviewed_knowledge_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    feedback_response_count: int
    felt_understood_mean: float | None
    response_relevance_mean: float | None
    felt_judged_rate: float | None
    willing_to_continue_rate: float | None
    correction_rate: float | None
    correction_resolution_rate: float | None
    latest_correction_ref: str | None
    may_mutate_business_state: bool = False

    def as_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


def observe_replayed_revision(
    *,
    prior_replay: RunReplaySnapshot,
    preparation: FamilyProblemUnderstandingPreparation,
    current_replay: RunReplaySnapshot,
) -> ReplayedRevisionObservation:
    """Observe actual persisted drafts and feedback; reject detached eval inputs."""

    if prior_replay.deletion_state != "active" or prior_replay.draft_payload is None:
        raise ValueError("prior durable draft is unavailable")
    if current_replay.deletion_state != "active" or current_replay.draft_payload is None:
        raise ValueError("current durable draft is unavailable")
    if prior_replay.scope.key != current_replay.scope.key:
        raise ValueError("revision replay scope mismatch")
    request_prior_run_id = preparation.request.payload.get("prior_run_id")
    request_prior_draft = preparation.request.payload.get("prior_draft")
    if request_prior_run_id != prior_replay.run_id:
        raise ValueError("preparation does not reference replayed prior run")
    if request_prior_draft != prior_replay.draft_payload:
        raise ValueError("preparation prior draft drifted from durable replay")

    request_knowledge = tuple(
        sorted(
            str(item["knowledge_ref"])
            for item in preparation.request.payload.get("reviewed_knowledge", ())
        )
    )
    if set(request_knowledge) != set(preparation.eval_spec.allowed_knowledge_refs):
        raise ValueError("reviewed knowledge drifted from evaluation refs")
    evidence_refs = tuple(sorted(preparation.request.input_refs))
    if set(evidence_refs) != set(preparation.eval_spec.allowed_evidence_refs):
        raise ValueError("evidence drifted from evaluation refs")

    feedback = project_family_understanding_feedback(prior_replay)
    prior_hypotheses = _hypotheses(prior_replay.draft_payload)
    current_hypotheses = _hypotheses(current_replay.draft_payload)
    return ReplayedRevisionObservation(
        prior_run_id=prior_replay.run_id,
        current_run_id=current_replay.run_id,
        prior_draft_hash=_digest(prior_replay.draft_payload),
        current_draft_hash=_digest(current_replay.draft_payload),
        prior_hypotheses=prior_hypotheses,
        current_hypotheses=current_hypotheses,
        hypotheses_changed=prior_hypotheses != current_hypotheses,
        reviewed_knowledge_refs=request_knowledge,
        evidence_refs=evidence_refs,
        feedback_response_count=feedback.response_count,
        felt_understood_mean=feedback.felt_understood_mean,
        response_relevance_mean=feedback.response_relevance_mean,
        felt_judged_rate=feedback.felt_judged_rate,
        willing_to_continue_rate=feedback.willing_to_continue_rate,
        correction_rate=feedback.correction_rate,
        correction_resolution_rate=feedback.correction_resolution_rate,
        latest_correction_ref=feedback.latest_correction_ref,
    )


def _hypotheses(draft: Mapping[str, object]) -> tuple[str, ...]:
    values = draft.get("hypotheses")
    if not isinstance(values, list):
        return ()
    return tuple(
        str(item["statement"])
        for item in values
        if isinstance(item, Mapping)
        and isinstance(item.get("statement"), str)
        and str(item["statement"]).strip()
    )


def _digest(draft: Mapping[str, object]) -> str:
    payload = json.dumps(draft, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


__all__ = ["ReplayedRevisionObservation", "observe_replayed_revision"]
