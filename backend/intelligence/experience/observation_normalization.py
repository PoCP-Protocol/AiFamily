"""Server-side normalization for governed multimodal experience inputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from backend.intelligence.model_gateway.contracts import MediaInput

ObservationModality = Literal["TEXT", "AUDIO", "IMAGE", "VIDEO"]
_TEXT_KEYS = ("expression", "message", "text", "guardian_text")
_DERIVED_KEYS = {"AUDIO": "transcript", "IMAGE": "ocr_text", "VIDEO": "transcript"}


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

    observations: list[NormalizedObservation] = []
    if "TEXT" in modalities:
        text = _first_text(payload, _TEXT_KEYS)
        if text is None:
            raise ObservationNormalizationError("TEXT_OBSERVATION_REQUIRED")
        observations.append(
            _observation(
                run_id=run_id,
                modality="TEXT",
                source_refs=(f"guardian-expression:{run_id}",),
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
            source_ref = f"media:sha256:{media.sha256}"
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
    return NormalizationResult(
        observations=tuple(observations),
        payload={
            "normalized_observations": tuple(item.to_gateway_value() for item in observations)
        },
        input_refs=tuple(dict.fromkeys((*input_refs, *normalized_refs))),
    )


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
