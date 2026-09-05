"""Evidence-bound, non-comparative achievement projection.

The achievement engine turns real interaction events into a feeling of
progress without inventing a score.  It is intentionally small: chapters and
milestones can grow later, while every visible achievement remains tied to an
append-only event and can be paused or withdrawn by the family.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from backend.intelligence.experience.contracts import (
    ExperienceContractError,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceProvenance,
    ExperienceScope,
)
from backend.platform.idempotency.keys import IdempotencyKey


class AchievementKey(StrEnum):
    FIRST_STEP = "first_step"
    PAUSE_AND_RETURN = "pause_and_return"
    SERVICE_INTENT_EXPRESSED = "service_intent_expressed"
    AI_EVIDENCE_MOMENT = "ai_evidence_moment"


_ACHIEVEMENT_BASES = frozenset(
    {
        "ACTION_COMPLETED",
        "REFLECTION_SUBMITTED",
        "RELATIONSHIP_FEEDBACK",
        "CONTRIBUTION_VERIFIED",
    }
)


@dataclass(frozen=True, slots=True)
class Achievement:
    """A family-owned milestone with human-readable evidence references."""

    achievement_id: str
    key: AchievementKey
    title: str
    message: str
    scope: ExperienceScope
    evidence_refs: tuple[str, ...]
    provenance: ExperienceProvenance
    idempotency_key: IdempotencyKey
    earned_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # These fields are explicit anti-gaming policy, not presentation metadata.
    # Defaults preserve compatibility for existing achievement producers while
    # making every projection family-private, non-comparative and non-commercial.
    basis: str = "ACTION_COMPLETED"
    visibility: str = "FAMILY_PRIVATE"
    comparison_scope: str = "NONE"
    commercial_reward: str = "NONE"
    # Stable identity for a repeatable milestone occurrence. ``default`` keeps
    # legacy one-time milestones idempotent; AI evidence moments derive a
    # value from their evidence set so distinct events can earn separately.
    occurrence_id: str = "default"

    def __post_init__(self) -> None:
        if not self.achievement_id or not self.title or not self.message:
            raise ExperienceContractError("ACHIEVEMENT_FIELDS_REQUIRED")
        if not isinstance(self.key, AchievementKey):
            raise ExperienceContractError("ACHIEVEMENT_KEY_UNSUPPORTED")
        if not isinstance(self.scope, ExperienceScope):
            raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")
        if not self.evidence_refs or any(not value for value in self.evidence_refs):
            raise ExperienceContractError("ACHIEVEMENT_EVIDENCE_REQUIRED")
        if not isinstance(self.provenance, ExperienceProvenance):
            raise ExperienceContractError("PROVENANCE_REQUIRED")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise ExperienceContractError("IDEMPOTENCY_KEY_REQUIRED")
        if self.idempotency_key.tenant_id != self.scope.tenant_id:
            raise ExperienceContractError("IDEMPOTENCY_TENANT_MISMATCH")
        if self.basis not in _ACHIEVEMENT_BASES:
            raise ExperienceContractError("ACHIEVEMENT_BASIS_UNSUPPORTED")
        if self.visibility != "FAMILY_PRIVATE":
            raise ExperienceContractError("ACHIEVEMENT_VISIBILITY_MUST_BE_PRIVATE")
        if self.comparison_scope != "NONE":
            raise ExperienceContractError("ACHIEVEMENT_COMPARISON_FORBIDDEN")
        if self.commercial_reward != "NONE":
            raise ExperienceContractError("ACHIEVEMENT_COMMERCIAL_REWARD_FORBIDDEN")
        if not isinstance(self.occurrence_id, str) or not self.occurrence_id.strip():
            raise ExperienceContractError("ACHIEVEMENT_OCCURRENCE_REQUIRED")
        if len(self.occurrence_id) > 256:
            raise ExperienceContractError("ACHIEVEMENT_OCCURRENCE_TOO_LONG")


class AchievementProjectionPort(Protocol):
    """Provider-neutral read-model port for evidence-bound achievements.

    Implementations may be synchronous (the in-memory dev/test adapter) or
    asynchronous (the SQL adapter).  The engine's ``apply_async`` composition
    path normalises both forms without allowing a persistence adapter to own a
    transaction or mutate a canonical domain fact.
    """

    def append(self, achievement: Achievement) -> Achievement | Awaitable[Achievement]:
        """Persist one achievement idempotently by scope and key."""
        ...

    def earned(
        self, scope: ExperienceScope
    ) -> tuple[Achievement, ...] | Awaitable[tuple[Achievement, ...]]:
        """Read this exact scope's earned achievements."""
        ...


class InMemoryAchievementProjection:
    """Append-only read model keyed by exact family scope and achievement key."""

    def __init__(self) -> None:
        self._records: dict[tuple[tuple[str, ...], AchievementKey, str], Achievement] = {}

    def append(self, achievement: Achievement) -> Achievement:
        key = (_scope_key(achievement.scope), achievement.key, achievement.occurrence_id)
        existing = self._records.get(key)
        if existing is not None:
            if existing != achievement:
                raise ExperienceContractError("ACHIEVEMENT_REPLAY_MISMATCH")
            return existing
        self._records[key] = achievement
        return achievement

    def earned(self, scope: ExperienceScope) -> tuple[Achievement, ...]:
        records = [
            achievement
            for achievement in self._records.values()
            if _same_scope(achievement.scope, scope)
        ]
        return tuple(sorted(records, key=lambda item: item.earned_at))


class AchievementEngine:
    """Evaluate experience events into evidence-bound milestones."""

    def __init__(self, projection: AchievementProjectionPort | None = None) -> None:
        self.projection = projection or InMemoryAchievementProjection()
        self._paused: set[tuple[str, ...]] = set()

    def apply(self, event: ExperienceEvent) -> tuple[Achievement, ...]:
        """Return newly earned achievements; repeated events are harmless."""

        key = _scope_key(event.scope)
        candidates: list[AchievementKey] = []
        if event.event_type is ExperienceEventType.ACTION_COMPLETED:
            candidates.append(AchievementKey.FIRST_STEP)
        if event.event_type is ExperienceEventType.ACTION_PAUSED:
            self._paused.add(key)
        elif event.event_type is ExperienceEventType.ACTION_RESUMED or (
            event.event_type is ExperienceEventType.ACTION_STARTED and key in self._paused
        ):
            self._paused.discard(key)
            candidates.append(AchievementKey.PAUSE_AND_RETURN)
        if event.event_type is ExperienceEventType.SERVICE_INTENT_DECLARED:
            candidates.append(AchievementKey.SERVICE_INTENT_EXPRESSED)

        earned: list[Achievement] = []
        existing = {
            (item.key, item.occurrence_id) for item in self.projection.earned(event.scope)
        }
        for achievement_key in candidates:
            occurrence_id = "default"
            if (achievement_key, occurrence_id) in existing:
                continue
            achievement = _build_achievement(event, achievement_key)
            earned.append(self.projection.append(achievement))
            existing.add((achievement_key, occurrence_id))
        return tuple(earned)

    async def apply_async(self, event: ExperienceEvent) -> tuple[Achievement, ...]:
        """Async composition path for durable or in-memory projections.

        The synchronous ``apply`` API remains the compatibility path used by
        existing local callers.  This method deliberately accepts either
        implementation shape exposed by :class:`AchievementProjectionPort` so
        a process-local test projection and a SQLAlchemy adapter exercise the
        same milestone rules.
        """

        key = _scope_key(event.scope)
        candidates: list[AchievementKey] = []
        if event.event_type is ExperienceEventType.ACTION_COMPLETED:
            candidates.append(AchievementKey.FIRST_STEP)
        if event.event_type is ExperienceEventType.ACTION_PAUSED:
            self._paused.add(key)
        elif event.event_type is ExperienceEventType.ACTION_RESUMED or (
            event.event_type is ExperienceEventType.ACTION_STARTED and key in self._paused
        ):
            self._paused.discard(key)
            candidates.append(AchievementKey.PAUSE_AND_RETURN)
        if event.event_type is ExperienceEventType.SERVICE_INTENT_DECLARED:
            candidates.append(AchievementKey.SERVICE_INTENT_EXPRESSED)

        earned: list[Achievement] = []
        existing = {
            (item.key, item.occurrence_id)
            for item in await _resolve_projection(self.projection.earned(event.scope))
        }
        for achievement_key in candidates:
            occurrence_id = "default"
            if (achievement_key, occurrence_id) in existing:
                continue
            achievement = _build_achievement(event, achievement_key)
            persisted = await _resolve_projection(self.projection.append(achievement))
            earned.append(persisted)
            existing.add((achievement_key, occurrence_id))
        return tuple(earned)


async def _resolve_projection[T](value: T | Awaitable[T]) -> T:
    """Resolve sync/async projection adapters without blocking the loop."""

    if inspect.isawaitable(value):
        return await value
    return value


def _build_achievement(event: ExperienceEvent, key: AchievementKey) -> Achievement:
    copy = {
        AchievementKey.FIRST_STEP: (
            "第一步已完成",
            "我们已经完成了一个自己选择的小行动。",
        ),
        AchievementKey.PAUSE_AND_RETURN: (
            "按自己的节奏回来",
            "暂停不是退步，今天我们又回到了自己的节奏。",
        ),
        AchievementKey.SERVICE_INTENT_EXPRESSED: (
            "把需要说出来",
            "家庭已经主动表达了需要，下一步可以慢慢了解支持。",
        ),
    }[key]
    scope_token = hashlib.sha256("|".join(_scope_key(event.scope)).encode("utf-8")).hexdigest()[:16]
    return Achievement(
        achievement_id=f"achievement:{event.scope.family_id}:{key.value}:{scope_token}",
        key=key,
        title=copy[0],
        message=copy[1],
        scope=event.scope,
        evidence_refs=(f"experience-event:{event.event_id}",),
        provenance=event.provenance,
        idempotency_key=IdempotencyKey(
            event.scope.tenant_id,
            f"achievement:{event.scope.family_id}:{key.value}:{scope_token}",
        ),
        earned_at=event.occurred_at,
        basis=(
            "ACTION_COMPLETED"
            if key is AchievementKey.FIRST_STEP
            else "RELATIONSHIP_FEEDBACK"
            if key is AchievementKey.SERVICE_INTENT_EXPRESSED
            else "ACTION_COMPLETED"
        ),
        occurrence_id="default",
    )


def _same_scope(left: ExperienceScope, right: ExperienceScope) -> bool:
    return (
        left.tenant_id == right.tenant_id
        and left.region_id == right.region_id
        and left.family_id == right.family_id
        and frozenset(left.subject_ids) == frozenset(right.subject_ids)
        and left.purpose == right.purpose
        and left.consent_version == right.consent_version
    )


def _scope_key(scope: ExperienceScope) -> tuple[str, ...]:
    return (
        scope.tenant_id,
        scope.region_id,
        scope.family_id,
        *sorted(scope.subject_ids),
        scope.purpose,
        scope.consent_version,
    )


__all__ = [
    "Achievement",
    "AchievementEngine",
    "AchievementKey",
    "AchievementProjectionPort",
    "InMemoryAchievementProjection",
]
