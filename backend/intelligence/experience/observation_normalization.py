"""Server-side normalization for governed multimodal experience inputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from backend.intelligence.model_gateway.contracts import MediaInput

ObservationModality = Literal["TEXT", "AUDIO", "IMAGE", "VIDEO"]
_TEXT_KEYS = ("expression", "message", "text", "guardian_text")
_DERIVED_KEYS = {"AUDIO": "transcript", "IMAGE": "ocr_text", "VIDEO": "transcript"}
_CONVERSATION_TURN_FIELDS = frozenset({"input_ref", "kind", "text", "created_at"})


class ObservationNormalizationError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    observation_ref: str
    modality: ObservationModality
    source_refs: tuple[str, ...]
    normalized_text: str | None
    derivation: Literal["GUARDIAN_TEXT", "TRANSCRIPT", "OCR", "MEDIA_REFERENCE"]
    derivation_version: str
    confidence: float | None
    adult_confirmed: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.observation_ref.strip() or not self.source_refs:
            raise ValueError("normalized observation requires identity and source refs")
        if any(not ref.strip() for ref in self.source_refs):
            raise ValueError("normalized observation source refs cannot be blank")
        if self.normalized_text is not None and not self.normalized_text.strip():
            raise ValueError("normalized observation text cannot be blank")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("normalized observation confidence must be within [0, 1]")
        if not self.derivation_version.strip() or not self.limitations:
            raise ValueError("normalization version and limitations are required")

    def to_gateway_value(self) -> dict[str, object]:
        return {
            "observation_ref": self.observation_ref,
            "modality": self.modality,
            "source_refs": self.source_refs,
            "normalized_text": self.normalized_text,
            "derivation": self.derivation,
            "derivation_version": self.derivation_version,
            "confidence": self.confidence,
            "adult_confirmed": self.adult_confirmed,
            "limitations": self.limitations,
        }


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    observations: tuple[NormalizedObservation, ...]
    payload: dict[str, object]
    input_refs: tuple[str, ...]


def normalize_observations(
    *,
    run_id: str,
    modalities: tuple[str, ...],
    payload: dict[str, Any],
    media_inputs: tuple[MediaInput, ...],
    input_refs: tuple[str, ...],
) -> NormalizationResult:
    """Create a bounded model payload without trusting client provenance fields."""

    if not run_id.strip():
        raise ObservationNormalizationError("RUN_ID_REQUIRED")
    unknown = set(modalities) - {"TEXT", "AUDIO", "IMAGE", "VIDEO"}
    if unknown:
        raise ObservationNormalizationError("UNSUPPORTED_MODALITY")

    conversation_turns, prior_run_id = _normalize_conversation_lineage(
        payload=payload,
        input_refs=input_refs,
    )
    if conversation_turns:
        _validate_authorized_media_inputs(media_inputs=media_inputs, input_refs=input_refs)

    observations: list[NormalizedObservation] = []
    if "TEXT" in modalities:
        text = _first_text(payload, _TEXT_KEYS)
        if text is None:
            raise ObservationNormalizationError("TEXT_OBSERVATION_REQUIRED")
        observations.append(
            _observation(
                run_id=run_id,
                modality="TEXT",
                source_refs=(
                    tuple(turn["input_ref"] for turn in conversation_turns)
                    if conversation_turns
                    else (f"guardian-expression:{run_id}",)
                ),
                normalized_text=text,
                derivation="GUARDIAN_TEXT",
                derivation_version="guardian-text.v1",
                confidence=1.0,
                adult_confirmed=True,
                limitations=("Adult-authored expression; not a verified family fact.",),
            )
        )

    for modality in ("AUDIO", "IMAGE", "VIDEO"):
        if modality not in modalities:
            continue
        matching = tuple(media for media in media_inputs if media.media_type == modality)
        if not matching:
            raise ObservationNormalizationError(f"{modality}_MEDIA_REQUIRED")
        for media in matching:
            derived = _derived_value(payload, media.sha256, modality)
            source_ref = _media_source_ref(
                media=media,
                input_refs=input_refs,
                require_authorized_ref=bool(conversation_turns),
            )
            observations.append(
                _observation(
                    run_id=run_id,
                    modality=modality,  # type: ignore[arg-type]
                    source_refs=(source_ref,),
                    normalized_text=derived[0],
                    derivation=derived[1],
                    derivation_version=derived[2],
                    confidence=derived[3],
                    adult_confirmed=derived[4],
                    limitations=derived[5],
                )
            )

    if not observations:
        raise ObservationNormalizationError("OBSERVATION_REQUIRED")
    normalized_refs = tuple(item.observation_ref for item in observations)
    gateway_payload: dict[str, object] = {
        "normalized_observations": tuple(item.to_gateway_value() for item in observations)
    }
    if conversation_turns:
        gateway_payload["conversation_turns"] = conversation_turns
        gateway_payload["prior_run_id"] = prior_run_id
    return NormalizationResult(
        observations=tuple(observations),
        payload=gateway_payload,
        input_refs=tuple(dict.fromkeys((*input_refs, *normalized_refs))),
    )


def _normalize_conversation_lineage(
    *,
    payload: dict[str, Any],
    input_refs: tuple[str, ...],
) -> tuple[tuple[dict[str, str], ...], str | None]:
    raw_turns = payload.get("conversation_turns")
    raw_prior_run_id = payload.get("prior_run_id")
    if raw_turns is None:
        if raw_prior_run_id is not None:
            raise ObservationNormalizationError("PRIOR_RUN_WITHOUT_CONVERSATION")
        return (), None
    if not isinstance(raw_turns, (list, tuple)) or not raw_turns:
        raise ObservationNormalizationError("CONVERSATION_TURNS_REQUIRED")

    allowed_refs = set(input_refs)
    seen_refs: set[str] = set()
    turns: list[dict[str, str]] = []
    for raw_turn in raw_turns:
        if not isinstance(raw_turn, dict) or set(raw_turn) != _CONVERSATION_TURN_FIELDS:
            raise ObservationNormalizationError("CONVERSATION_TURN_INVALID")
        input_ref = raw_turn.get("input_ref")
        kind = raw_turn.get("kind")
        text = raw_turn.get("text")
        created_at = raw_turn.get("created_at")
        if not isinstance(input_ref, str) or not input_ref.strip():
            raise ObservationNormalizationError("CONVERSATION_INPUT_REF_REQUIRED")
        input_ref = input_ref.strip()
        if input_ref not in allowed_refs:
            raise ObservationNormalizationError("CONVERSATION_INPUT_REF_NOT_AUTHORIZED")
        if input_ref in seen_refs:
            raise ObservationNormalizationError("CONVERSATION_INPUT_REF_DUPLICATE")
        if kind not in {"CONCERN", "CORRECTION", "FOLLOW_UP"}:
            raise ObservationNormalizationError("CONVERSATION_KIND_INVALID")
        if not isinstance(text, str) or not text.strip():
            raise ObservationNormalizationError("CONVERSATION_TEXT_REQUIRED")
        if not isinstance(created_at, str) or not _is_timezone_aware_iso8601(created_at):
            raise ObservationNormalizationError("CONVERSATION_CREATED_AT_INVALID")
        seen_refs.add(input_ref)
        turns.append(
            {
                "input_ref": input_ref,
                "kind": kind,
                "text": text.strip(),
                "created_at": created_at.strip(),
            }
        )

    if raw_prior_run_id is None:
        prior_run_id = None
    elif not isinstance(raw_prior_run_id, str) or not raw_prior_run_id.strip():
        raise ObservationNormalizationError("PRIOR_RUN_ID_INVALID")
    else:
        prior_run_id = raw_prior_run_id.strip()
    if turns[0]["kind"] != "CONCERN" or any(
        turn["kind"] == "CONCERN" for turn in turns[1:]
    ):
        raise ObservationNormalizationError("CONVERSATION_SEQUENCE_INVALID")
    if len(turns) > 1 and prior_run_id is None:
        raise ObservationNormalizationError("PRIOR_RUN_ID_REQUIRED")
    return tuple(turns), prior_run_id


def _is_timezone_aware_iso8601(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _media_source_ref(
    *,
    media: MediaInput,
    input_refs: tuple[str, ...],
    require_authorized_ref: bool,
) -> str:
    if media.uri in input_refs:
        return media.uri
    if require_authorized_ref:
        raise ObservationNormalizationError("MEDIA_INPUT_REF_NOT_AUTHORIZED")
    return f"media:sha256:{media.sha256}"


def _validate_authorized_media_inputs(
    *,
    media_inputs: tuple[MediaInput, ...],
    input_refs: tuple[str, ...],
) -> None:
    allowed_refs = set(input_refs)
    bindings: dict[str, tuple[str, str, str]] = {}
    for media in media_inputs:
        if media.uri not in allowed_refs:
            raise ObservationNormalizationError("MEDIA_INPUT_REF_NOT_AUTHORIZED")
        binding = (media.media_type, media.mime_type, media.sha256)
        previous = bindings.get(media.uri)
        if previous is not None:
            reason = (
                "MEDIA_INPUT_REF_DUPLICATE"
                if previous == binding
                else "MEDIA_INPUT_REF_CONFLICT"
            )
            raise ObservationNormalizationError(reason)
        bindings[media.uri] = binding


def _first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _derived_value(
    payload: dict[str, Any], sha256: str, modality: str
) -> tuple[
    str | None,
    Literal["TRANSCRIPT", "OCR", "MEDIA_REFERENCE"],
    str,
    float | None,
    bool,
    tuple[str, ...],
]:
    records = payload.get("media_observations")
    record = records.get(sha256) if isinstance(records, dict) else None
    text_key = _DERIVED_KEYS[modality]
    if isinstance(record, dict):
        text = record.get(text_key)
        version = record.get("version")
        confidence = record.get("confidence")
        adult_confirmed = record.get("adult_confirmed")
        if not isinstance(text, str) or not text.strip():
            raise ObservationNormalizationError("DERIVED_TEXT_REQUIRED")
        if not isinstance(version, str) or not version.strip():
            raise ObservationNormalizationError("DERIVATION_VERSION_REQUIRED")
        if not isinstance(confidence, (float, int)) or isinstance(confidence, bool):
            raise ObservationNormalizationError("DERIVATION_CONFIDENCE_REQUIRED")
        if not 0 <= float(confidence) <= 1:
            raise ObservationNormalizationError("DERIVATION_CONFIDENCE_INVALID")
        if adult_confirmed is not True:
            raise ObservationNormalizationError("ADULT_CONFIRMATION_REQUIRED")
        derivation: Literal["TRANSCRIPT", "OCR"] = "OCR" if modality == "IMAGE" else "TRANSCRIPT"
        return (
            text.strip(),
            derivation,
            version.strip(),
            float(confidence),
            True,
            ("Machine-derived text reviewed by an adult; not a verified family fact.",),
        )
    return (
        None,
        "MEDIA_REFERENCE",
        "authorized-media-ref.v1",
        None,
        True,
        ("No reviewed transcript or OCR was supplied; interpretation is limited to media.",),
    )


def _observation(
    *,
    run_id: str,
    modality: ObservationModality,
    source_refs: tuple[str, ...],
    normalized_text: str | None,
    derivation: Literal["GUARDIAN_TEXT", "TRANSCRIPT", "OCR", "MEDIA_REFERENCE"],
    derivation_version: str,
    confidence: float | None,
    adult_confirmed: bool,
    limitations: tuple[str, ...],
) -> NormalizedObservation:
    binding = {
        "run_id": run_id,
        "modality": modality,
        "source_refs": source_refs,
        "normalized_text": normalized_text,
        "derivation": derivation,
        "derivation_version": derivation_version,
        "confidence": confidence,
        "adult_confirmed": adult_confirmed,
        "limitations": limitations,
    }
    encoded = json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return NormalizedObservation(
        observation_ref=f"normalized-observation:v1:sha256:{hashlib.sha256(encoded).hexdigest()}",
        modality=modality,
        source_refs=source_refs,
        normalized_text=normalized_text,
        derivation=derivation,
        derivation_version=derivation_version,
        confidence=confidence,
        adult_confirmed=adult_confirmed,
        limitations=limitations,
    )


__all__ = [
    "NormalizationResult",
    "NormalizedObservation",
    "ObservationNormalizationError",
    "normalize_observations",
]
