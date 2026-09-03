"""Read-only evaluation of durable family-understanding revision interactions."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from backend.intelligence.experience.family_problem_understanding_preparation import (
    FamilyProblemUnderstandingPreparation,
)
from backend.intelligence.experience.run_http import (
    InteractionType,
    RunReplaySnapshot,
    RunScope,
)

SelectionStatus = Literal["NOT_MEASURED", "DESCRIPTIVE_ONLY", "ELIGIBLE"]


class ScopedReplayLedger(Protocol):
    def replay(self, *, scope: RunScope, run_id: str) -> RunReplaySnapshot | Any: ...


@dataclass(frozen=True, slots=True)
class StoredUnderstandingPreparation:
    preparation_ref: str
    run_id: str
    prior_run_id: str
    context_snapshot_ref: str
    draft_version: str
    candidate_id: str
    expected_response_count: int
    preparation: FamilyProblemUnderstandingPreparation


class UnderstandingPreparationRepository(Protocol):
    def get(
        self, *, scope: RunScope, preparation_ref: str
    ) -> StoredUnderstandingPreparation | Any: ...


@dataclass(frozen=True, slots=True)
class DurableRevisionObservation:
    prior_run_id: str
    current_run_id: str
    preparation_ref: str
    context_snapshot_ref: str
    prior_draft_hash: str
    current_draft_hash: str
    prior_hypotheses: tuple[str, ...]
    current_hypotheses: tuple[str, ...]
    hypotheses_changed: bool
    response_count: int
    expected_response_count: int
    coverage_rate: float
    rating_distribution: tuple[tuple[int, int], ...]
    high_understanding_rate: float | None
    low_understanding_rate: float | None
    felt_understood_mean: float | None
    response_relevance_mean: float | None
    felt_judged_rate: float | None
    willing_to_continue_rate: float | None
    correction_rate: float | None
    correction_resolution_rate: float | None
    selection_status: SelectionStatus
    selection_bias: str
    may_mutate_business_state: bool = False

    def as_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


async def observe_replayed_revision_from_ledger(
    *,
    ledger: ScopedReplayLedger,
    preparation_repository: UnderstandingPreparationRepository,
    scope: RunScope,
    prior_run_id: str,
    current_run_id: str,
    preparation_ref: str,
) -> DurableRevisionObservation:
    """Replay both runs now and load one canonical preparation record."""

    prior = await _replay(ledger, scope, prior_run_id)
    current = await _replay(ledger, scope, current_run_id)
    stored = preparation_repository.get(scope=scope, preparation_ref=preparation_ref)
    if inspect.isawaitable(stored):
        stored = await stored
    if not isinstance(stored, StoredUnderstandingPreparation):
        raise ValueError("preparation repository returned an invalid record")
    _validate_lineage(stored, preparation_ref, prior_run_id, current_run_id, prior)

    feedback = _project_exact_feedback(
        prior,
        draft_version=stored.draft_version,
        candidate_id=stored.candidate_id,
        expected_response_count=stored.expected_response_count,
    )
    prior_hypotheses = _hypotheses(prior.draft_payload)
    current_hypotheses = _hypotheses(current.draft_payload)
    return DurableRevisionObservation(
        prior_run_id=prior.run_id,
        current_run_id=current.run_id,
        preparation_ref=stored.preparation_ref,
        context_snapshot_ref=stored.context_snapshot_ref,
        prior_draft_hash=_digest(prior.draft_payload),
        current_draft_hash=_digest(current.draft_payload),
        prior_hypotheses=prior_hypotheses,
        current_hypotheses=current_hypotheses,
        hypotheses_changed=prior_hypotheses != current_hypotheses,
        **feedback,
    )


async def _replay(ledger: ScopedReplayLedger, scope: RunScope, run_id: str) -> RunReplaySnapshot:
    replay = ledger.replay(scope=scope, run_id=run_id)
    if inspect.isawaitable(replay):
        replay = await replay
    if not isinstance(replay, RunReplaySnapshot) or replay.scope.key != scope.key:
        raise ValueError("ledger returned a cross-scope or invalid replay")
    if replay.deletion_state != "active" or replay.draft_payload is None:
        raise ValueError("durable replay draft is unavailable")
    return replay


def _validate_lineage(
    stored: StoredUnderstandingPreparation,
    preparation_ref: str,
    prior_run_id: str,
    current_run_id: str,
    prior: RunReplaySnapshot,
) -> None:
    request = stored.preparation.request
    if (
        stored.preparation_ref != preparation_ref
        or stored.run_id != current_run_id
        or stored.prior_run_id != prior_run_id
        or request.run_id != current_run_id
        or request.context_snapshot_ref != stored.context_snapshot_ref
        or request.payload.get("prior_run_id") != prior_run_id
        or request.payload.get("prior_draft") != prior.draft_payload
    ):
        raise ValueError("canonical preparation lineage mismatch")
    request_knowledge = {
        str(item["knowledge_ref"]) for item in request.payload.get("reviewed_knowledge", ())
    }
    if request_knowledge != set(stored.preparation.eval_spec.allowed_knowledge_refs):
        raise ValueError("canonical preparation knowledge refs drifted")
    if set(request.input_refs) != set(stored.preparation.eval_spec.allowed_evidence_refs):
        raise ValueError("canonical preparation evidence refs drifted")
    if stored.expected_response_count <= 0:
        raise ValueError("expected response count must be positive")


def _project_exact_feedback(
    replay: RunReplaySnapshot,
    *,
    draft_version: str,
    candidate_id: str,
    expected_response_count: int,
) -> dict[str, object]:
    latest: dict[str, Mapping[str, Any]] = {}
    for entry in replay.interactions:
        payload = entry.payload
        if (
            entry.interaction_type is InteractionType.FEEDBACK
            and payload.get("feedback_kind") == "family_understanding"
            and payload.get("draft_version") == draft_version
            and payload.get("candidate_id") == candidate_id
        ):
            actor = str(payload.get("adult_actor_ref", ""))
            if actor:
                latest[actor] = payload
    values = tuple(latest.values())
    count = len(values)
    coverage = round(count / expected_response_count, 6)
    distribution = Counter(int(value["understood_rating"]) for value in values)
    rating_distribution = tuple((rating, distribution.get(rating, 0)) for rating in range(1, 6))
    if count == 0:
        status: SelectionStatus = "NOT_MEASURED"
    elif count < 3 or coverage < 0.5:
        status = "DESCRIPTIVE_ONLY"
    else:
        status = "ELIGIBLE"
    publish_means = status == "ELIGIBLE"
    ratings = [int(value["understood_rating"]) for value in values]
    relevance = [int(value["response_relevance"]) for value in values]
    corrections = [value for value in values if bool(value["correction_needed"])]
    return {
        "response_count": count,
        "expected_response_count": expected_response_count,
        "coverage_rate": coverage,
        "rating_distribution": rating_distribution,
        "high_understanding_rate": _rate(ratings, lambda value: value >= 4)
        if publish_means
        else None,
        "low_understanding_rate": _rate(ratings, lambda value: value <= 2)
        if publish_means
        else None,
        "felt_understood_mean": _rating_mean(ratings) if publish_means else None,
        "response_relevance_mean": _rating_mean(relevance) if publish_means else None,
        "felt_judged_rate": _bool_rate(values, "felt_judged") if publish_means else None,
        "willing_to_continue_rate": _bool_rate(values, "willing_to_continue")
        if publish_means
        else None,
        "correction_rate": round(len(corrections) / count, 6) if publish_means else None,
        "correction_resolution_rate": (
            round(
                sum(value.get("correction_resolved") is True for value in corrections)
                / len(corrections),
                6,
            )
            if publish_means and corrections
            else None
        ),
        "selection_status": status,
        "selection_bias": (
            "complete-enough-for-comparison"
            if status == "ELIGIBLE"
            else "insufficient-or-self-selected-feedback"
        ),
    }


def _hypotheses(draft: Mapping[str, object] | None) -> tuple[str, ...]:
    values = draft.get("hypotheses") if draft is not None else None
    return tuple(
        str(item["statement"])
        for item in values or ()
        if isinstance(item, Mapping) and isinstance(item.get("statement"), str)
    )


def _digest(draft: Mapping[str, object] | None) -> str:
    payload = json.dumps(
        dict(draft) if draft is not None else None,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _rating_mean(values: list[int]) -> float:
    return round(sum((value - 1) / 4 for value in values) / len(values), 6)


def _rate(values: list[int], predicate: Any) -> float:
    return round(sum(predicate(value) for value in values) / len(values), 6)


def _bool_rate(values: tuple[Mapping[str, Any], ...], key: str) -> float:
    return round(sum(bool(value[key]) for value in values) / len(values), 6)


__all__ = [
    "DurableRevisionObservation",
    "ScopedReplayLedger",
    "StoredUnderstandingPreparation",
    "UnderstandingPreparationRepository",
    "observe_replayed_revision_from_ledger",
]
