from __future__ import annotations

from dataclasses import replace

import pytest

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import MultimodalExperienceService
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
    MultimodalRouteRequest,
)
from backend.intelligence.experience.runs import DurableExperienceRun, RunEventType, RunState
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.model_gateway.test_fail_closed import build


def _scope() -> ContextScope:
    return ContextScope(
        tenant_id="tenant-lifecycle",
        region_id="CN",
        family_id="family-lifecycle",
        subject_ids=("guardian-lifecycle", "child-lifecycle"),
        purpose="family-image-summary",
        consent_version="consent-lifecycle-v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref="delete:family-lifecycle",
        correlation_id="corr:lifecycle-001",
        causation_id="cause:lifecycle-001",
    )


def _command(scope: ContextScope) -> ContextBoundMultimodalCommand:
    return ContextBoundMultimodalCommand(
        run_id="run-lifecycle-001",
        route_request=MultimodalRouteRequest(
            use_case=scope.purpose,
            data_class=scope.data_class.value,
            modalities=("TEXT", "IMAGE"),
            environment="test",
            estimated_input_tokens=100,
        ),
        scope=scope,
        prompt_version="prompt.lifecycle.v1",
        schema_version="schema.lifecycle.v1",
        payload={"media_ref": "fixture:image-lifecycle"},
        output_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
    )


def _service(provider: FakeProvider) -> ContextBoundMultimodalExperienceService:
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id="fake-deterministic",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
    )
    routed = RoutedMultimodalExperienceService(
        router=MultimodalRouter((profile,)),
        generation=MultimodalExperienceService(build(provider)),
    )
    return ContextBoundMultimodalExperienceService(context=ContextBroker(), routed=routed)


def _run(scope: ContextScope) -> DurableExperienceRun:
    return DurableExperienceRun(
        run_id="run-lifecycle-001",
        tenant_id=scope.tenant_id,
        family_id=scope.family_id,
        subject_ids=scope.subject_ids,
        request_ref="request:lifecycle-001",
    )


@pytest.mark.asyncio
async def test_context_gateway_draft_marks_run_succeeded() -> None:
    scope = _scope()
    run = _run(scope)
    result = await _service(FakeProvider({scope.purpose: {"summary": "draft"}})).generate_draft(
        _command(scope), run=run
    )

    assert result.output["summary"] == "draft"
    assert run.state is RunState.SUCCEEDED
    assert [event.event_type for event in run.events] == [
        RunEventType.STARTED,
        RunEventType.CHECKPOINTED,
        RunEventType.SUCCEEDED,
    ]
    assert run.latest_checkpoint is not None
    assert run.latest_checkpoint.status == "DRAFT"


@pytest.mark.asyncio
async def test_context_gateway_failure_marks_run_failed() -> None:
    scope = _scope()
    run = _run(scope)
    provider = FakeProvider(
        {scope.purpose: {"summary": "never returned"}}, fail_with="PROVIDER_5XX"
    )

    with pytest.raises(ModelGatewayError):
        await _service(provider).generate_draft(_command(scope), run=run)

    assert run.state is RunState.FAILED
    assert [event.event_type for event in run.events] == [
        RunEventType.STARTED,
        RunEventType.FAILED,
    ]
    assert run.latest_checkpoint is None


@pytest.mark.asyncio
async def test_context_run_scope_mismatch_is_rejected_before_snapshot() -> None:
    scope = _scope()
    run = DurableExperienceRun(
        run_id="run-lifecycle-001",
        tenant_id=scope.tenant_id,
        family_id="different-family",
        subject_ids=scope.subject_ids,
        request_ref="request:lifecycle-001",
    )

    with pytest.raises(ValueError, match="run scope"):
        await _service(FakeProvider({scope.purpose: {"summary": "blocked"}})).generate_draft(
            _command(scope), run=run
        )
    assert run.state is RunState.QUEUED
