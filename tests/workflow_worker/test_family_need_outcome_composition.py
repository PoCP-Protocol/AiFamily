import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from backend.intelligence.context_engine.async_port import AsyncContextBrokerAdapter
from backend.intelligence.context_engine.family_need_outcome_poller import (
    FamilyNeedOutcomeReflectionPoller,
)
from backend.intelligence.context_engine.outcome_reflection import OutcomeReflectionContextWriter
from backend.intelligence.context_engine.store import ContextBroker
from backend.workflow_worker.family_need_outcome_composition import (
    add_family_need_outcome_reflection_activity,
    add_sql_family_need_outcome_reflection_activity,
)
from backend.workflow_worker.runtime import WorkflowWorkerRuntime


class Poller(FamilyNeedOutcomeReflectionPoller):
    pass


def test_composition_adds_explicitly_scoped_activity_without_mutating_runtime():
    runtime = WorkflowWorkerRuntime.from_activities(
        (type("Existing", (), {"name": "existing", "run_once": None})(),)
    )
    poller = Poller.__new__(Poller)
    updated = add_family_need_outcome_reflection_activity(
        runtime, poller=poller, tenant_id="t", family_id="f"
    )
    assert [item.name for item in runtime.activities] == ["existing"]
    assert [item.name for item in updated.activities] == [
        "existing",
        "family_need.outcome_reflection",
    ]


def test_composition_rejects_invalid_runtime():
    with pytest.raises(TypeError, match="WorkflowWorkerRuntime"):
        add_family_need_outcome_reflection_activity(
            object(), poller=Poller.__new__(Poller), tenant_id="t", family_id="f"
        )


@pytest.mark.asyncio
async def test_sql_composition_builds_session_per_operation_reader():
    class DurableBroker(ContextBroker):
        durability_mode = "DURABLE"

    class ScopeResolver:
        async def resolve(self, *, tenant_id: str, family_id: str):
            raise AssertionError("scope resolution belongs to activity execution")

    runtime = WorkflowWorkerRuntime.from_activities(
        (type("Existing", (), {"name": "existing", "run_once": None})(),)
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    updated = add_sql_family_need_outcome_reflection_activity(
        runtime,
        engine=engine,
        writer=OutcomeReflectionContextWriter(
            AsyncContextBrokerAdapter(DurableBroker())
        ),
        scope_resolver=ScopeResolver(),
        tenant_id="t",
        family_id="f",
    )

    assert updated.activities[-1].name == "family_need.outcome_reflection"
    await engine.dispose()
