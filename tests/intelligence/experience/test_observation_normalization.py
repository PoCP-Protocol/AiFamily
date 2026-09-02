from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import MultimodalRouteRequest
from backend.intelligence.experience.observation_normalization import (
    ObservationNormalizationError,
    normalize_observations,
)
from backend.intelligence.model_gateway.contracts import MediaInput


def media(media_type: str, digest: str) -> MediaInput:
    return MediaInput(
        media_type=media_type,  # type: ignore[arg-type]
        uri=f"media:authorized:{digest}",
        mime_type="audio/m4a" if media_type == "AUDIO" else "image/jpeg",
        sha256=digest,
    )


def test_text_voice_and_image_produce_distinct_content_addressed_observations() -> None:
    audio_hash = "a" * 64
    image_hash = "b" * 64
    result = normalize_observations(
        run_id="run-three-modalities",
        modalities=("TEXT", "AUDIO", "IMAGE"),
        payload={
            "expression": "写作业时我们越催越生气。",
            "conversation_turns": [
                {
                    "input_ref": "input:concern-1",
                    "kind": "CONCERN",
                    "text": "写作业时我们越催越生气。",
                    "created_at": "2026-09-03T09:00:00+08:00",
                }
            ],
            "prior_run_id": None,
            "media_observations": {
                audio_hash: {
                    "transcript": "录音里我在反复催促，孩子说题目不会。",
                    "version": "asr-reviewed.v1",
                    "confidence": 0.91,
                    "adult_confirmed": True,
                },
                image_hash: {
                    "ocr_text": "作业本上有多处空题和修改痕迹。",
                    "version": "ocr-reviewed.v1",
                    "confidence": 0.88,
                    "adult_confirmed": True,
                },
            },
        },
        media_inputs=(media("AUDIO", audio_hash), media("IMAGE", image_hash)),
        input_refs=(
            "input:concern-1",
            f"media:authorized:{audio_hash}",
            f"media:authorized:{image_hash}",
        ),
    )

    assert [item.modality for item in result.observations] == ["TEXT", "AUDIO", "IMAGE"]
    assert len({item.observation_ref for item in result.observations}) == 3
    assert result.observations[1].derivation == "TRANSCRIPT"
    assert result.observations[2].derivation == "OCR"
    assert result.observations[0].source_refs == ("input:concern-1",)
    assert result.observations[1].source_refs == (f"media:authorized:{audio_hash}",)
    assert all(item.adult_confirmed for item in result.observations)
    assert result.payload["normalized_observations"]
    assert result.payload["conversation_turns"] == (
        {
            "input_ref": "input:concern-1",
            "kind": "CONCERN",
            "text": "写作业时我们越催越生气。",
            "created_at": "2026-09-03T09:00:00+08:00",
        },
    )
    assert result.payload["prior_run_id"] is None


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (
            {
                "expression": "家庭表达",
                "media_observations": {
                    "a" * 64: {
                        "transcript": "未经成人确认的转写",
                        "version": "asr.v1",
                        "confidence": 0.9,
                        "adult_confirmed": False,
                    }
                },
            },
            "ADULT_CONFIRMATION_REQUIRED",
        ),
        (
            {
                "expression": "家庭表达",
                "media_observations": {
                    "a" * 64: {
                        "transcript": "缺少可信度",
                        "version": "asr.v1",
                        "adult_confirmed": True,
                    }
                },
            },
            "DERIVATION_CONFIDENCE_REQUIRED",
        ),
    ],
)
def test_unconfirmed_or_incomplete_machine_text_fails_closed(
    payload: dict[str, object], reason: str
) -> None:
    with pytest.raises(ObservationNormalizationError) as error:
        normalize_observations(
            run_id="run-invalid-derived",
            modalities=("TEXT", "AUDIO"),
            payload=payload,
            media_inputs=(media("AUDIO", "a" * 64),),
            input_refs=(),
        )
    assert error.value.reason == reason


def test_media_modality_without_matching_authorized_reference_is_rejected() -> None:
    with pytest.raises(ObservationNormalizationError) as error:
        normalize_observations(
            run_id="run-missing-media",
            modalities=("TEXT", "IMAGE"),
            payload={"expression": "家庭表达"},
            media_inputs=(),
            input_refs=(),
        )
    assert error.value.reason == "IMAGE_MEDIA_REQUIRED"


@pytest.mark.parametrize(
    ("turns", "input_refs", "prior_run_id", "reason"),
    [
        (
            [
                {
                    "input_ref": "input:outside-request",
                    "kind": "CONCERN",
                    "text": "家庭表达",
                    "created_at": "2026-09-03T09:00:00+08:00",
                }
            ],
            ("input:allowed",),
            None,
            "CONVERSATION_INPUT_REF_NOT_AUTHORIZED",
        ),
        (
            [
                {
                    "input_ref": "input:allowed",
                    "kind": "ANSWER",
                    "text": "家庭表达",
                    "created_at": "2026-09-03T09:00:00+08:00",
                }
            ],
            ("input:allowed",),
            None,
            "CONVERSATION_KIND_INVALID",
        ),
        (
            [
                {
                    "input_ref": "input:allowed",
                    "kind": "CONCERN",
                    "text": "家庭表达",
                    "created_at": "2026-09-03T09:00:00",
                }
            ],
            ("input:allowed",),
            None,
            "CONVERSATION_CREATED_AT_INVALID",
        ),
        (
            [
                {
                    "input_ref": "input:allowed",
                    "kind": "FOLLOW_UP",
                    "text": "补充回答",
                    "created_at": "2026-09-03T09:00:00+08:00",
                }
            ],
            ("input:allowed",),
            " ",
            "PRIOR_RUN_ID_INVALID",
        ),
        (
            [
                {
                    "input_ref": "input:follow-up-first",
                    "kind": "FOLLOW_UP",
                    "text": "缺少最初关注。",
                    "created_at": "2026-09-03T09:00:00+08:00",
                }
            ],
            ("input:follow-up-first",),
            "run-before",
            "CONVERSATION_SEQUENCE_INVALID",
        ),
        (
            [
                {
                    "input_ref": "input:concern",
                    "kind": "CONCERN",
                    "text": "最初关注。",
                    "created_at": "2026-09-03T09:00:00+08:00",
                },
                {
                    "input_ref": "input:follow-up",
                    "kind": "FOLLOW_UP",
                    "text": "补充回答。",
                    "created_at": "2026-09-03T09:05:00+08:00",
                },
            ],
            ("input:concern", "input:follow-up"),
            None,
            "PRIOR_RUN_ID_REQUIRED",
        ),
    ],
)
def test_invalid_conversation_lineage_fails_before_gateway(
    turns: list[dict[str, str]],
    input_refs: tuple[str, ...],
    prior_run_id: str | None,
    reason: str,
) -> None:
    with pytest.raises(ObservationNormalizationError) as error:
        normalize_observations(
            run_id="run-invalid-lineage",
            modalities=("TEXT",),
            payload={
                "expression": "家庭表达",
                "conversation_turns": turns,
                "prior_run_id": prior_run_id,
            },
            media_inputs=(),
            input_refs=input_refs,
        )
    assert error.value.reason == reason


def test_authorized_media_ref_is_required_for_conversation_bound_media() -> None:
    digest = "c" * 64
    with pytest.raises(ObservationNormalizationError) as error:
        normalize_observations(
            run_id="run-media-ref-mismatch",
            modalities=("TEXT", "IMAGE"),
            payload={
                "expression": "请结合图片理解。",
                "conversation_turns": [
                    {
                        "input_ref": "input:concern-image",
                        "kind": "CONCERN",
                        "text": "请结合图片理解。",
                        "created_at": "2026-09-03T09:00:00+08:00",
                    }
                ],
                "prior_run_id": None,
            },
            media_inputs=(media("IMAGE", digest),),
            input_refs=("input:concern-image",),
        )
    assert error.value.reason == "MEDIA_INPUT_REF_NOT_AUTHORIZED"


def test_same_authorized_media_ref_cannot_bind_to_different_content() -> None:
    first = media("IMAGE", "d" * 64)
    second = MediaInput(
        media_type="IMAGE",
        uri=first.uri,
        mime_type="image/png",
        sha256="e" * 64,
    )
    with pytest.raises(ObservationNormalizationError) as error:
        normalize_observations(
            run_id="run-media-ref-conflict",
            modalities=("TEXT", "IMAGE"),
            payload={
                "expression": "请结合图片理解。",
                "conversation_turns": [
                    {
                        "input_ref": "input:media-conflict",
                        "kind": "CONCERN",
                        "text": "请结合图片理解。",
                        "created_at": "2026-09-03T09:00:00+08:00",
                    }
                ],
                "prior_run_id": None,
            },
            media_inputs=(first, second),
            input_refs=("input:media-conflict", first.uri),
        )
    assert error.value.reason == "MEDIA_INPUT_REF_CONFLICT"


class RecordingRouted:
    def __init__(self) -> None:
        self.command = None

    async def generate_draft(self, command, route_request, *, run=None):  # type: ignore[no-untyped-def]
        self.command = command
        return SimpleNamespace(
            run_id=command.run_id,
            output={"status": "DRAFT"},
            requires_human_confirmation=True,
            experience=SimpleNamespace(draft_id=None, provenance_ref=None),
        )


def scope() -> ContextScope:
    return ContextScope(
        tenant_id="tenant-observation",
        region_id="CN",
        family_id="family-observation",
        subject_ids=("guardian-observation",),
        purpose="family-growth-support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref="delete:observation",
        correlation_id="corr:observation",
        causation_id="cause:observation",
    )


@pytest.mark.asyncio
async def test_existing_context_runtime_sends_only_server_normalized_payload_to_gateway() -> None:
    current_scope = scope()
    routed = RecordingRouted()
    service = ContextBoundMultimodalExperienceService(
        context=ContextBroker(),
        routed=routed,  # type: ignore[arg-type]
    )
    command = ContextBoundMultimodalCommand(
        run_id="run-normalized-runtime",
        route_request=MultimodalRouteRequest(
            use_case=current_scope.purpose,
            data_class=current_scope.data_class.value,
            modalities=("TEXT",),
            environment="test",
            estimated_input_tokens=32,
        ),
        scope=current_scope,
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        payload={
            "expression": "写作业时我们越催越生气。",
            "conversation_turns": [
                {
                    "input_ref": "input:runtime-concern",
                    "kind": "CONCERN",
                    "text": "写作业时我们越催越生气。",
                    "created_at": "2026-09-03T09:00:00+08:00",
                },
                {
                    "input_ref": "input:runtime-follow-up",
                    "kind": "FOLLOW_UP",
                    "text": "上周日先散步再商量时，沟通顺利很多。",
                    "created_at": "2026-09-03T09:05:00+08:00",
                }
            ],
            "prior_run_id": "run-before-correction",
            "client_fact": "不要信任",
        },
        output_schema={"type": "object"},
        input_refs=("input:runtime-concern", "input:runtime-follow-up"),
    )

    result = await service.generate_draft(command)

    assert routed.command.payload["normalized_observations"] == tuple(
        item.to_gateway_value() for item in result.normalized_observations
    )
    assert routed.command.payload["conversation_turns"] == (
        {
            "input_ref": "input:runtime-concern",
            "kind": "CONCERN",
            "text": "写作业时我们越催越生气。",
            "created_at": "2026-09-03T09:00:00+08:00",
        },
        {
            "input_ref": "input:runtime-follow-up",
            "kind": "FOLLOW_UP",
            "text": "上周日先散步再商量时，沟通顺利很多。",
            "created_at": "2026-09-03T09:05:00+08:00",
        },
    )
    assert routed.command.payload["prior_run_id"] == "run-before-correction"
    assert "client_fact" not in routed.command.payload
    assert routed.command.input_refs[0] == "input:runtime-concern"
    assert any(
        ref.startswith("normalized-observation:v1:sha256:")
        for ref in routed.command.input_refs
    )


@pytest.mark.asyncio
async def test_normalized_observation_changes_when_adult_correction_changes() -> None:
    current_scope = scope()
    routed = RecordingRouted()
    service = ContextBoundMultimodalExperienceService(
        context=ContextBroker(),
        routed=routed,  # type: ignore[arg-type]
    )
    base = ContextBoundMultimodalCommand(
        run_id="run-correction",
        route_request=MultimodalRouteRequest(
            use_case=current_scope.purpose,
            data_class=current_scope.data_class.value,
            modalities=("TEXT",),
            environment="test",
            estimated_input_tokens=32,
        ),
        scope=current_scope,
        prompt_version="prompt.v1",
        schema_version="schema.v1",
        payload={"expression": "主要是孩子不配合。"},
        output_schema={"type": "object"},
    )
    first = await service.generate_draft(base)
    corrected = await service.generate_draft(
        replace(
            base,
            run_id="run-correction-v2",
            payload={"expression": "补充：孩子是遇到不会的题才发脾气。"},
        )
    )

    assert (
        first.normalized_observations[0].observation_ref
        != corrected.normalized_observations[0].observation_ref
    )
