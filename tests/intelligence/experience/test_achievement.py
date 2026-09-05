from __future__ import annotations

import pytest

from backend.intelligence.experience.achievement import (
    AchievementEngine,
    AchievementKey,
)
from backend.intelligence.experience.contracts import (
    ExperienceContractError,
    ExperienceEventType,
)
from tests.intelligence.experience.test_gateway import _event, _scope


def test_completed_action_creates_one_evidence_bound_first_step() -> None:
    engine = AchievementEngine()
    event = _event(event_id="action-completed", event_type=ExperienceEventType.ACTION_COMPLETED)

    first = engine.apply(event)
    replay = engine.apply(event)

    assert tuple(item.key for item in first) == (AchievementKey.FIRST_STEP,)
    assert replay == ()
    assert first[0].evidence_refs == ("experience-event:action-completed",)
    assert len(engine.projection.earned(_scope())) == 1


def test_pause_and_return_is_a_positive_milestone_without_streak_penalty() -> None:
    engine = AchievementEngine()
    engine.apply(_event(event_id="action-paused", event_type=ExperienceEventType.ACTION_PAUSED))
    earned = engine.apply(
        _event(event_id="action-returned", event_type=ExperienceEventType.ACTION_STARTED)
    )

    assert tuple(item.key for item in earned) == (AchievementKey.PAUSE_AND_RETURN,)


def test_explicit_resume_survives_achievement_worker_restart() -> None:
    first_worker = AchievementEngine()
    first_worker.apply(
        _event(event_id="action-paused", event_type=ExperienceEventType.ACTION_PAUSED)
    )

    restarted_worker = AchievementEngine(projection=first_worker.projection)
    earned = restarted_worker.apply(
        _event(event_id="action-resumed", event_type=ExperienceEventType.ACTION_RESUMED)
    )

    assert tuple(item.key for item in earned) == (AchievementKey.PAUSE_AND_RETURN,)


def test_service_intent_is_recorded_without_auto_purchase() -> None:
    engine = AchievementEngine()
    earned = engine.apply(
        _event(
            event_id="service-intent",
            event_type=ExperienceEventType.SERVICE_INTENT_DECLARED,
        )
    )

    assert earned[0].key is AchievementKey.SERVICE_INTENT_EXPRESSED
    assert "购买" not in earned[0].message


def test_projection_is_family_and_consent_scoped() -> None:
    engine = AchievementEngine()
    engine.apply(
        _event(
            event_id="family-a-action",
            event_type=ExperienceEventType.ACTION_COMPLETED,
        )
    )
    other = _scope(family_id="family-b")

    assert engine.projection.earned(other) == ()


def test_achievement_rejects_missing_evidence() -> None:
    event = _event(event_id="invalid-achievement")
    from backend.intelligence.experience.achievement import Achievement

    with pytest.raises(ExperienceContractError, match="EVIDENCE_REQUIRED"):
        Achievement(
            achievement_id="achievement-invalid",
            key=AchievementKey.FIRST_STEP,
            title="第一步",
            message="完成了一步",
            scope=event.scope,
            evidence_refs=(),
            provenance=event.provenance,
            idempotency_key=event.idempotency_key,
        )
