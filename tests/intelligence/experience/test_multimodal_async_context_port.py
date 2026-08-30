from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.intelligence.context_engine.async_port import AsyncContextBrokerAdapter
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import MultimodalRouteRequest


def _scope() -> ContextScope:
    return ContextScope(
        tenant_id="tenant-async-context",
        region_id="CN",
        family_id="family-async-context",
        subject_ids=("child-async-context",),
        purpose="family-growth-support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref="delete:async-context",
        correlation_id="corr:async-context",
        causation_id="cause:async-context",
    )


class _RecordingContext:
    durability_mode = "DURABLE"

    def __init__(self) -> None:
        self._delegate = AsyncContextBrokerAdapter(ContextBroker())
        self.events: list[str] = []

    async def snapshot(self, **kwargs):  # type: ignore[no-untyped-def]
        self.events.append("snapshot")
        return await self._delegate.snapshot(**kwargs)

    async def read(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.events.append("read")
        return await self._delegate.read(*args, **kwargs)

    async def append(self, observation) -> None:  # type: ignore[no-untyped-def]
        return await self._delegate.append(observation)

    async def delete_subject(self, tenant_id: str, subject_id: str) -> int:
        return await self._delegate.delete_subject(tenant_id, subject_id)


class _RecordingRouted:
    def __init__(self, context: _RecordingContext) -> None:
        self.context = context

    async def generate_draft(self, command, route_request, *, run=None):  # type: ignore[no-untyped-def]
        assert self.context.events == ["snapshot"]
        return SimpleNamespace(
            run_id=command.run_id,
            output={"status": "DRAFT", "headline": "async context"},
            requires_human_confirmation=True,
            experience=SimpleNamespace(draft_id=None, provenance_ref=None),
        )


def _command() -> ContextBoundMultimodalCommand:
    scope = _scope()
    return ContextBoundMultimodalCommand(
        run_id="run-async-context",
        route_request=MultimodalRouteRequest(
            use_case=scope.purpose,
            data_class=scope.data_class.value,
            modalities=("TEXT",),
            environment="test",
            estimated_input_tokens=16,
        ),
        scope=scope,
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        payload={"message": "hello"},
        output_schema={"type": "object"},
    )


@pytest.mark.asyncio
async def test_context_bound_application_awaits_async_context_port_before_route() -> None:
    context = _RecordingContext()
    service = ContextBoundMultimodalExperienceService(
        context=context, routed=_RecordingRouted(context)  # type: ignore[arg-type]
    )

    result = await service.generate_draft(_command())

    assert result.snapshot.generated_at <= datetime.now(UTC)
    assert result.output["status"] == "DRAFT"
