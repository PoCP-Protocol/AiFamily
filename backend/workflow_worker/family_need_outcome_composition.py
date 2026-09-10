"""Explicit composition helper for the FamilyNeed reflection activity."""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncEngine

from backend.intelligence.context_engine.family_need_outcome_poller import (
    FamilyNeedOutcomeReflectionPoller,
)
from backend.intelligence.context_engine.outcome_reflection import (
    OutcomeReflectionContextWriter,
)
from backend.workflow_worker.family_need_event_reader import SqlAlchemyFamilyNeedEventReader
from backend.workflow_worker.family_need_outcome_reflection import (
    FamilyNeedOutcomeReflectionActivity,
)
from backend.workflow_worker.runtime import WorkflowWorkerRuntime


def add_family_need_outcome_reflection_activity(
    runtime: WorkflowWorkerRuntime,
    *,
    poller: FamilyNeedOutcomeReflectionPoller,
    tenant_id: str,
    family_id: str,
    limit: int = 100,
) -> WorkflowWorkerRuntime:
    """Return a runtime with one explicitly scoped reflection activity.

    ``dataclasses.replace`` preserves all existing runtime settings while
    making the addition visible at the composition root.  No database,
    identity, consent, or scheduler is created here.
    """

    if not isinstance(runtime, WorkflowWorkerRuntime):
        raise TypeError("runtime must be a WorkflowWorkerRuntime")
    activity = FamilyNeedOutcomeReflectionActivity(
        poller=poller,
        tenant_id=tenant_id,
        family_id=family_id,
        limit=limit,
    )
    return replace(runtime, activities=(*runtime.activities, activity))


def add_sql_family_need_outcome_reflection_activity(
    runtime: WorkflowWorkerRuntime,
    *,
    engine: AsyncEngine,
    writer: OutcomeReflectionContextWriter,
    scope_resolver: object,
    tenant_id: str,
    family_id: str,
    limit: int = 100,
) -> WorkflowWorkerRuntime:
    """Compose the durable FamilyNeed reflection activity at deployment time.

    The worker creates only the session-per-operation event reader.  The
    caller must provide the durable Context writer and authenticated scope
    resolver; neither can be inferred from worker environment variables.
    """
    if not isinstance(engine, AsyncEngine):
        raise TypeError("engine must be an AsyncEngine")
    if not isinstance(writer, OutcomeReflectionContextWriter):
        raise TypeError("writer must be an OutcomeReflectionContextWriter")
    if not callable(getattr(scope_resolver, "resolve", None)):
        raise TypeError("scope_resolver must expose resolve")
    poller = FamilyNeedOutcomeReflectionPoller(
        SqlAlchemyFamilyNeedEventReader(engine),
        writer,
        scope_resolver,
    )
    return add_family_need_outcome_reflection_activity(
        runtime,
        poller=poller,
        tenant_id=tenant_id,
        family_id=family_id,
        limit=limit,
    )


__all__ = [
    "add_family_need_outcome_reflection_activity",
    "add_sql_family_need_outcome_reflection_activity",
]
