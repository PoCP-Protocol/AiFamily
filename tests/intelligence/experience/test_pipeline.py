from __future__ import annotations

import pytest

from backend.intelligence.experience.achievement import AchievementEngine
from backend.intelligence.experience.contracts import ExperienceContractError, ExperienceEventType
from backend.intelligence.experience.experiments import (
    ExperimentAllocator,
    ExperimentDefinition,
    ExperimentStatus,
)
from backend.intelligence.experience.features import FeatureKind, FeaturePurpose
from backend.intelligence.experience.pipeline import (
    ExperiencePipeline,
    InMemoryExperienceOutbox,
)
from backend.platform.idempotency.keys import IdempotencyKey
from tests.intelligence.experience.test_features_experiments import _scope, _signal
from tests.intelligence.experience.test_gateway import _event


def test_pipeline_ingests_features_events_and_assignments_then_projects_them() -> None:
    pipeline = ExperiencePipeline()
    scope = _scope()
    feature = _signal(
        "duration-session",
        FeatureKind.VIEW_DURATION_SECONDS,
        "42",
        purpose=FeaturePurpose.UX_OPTIMIZATION,
        scope=scope,
    )
    event = _event(event_id="entry-001", scope=scope)
    assignment = ExperimentAllocator().assign(
        ExperimentDefinition(
            experiment_id="exp-home",
            version="1",
            variants=("control", "guided"),
            purpose="ux_optimization",
            status=ExperimentStatus.RUNNING,
        ),
        scope,
    )
    assert assignment is not None

    pipeline.ingest(feature)
    pipeline.ingest(event)
    pipeline.ingest(assignment)
    assert len(pipeline.outbox.pending()) == 3
    assert pipeline.publish() == 3
    assert pipeline.outbox.pending() == ()
    assert pipeline.projection.feature_total(scope, FeatureKind.VIEW_DURATION_SECONDS) == 42
    assert pipeline.projection.event_count(scope, ExperienceEventType.CONTENT_SHOWN) == 1
    assert pipeline.projection.assignment("exp-home", scope) is assignment


def test_outbox_replay_is_idempotent_and_conflicts_are_rejected() -> None:
    outbox = InMemoryExperienceOutbox()
    event = _event(event_id="entry-replay")
    first = outbox.append(event)
    assert outbox.append(event) is first

    conflicting = _event(event_id="entry-other")
    conflicting = type(event)(
        event_id=conflicting.event_id,
        event_type=ExperienceEventType.ACTION_STARTED,
        node=conflicting.node,
        scope=conflicting.scope,
        idempotency_key=IdempotencyKey(event.scope.tenant_id, event.event_id),
        provenance=conflicting.provenance,
        actor_id=conflicting.actor_id,
    )
    with pytest.raises(ExperienceContractError, match="IDEMPOTENCY_REPLAY_MISMATCH"):
        outbox.append(conflicting)


def test_failed_projection_leaves_message_pending_for_retry() -> None:
    outbox = InMemoryExperienceOutbox()
    outbox.append(
        _signal(
            "duration-failure",
            FeatureKind.VIEW_DURATION_SECONDS,
            "7",
            purpose=FeaturePurpose.UX_OPTIMIZATION,
        )
    )

    class FailingProjection:
        def apply(self, _message: object) -> None:
            raise RuntimeError("projection unavailable")

    with pytest.raises(RuntimeError, match="projection unavailable"):
        outbox.publish_next(FailingProjection())  # type: ignore[arg-type]
    assert len(outbox.pending()) == 1


def test_projection_is_replay_safe_and_scope_isolated() -> None:
    pipeline = ExperiencePipeline()
    scope = _scope()
    other_scope = _scope(tenant_id="tenant-b", family_id="family-b")
    message = pipeline.ingest(
        _signal(
            "duration-isolated",
            FeatureKind.VIEW_DURATION_SECONDS,
            "9",
            purpose=FeaturePurpose.UX_OPTIMIZATION,
            scope=scope,
        )
    )
    pipeline.projection.apply(message)
    pipeline.projection.apply(message)
    assert pipeline.projection.feature_total(scope, FeatureKind.VIEW_DURATION_SECONDS) == 9
    assert pipeline.projection.feature_total(other_scope, FeatureKind.VIEW_DURATION_SECONDS) is None


def test_achievement_flows_through_outbox_and_projection_once() -> None:
    pipeline = ExperiencePipeline()
    event = _event(
        event_id="action-achievement",
        event_type=ExperienceEventType.ACTION_COMPLETED,
    )
    achievement = AchievementEngine().apply(event)[0]

    message = pipeline.ingest(achievement)
    pipeline.ingest(achievement)
    assert message.event_type == "experience.achievement.first_step"
    assert pipeline.publish() == 1
    pipeline.projection.apply(message)
    assert pipeline.projection.achievements(event.scope) == (achievement,)
