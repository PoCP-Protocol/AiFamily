from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.intelligence.context_engine.contracts import (
    ContextScope,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.sql_store import (
    AsyncSqlContextBroker,
    ContextPersistenceBase,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import MultimodalRouteRequest

NOW = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)


def _scope() -> ContextScope:
    return ContextScope(
        tenant_id="tenant-sql-experience",
        region_id="CN",
        family_id="family-sql-experience",
        subject_ids=("child-sql-experience",),
        purpose="family-growth-support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=DataClass.OPERATIONAL_TEXT,
        locale="zh-CN",
        deletion_ref="delete:sql-experience",
        correlation_id="corr:sql-experience",
        causation_id="cause:sql-experience",
    )


def _observation(scope: ContextScope) -> StateObservation:
    return StateObservation(
        observation_id="observation-sql-experience",
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        subject_id=scope.subject_ids[0],
        dimension="expression",
        observed_value="calm",
        evidence_refs=("evidence:sql-experience",),
        provenance="test",
        observed_at=NOW,
        data_class=scope.data_class,
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        consent_granted=True,
        region_id=scope.region_id,
        locale=scope.locale,
        deletion_ref=scope.deletion_ref,
        correlation_id=scope.correlation_id,
        causation_id=scope.causation_id,
        expires_at=NOW + timedelta(hours=1),
        retention_policy="test-1h",
    )


def _command(scope: ContextScope) -> ContextBoundMultimodalCommand:
    return ContextBoundMultimodalCommand(
        run_id="run-sql-context",
        route_request=MultimodalRouteRequest(
            use_case=scope.purpose,
            data_class=scope.data_class.value,
            modalities=("TEXT",),
            environment="staging",
            estimated_input_tokens=16,
        ),
        scope=scope,
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        payload={"message": "hello"},
        output_schema={"type": "object"},
    )


class _RecordingRouted:
    def __init__(self) -> None:
        self.context_snapshot_ref: str | None = None

    async def generate_draft(self, command, route_request, *, run=None):  # type: ignore[no-untyped-def]
        self.context_snapshot_ref = command.context_snapshot_ref
        return SimpleNamespace(
            run_id=command.run_id,
            output={"status": "DRAFT", "headline": "sql context"},
            requires_human_confirmation=True,
            experience=SimpleNamespace(draft_id=None, provenance_ref=None),
        )


@pytest.mark.asyncio
async def test_multimodal_application_uses_durable_sql_context_before_route(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'context.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(ContextPersistenceBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        scope = _scope()
        context = AsyncSqlContextBroker(session_factory)
        await context.append(_observation(scope))
        routed = _RecordingRouted()
        service = ContextBoundMultimodalExperienceService(
            context=context,
            routed=routed,
            clock=lambda: NOW,
        )  # type: ignore[arg-type]

        result = await service.generate_draft(_command(scope))

        assert result.output["status"] == "DRAFT"
        assert result.snapshot.observations[0].observation_id == "observation-sql-experience"
        assert routed.context_snapshot_ref == result.snapshot.snapshot_ref
    finally:
        await engine.dispose()
