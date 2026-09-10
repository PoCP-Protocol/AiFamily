from types import SimpleNamespace

import pytest

from backend.intelligence.context_engine.family_need_outcome_poller import (
    FamilyNeedOutcomeReflectionPoller,
)
from backend.workflow_worker.family_need_outcome_reflection import (
    FamilyNeedOutcomeReflectionActivity,
    build_family_need_outcome_reflection_activity,
)
from backend.workflow_worker.runtime import WorkflowWorkerRuntime


class Poller(FamilyNeedOutcomeReflectionPoller):
    async def poll_once(self, **kwargs):
        return SimpleNamespace(inspected=2, projected=1)


@pytest.mark.asyncio
async def test_activity_runs_one_bounded_worker_pass():
    activity = FamilyNeedOutcomeReflectionActivity(Poller.__new__(Poller), "t", "f")
    result = await activity.poll_once()
    assert activity.name == "family_need.outcome_reflection"
    assert result.projected == 1
    assert activity.last_report is result


@pytest.mark.asyncio
async def test_activity_implements_workflow_runtime_protocol():
    activity = FamilyNeedOutcomeReflectionActivity(Poller.__new__(Poller), "t", "f")
    execution = await activity.run_once()
    assert execution.succeeded is True
    assert execution.result_type == "SimpleNamespace"
    assert activity.last_report is not None


@pytest.mark.asyncio
async def test_activity_runs_inside_shared_worker_runtime_cycle():
    activity = FamilyNeedOutcomeReflectionActivity(Poller.__new__(Poller), "t", "f")
    runtime = WorkflowWorkerRuntime.from_activities((activity,))
    outcomes = await runtime.run_cycle()
    assert outcomes[0].activity == "family_need.outcome_reflection"
    assert outcomes[0].succeeded is True
    assert runtime.health.cycle_count == 1


@pytest.mark.asyncio
async def test_reflection_failure_is_reported_by_shared_runtime():
    class FailingPoller(Poller):
        async def poll_once(self, **kwargs):
            raise RuntimeError("reflection store unavailable")

    activity = FamilyNeedOutcomeReflectionActivity(FailingPoller.__new__(FailingPoller), "t", "f")
    runtime = WorkflowWorkerRuntime.from_activities((activity,), degraded_after_failed_cycles=1)
    outcomes = await runtime.run_cycle()
    assert outcomes[0].succeeded is False
    assert outcomes[0].error_type == "RuntimeError"


def test_activity_rejects_blank_identity():
    with pytest.raises(ValueError, match="tenant and family"):
        FamilyNeedOutcomeReflectionActivity(Poller.__new__(Poller), "", "f")


def test_factory_validates_batch_limit():
    with pytest.raises(ValueError, match="event limit"):
        build_family_need_outcome_reflection_activity(
            poller=Poller.__new__(Poller), tenant_id="t", family_id="f", limit=0
        )
