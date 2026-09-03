"""Deterministic two-stage curation for the experience gateway.

This module borrows the useful part of a large-scale content recommender:
recall a broad candidate set first, then apply a small, auditable delivery
policy before choosing the next few items.  The policy is intentionally about
content delivery, never about scoring families or children.

No model or domain repository is imported here.  A future AI curator may
produce candidates, but the final admission policy remains deterministic and
the result is emitted as a ``RecommendationDecision`` through the gateway.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.intelligence.experience.contracts import (
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    RecommendationDecision,
    ScopeMismatchError,
)
from backend.intelligence.experience.gateway import ExperienceGateway
from backend.platform.idempotency.keys import IdempotencyKey

_LOCALE_RE = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")


@dataclass(frozen=True, slots=True)
class ExperienceCandidate:
    """A recalled content/action candidate, not a business fact."""

    candidate_id: str
    source_ref: str
    scope: ExperienceScope
    content_locale: str
    delivery_priority: int = 0
    eligible: bool = True
    is_commercial: bool = False
    cooldown_until: datetime | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.source_ref:
            raise ExperienceContractError("CANDIDATE_ID_AND_SOURCE_REQUIRED")
        if not isinstance(self.scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not _LOCALE_RE.fullmatch(self.content_locale):
            raise ExperienceContractError("CANDIDATE_LOCALE_UNSUPPORTED")
        if not isinstance(self.delivery_priority, int):
            raise ExperienceContractError("CANDIDATE_PRIORITY_UNSUPPORTED")


@dataclass(frozen=True, slots=True)
class CurationResult:
    """Decision plus policy evidence for an application response."""

    decision: RecommendationDecision
    recalled_count: int
    admitted_count: int
    filtered_count: int


class RecommendationCurator:
    """Recall, policy-filter, and order candidates for one exact scope."""

    def __init__(self, gateway: ExperienceGateway) -> None:
        self._gateway = gateway

    def curate(
        self,
        *,
        request_id: str,
        scope: ExperienceScope,
        candidates: Iterable[ExperienceCandidate],
        strategy_version: str,
        idempotency_key: IdempotencyKey,
        provenance: ExperienceProvenance,
        limit: int = 3,
        now: datetime | None = None,
    ) -> CurationResult:
        """Create and publish a proposal without mutating business state."""

        if not request_id or not strategy_version:
            raise ExperienceContractError("CURATION_REQUEST_AND_STRATEGY_REQUIRED")
        if not isinstance(scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not isinstance(idempotency_key, IdempotencyKey):
            raise ExperienceContractError("IDEMPOTENCY_KEY_REQUIRED")
        if idempotency_key.tenant_id != scope.tenant_id:
            raise ScopeMismatchError("IDEMPOTENCY_TENANT_MISMATCH")
        if limit <= 0:
            raise ValueError("limit must be positive")

        recalled = _deduplicate(candidates)
        reference = now or datetime.now(UTC)
        admitted: list[ExperienceCandidate] = []
        reasons: list[str] = []
        for candidate in recalled:
            reason = _filter_reason(candidate, scope, reference)
            if reason is None:
                admitted.append(candidate)
            else:
                reasons.append(reason)
        if not admitted:
            raise ExperienceContractError("NO_ELIGIBLE_CANDIDATE")

        ordered = sorted(
            admitted,
            key=lambda candidate: (-candidate.delivery_priority, candidate.candidate_id),
        )
        selected = tuple(candidate.candidate_id for candidate in ordered[:limit])
        decision = RecommendationDecision(
            decision_id=f"decision:{request_id}",
            request_id=request_id,
            scope=scope,
            idempotency_key=idempotency_key,
            provenance=provenance,
            strategy_version=strategy_version,
            candidate_ids=tuple(candidate.candidate_id for candidate in ordered),
            selected_ids=selected,
            reason_codes=(
                f"recalled:{len(recalled)}",
                f"admitted:{len(admitted)}",
                f"filtered:{len(reasons)}",
                *tuple(sorted(set(reasons))),
            ),
        )
        published = self._gateway.publish_decision(decision)
        return CurationResult(
            decision=published,
            recalled_count=len(recalled),
            admitted_count=len(admitted),
            filtered_count=len(reasons),
        )


def _deduplicate(candidates: Iterable[ExperienceCandidate]) -> list[ExperienceCandidate]:
    unique: dict[str, ExperienceCandidate] = {}
    for candidate in candidates:
        previous = unique.get(candidate.candidate_id)
        if previous is not None and previous != candidate:
            raise ExperienceContractError("CANDIDATE_ID_COLLISION")
        unique[candidate.candidate_id] = candidate
    return list(unique.values())


def _filter_reason(
    candidate: ExperienceCandidate,
    scope: ExperienceScope,
    now: datetime,
) -> str | None:
    if not _same_scope(candidate.scope, scope):
        return "scope_mismatch"
    if not candidate.eligible:
        return "candidate_ineligible"
    if candidate.content_locale != scope.content_locale:
        return "locale_mismatch"
    if candidate.is_commercial and str(scope.data_class) == "MINOR_PERSONAL_DATA":
        return "minor_commercial_blocked"
    if candidate.cooldown_until is not None and _as_utc(candidate.cooldown_until) > _as_utc(now):
        return "frequency_guard"
    return None


def _same_scope(left: ExperienceScope, right: ExperienceScope) -> bool:
    return (
        left.tenant_id == right.tenant_id
        and left.region_id == right.region_id
        and left.family_id == right.family_id
        and frozenset(left.subject_ids) == frozenset(right.subject_ids)
        and left.purpose == right.purpose
        and left.consent_version == right.consent_version
    )


def _as_utc(value: datetime) -> datetime:
    return (value if value.tzinfo is not None else value.replace(tzinfo=UTC)).astimezone(UTC)


__all__ = ["CurationResult", "ExperienceCandidate", "RecommendationCurator"]
