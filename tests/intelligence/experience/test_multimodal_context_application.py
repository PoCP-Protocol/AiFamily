from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.context_engine.contracts import (
    ContextScope,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import (
    MultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
    MultimodalRouteRequest,
)
from backend.intelligence.experience.run_http import FeedbackPreferenceSnapshot, RunScope
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.model_gateway.test_fail_closed import build

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def _scope() -> ContextScope:
    return ContextScope(
        tenant_id="tenant-a",
        region_id="CN",
        family_id="family-a",
        subject_ids=("guardian-a", "child-a"),
        purpose="family-image-summary",
        consent_version="consent-v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref="delete:family-a",
        correlation_id="corr:context-001",
        causation_id="cause:context-001",
    )


def _command(**overrides: object) -> ContextBoundMultimodalCommand:
    scope = _scope()
    values: dict[str, object] = {
        "run_id": "run-context-001",
        "route_request": MultimodalRouteRequest(
            use_case="family-image-summary",
            data_class="SYNTHETIC",
            modalities=("TEXT", "IMAGE"),
            environment="test",
            estimated_input_tokens=500,
        ),
        "scope": scope,
        "prompt_version": "prompt.v1",
        "schema_version": "schema.v1",
        "payload": {"media_ref": "fixture:image-001"},
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
    }
    values.update(overrides)
    return ContextBoundMultimodalCommand(**values)  # type: ignore[arg-type]


def _service_with_provider(
    *, context: ContextBroker | None = None
) -> tuple[ContextBoundMultimodalExperienceService, FakeProvider]:
    provider = FakeProvider({"family-image-summary": {"summary": "基于授权上下文生成的草案"}})
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
    return (
        ContextBoundMultimodalExperienceService(
            context=context or ContextBroker(),
            routed=routed,
            clock=lambda: NOW,
        ),
        provider,
    )


def _service(*, context: ContextBroker | None = None) -> ContextBoundMultimodalExperienceService:
    return _service_with_provider(context=context)[0]


def _feedback_preferences() -> FeedbackPreferenceSnapshot:
    scope = _scope()
    return FeedbackPreferenceSnapshot(
        scope=RunScope(
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            subject_ids=scope.subject_ids,
        ),
        helpful_count=2,
        not_helpful_count=1,
        request_human_count=0,
    )


def _observation() -> StateObservation:
    observed_at = datetime(2026, 8, 30, tzinfo=UTC)
    return StateObservation(
        observation_id="observation-001",
        tenant_id="tenant-a",
        family_id="family-a",
        subject_id="guardian-a",
        dimension="family_expression",
        observed_value="synthetic image reference",
        evidence_refs=("evidence:image-001",),
        provenance="synthetic-fixture",
        observed_at=observed_at,
        expires_at=observed_at + timedelta(days=1),
        data_class=DataClass.SYNTHETIC,
        purpose="family-image-summary",
        consent_version="consent-v1",
        consent_granted=True,
        deletion_ref="delete:family-a",
        correlation_id="corr:context-001",
        causation_id="cause:context-001",
        retention_policy="synthetic-test",
    )


@pytest.mark.asyncio
async def test_context_is_created_before_routed_gateway_draft() -> None:
    context = ContextBroker()
    context.append(_observation())

    result = await _service(context=context).generate_draft(
        _command(input_refs=("evidence:image-001",))
    )

    assert result.snapshot.scope.family_id == "family-a"
    assert result.snapshot.source_refs == ("evidence:image-001",)
    assert result.routed.route.provenance_input.use_case == "family-image-summary"
    assert result.output["summary"] == "基于授权上下文生成的草案"
    assert result.requires_human_confirmation is True


@pytest.mark.asyncio
async def test_feedback_preferences_are_added_as_server_owned_prompt_context() -> None:
    service, provider = _service_with_provider()
    await service.generate_draft(
        _command(
            feedback_preferences=_feedback_preferences(),
            payload={"media_ref": "fixture:image-001", "experience_feedback": "forged"},
        )
    )

    request = provider.invocations[-1]
    assert request.payload["experience_feedback"] == {
        "signal_counts": {"helpful": 2, "not_helpful": 1, "request_human": 0},
        "sample_size": 3,
    }


def test_context_command_rejects_purpose_or_data_class_drift() -> None:
    with pytest.raises(ValueError, match="use_case"):
        _command(
            route_request=MultimodalRouteRequest(
                use_case="different-purpose",
                data_class="SYNTHETIC",
                modalities=("TEXT",),
                environment="test",
                estimated_input_tokens=10,
            )
        )

    with pytest.raises(ValueError, match="data_class"):
        _command(
            route_request=MultimodalRouteRequest(
                use_case="family-image-summary",
                data_class="OPERATIONAL_TEXT",
                modalities=("TEXT",),
                environment="test",
                estimated_input_tokens=10,
            )
        )
