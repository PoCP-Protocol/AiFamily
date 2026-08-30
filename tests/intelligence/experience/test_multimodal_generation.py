from __future__ import annotations

import pytest

from backend.intelligence.experience.multimodal_generation import (
    MultimodalExperienceCommand,
    MultimodalExperienceDraft,
    MultimodalExperienceService,
)
from backend.intelligence.model_gateway.contracts import MediaInput
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.model_gateway.test_fail_closed import VALID_OUTPUT, build


def _command(**overrides: object) -> MultimodalExperienceCommand:
    values: dict[str, object] = {
        "run_id": "run-image-001",
        "provider_id": "fake-deterministic",
        "use_case": "family-image-summary",
        "prompt_version": "v1",
        "schema_version": "s1",
        "data_class": "SYNTHETIC",
        "context_snapshot_ref": "ctx-image-001",
        "payload": {"scene": "homework"},
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
            "additionalProperties": False,
        },
        "media_inputs": (
            MediaInput(
                media_type="IMAGE",
                uri="https://assets.invalid/image-001",
                mime_type="image/png",
                sha256="a" * 64,
            ),
        ),
    }
    values.update(overrides)
    return MultimodalExperienceCommand(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_service_forwards_image_to_gateway_and_returns_draft() -> None:
    provider = FakeProvider(
        {"family-image-summary": {"summary": "观察到一张家庭场景图片"}}
    )
    service = MultimodalExperienceService(build(provider))

    result = await service.generate_draft(_command())

    assert isinstance(result, MultimodalExperienceDraft)
    assert result.run_id == "run-image-001"
    assert result.output["summary"] == "观察到一张家庭场景图片"
    assert result.requires_human_confirmation is True
    assert result.draft.may_mutate_business_state is False
    assert provider.invocations[0].request_id == "run-image-001"
    assert provider.invocations[0].media_inputs[0].media_type == "IMAGE"


def test_command_rejects_duplicate_input_refs() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        _command(input_refs=("evidence-1", "evidence-1"))


def test_command_requires_structured_output_schema() -> None:
    with pytest.raises(ValueError, match="output_schema"):
        _command(output_schema={})


@pytest.mark.asyncio
async def test_service_preserves_gateway_fail_closed_policy() -> None:
    provider = FakeProvider({"family-image-summary": VALID_OUTPUT})
    service = MultimodalExperienceService(build(provider))

    with pytest.raises(Exception, match="POLICY_REJECTED"):
        await service.generate_draft(
            _command(
                provider_id="openai-compatible-unassessed",
                data_class="MINOR_PERSONAL_DATA",
            )
        )
    assert provider.invocations == []
