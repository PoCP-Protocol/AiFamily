"""Synthetic multimodal evidence alignment for Xiao Ju Deng live sessions.

This research sandbox aligns VAD/ASR audio evidence with sampled video frames
and OCR observations.  It produces a draft timeline only: no output is a
canonical Family fact, no provider is contacted directly, and every result
requires a human review before it may be shown outside the sandbox.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"


class MultimodalRejected(RuntimeError):
    """Multimodal evidence was incomplete, unsafe, or outside its scope."""


@dataclass(frozen=True, slots=True)
class SyntheticMediaInput:
    tenant_id: str
    family_id: str
    session_ref: str
    media_ref: str
    audio_ref: str
    video_ref: str
    duration_ms: int
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True
    contains_real_person: bool = False
    contains_biometric_data: bool = False

    def validate(self) -> None:
        if self.source != SANDBOX_SOURCE or not self.fixture_only:
            raise MultimodalRejected("multimodal input must be explicitly synthetic")
        if self.contains_real_person or self.contains_biometric_data:
            raise MultimodalRejected("real-person or biometric media is not admitted")
        if not all(
            (
                self.tenant_id,
                self.family_id,
                self.session_ref,
                self.media_ref,
                self.audio_ref,
                self.video_ref,
            )
        ):
            raise MultimodalRejected("multimodal input identity is incomplete")
        if self.duration_ms <= 0:
            raise MultimodalRejected("media duration must be positive")


@dataclass(frozen=True, slots=True)
class SpeechWindow:
    start_ms: int
    end_ms: int
    confidence: float


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str
    speaker_ref: str
    confidence: float
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class VideoKeyframe:
    at_ms: int
    frame_ref: str
    scene_ref: str
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class OcrObservation:
    frame_ref: str
    text: str
    confidence: float
    evidence_ref: str


class VadPort(Protocol):
    def detect(self, media: SyntheticMediaInput) -> Sequence[SpeechWindow]: ...


class AsrPort(Protocol):
    def transcribe(
        self, media: SyntheticMediaInput, windows: Sequence[SpeechWindow]
    ) -> Sequence[TranscriptSegment]: ...


class FrameSamplerPort(Protocol):
    def sample(self, media: SyntheticMediaInput) -> Sequence[VideoKeyframe]: ...


class OcrPort(Protocol):
    def extract(
        self, media: SyntheticMediaInput, frames: Sequence[VideoKeyframe]
    ) -> Sequence[OcrObservation]: ...


@dataclass(frozen=True, slots=True)
class TimelineCue:
    start_ms: int
    end_ms: int
    speaker_ref: str
    transcript: str
    frame_ref: str | None
    scene_ref: str | None
    ocr_text: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MultimodalTimelineDraft:
    timeline_ref: str
    tenant_id: str
    family_id: str
    session_ref: str
    media_ref: str
    cues: tuple[TimelineCue, ...]
    evidence_digest: str
    modalities: tuple[str, ...]
    risk_flags: tuple[str, ...]
    status: str = "DRAFT"
    human_review_required: bool = True
    may_mutate_business_state: bool = False
    external_effect: bool = False
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


class MultimodalTimelinePipeline:
    """Align provider-neutral multimodal observations on one session clock."""

    def __init__(
        self,
        *,
        vad: VadPort,
        asr: AsrPort,
        frames: FrameSamplerPort,
        ocr: OcrPort,
    ) -> None:
        self._vad = vad
        self._asr = asr
        self._frames = frames
        self._ocr = ocr

    def build(self, media: SyntheticMediaInput) -> MultimodalTimelineDraft:
        media.validate()
        try:
            windows = tuple(self._vad.detect(media))
            transcripts = tuple(self._asr.transcribe(media, windows))
            keyframes = tuple(self._frames.sample(media))
            ocr = tuple(self._ocr.extract(media, keyframes))
        except Exception as exc:
            raise MultimodalRejected("multimodal provider failed closed") from exc

        _validate_windows(windows, media.duration_ms)
        _validate_transcripts(transcripts, media.duration_ms)
        _validate_frames(keyframes, media.duration_ms)
        _validate_ocr(ocr, keyframes)
        if not transcripts:
            raise MultimodalRejected("ASR produced no transcript evidence")
        if not keyframes:
            raise MultimodalRejected("video sampler produced no frame evidence")

        cues = tuple(
            _align_segment(segment, keyframes=keyframes, ocr=ocr)
            for segment in sorted(transcripts, key=lambda item: (item.start_ms, item.end_ms))
        )
        modalities = ["audio", "video", "transcript"]
        if any(cue.ocr_text for cue in cues):
            modalities.append("ocr")
        digest_source = "|".join(
            f"{cue.start_ms}:{cue.end_ms}:{cue.speaker_ref}:{cue.transcript}:"
            f"{cue.frame_ref}:{','.join(cue.ocr_text)}:{','.join(cue.evidence_refs)}"
            for cue in cues
        )
        evidence_digest = sha256(digest_source.encode("utf-8")).hexdigest()
        risk_flags = _risk_flags(cues)
        return MultimodalTimelineDraft(
            timeline_ref=f"timeline.synthetic.{evidence_digest[:20]}",
            tenant_id=media.tenant_id,
            family_id=media.family_id,
            session_ref=media.session_ref,
            media_ref=media.media_ref,
            cues=cues,
            evidence_digest=evidence_digest,
            modalities=tuple(modalities),
            risk_flags=risk_flags,
        )


def _align_segment(
    segment: TranscriptSegment,
    *,
    keyframes: Sequence[VideoKeyframe],
    ocr: Sequence[OcrObservation],
) -> TimelineCue:
    midpoint = segment.start_ms + (segment.end_ms - segment.start_ms) // 2
    frame = min(keyframes, key=lambda item: (abs(item.at_ms - midpoint), item.at_ms))
    frame_ocr = tuple(item for item in ocr if item.frame_ref == frame.frame_ref)
    refs = [segment.evidence_ref, frame.evidence_ref]
    refs.extend(item.evidence_ref for item in frame_ocr)
    return TimelineCue(
        start_ms=segment.start_ms,
        end_ms=segment.end_ms,
        speaker_ref=segment.speaker_ref,
        transcript=segment.text.strip(),
        frame_ref=frame.frame_ref,
        scene_ref=frame.scene_ref,
        ocr_text=tuple(item.text.strip() for item in frame_ocr if item.text.strip()),
        evidence_refs=tuple(refs),
    )


def _validate_windows(windows: Sequence[SpeechWindow], duration_ms: int) -> None:
    for window in windows:
        _validate_interval(window.start_ms, window.end_ms, duration_ms, "VAD")
        _validate_confidence(window.confidence, "VAD")


def _validate_transcripts(segments: Sequence[TranscriptSegment], duration_ms: int) -> None:
    previous_end = 0
    for segment in sorted(segments, key=lambda item: (item.start_ms, item.end_ms)):
        _validate_interval(segment.start_ms, segment.end_ms, duration_ms, "ASR")
        _validate_confidence(segment.confidence, "ASR")
        if not all((segment.text.strip(), segment.speaker_ref, segment.evidence_ref)):
            raise MultimodalRejected("ASR evidence is incomplete")
        if segment.start_ms < previous_end:
            raise MultimodalRejected("ASR segments overlap or are out of order")
        previous_end = segment.end_ms


def _validate_frames(frames: Sequence[VideoKeyframe], duration_ms: int) -> None:
    seen: set[str] = set()
    for frame in frames:
        if not 0 <= frame.at_ms <= duration_ms:
            raise MultimodalRejected("video frame is outside the media timeline")
        if not all((frame.frame_ref, frame.scene_ref, frame.evidence_ref)):
            raise MultimodalRejected("video frame evidence is incomplete")
        if frame.frame_ref in seen:
            raise MultimodalRejected("duplicate video frame reference")
        seen.add(frame.frame_ref)


def _validate_ocr(observations: Sequence[OcrObservation], frames: Sequence[VideoKeyframe]) -> None:
    frame_refs = {frame.frame_ref for frame in frames}
    for item in observations:
        _validate_confidence(item.confidence, "OCR")
        if item.frame_ref not in frame_refs:
            raise MultimodalRejected("OCR evidence references an unknown frame")
        if not item.evidence_ref or not item.text.strip():
            raise MultimodalRejected("OCR evidence is incomplete")


def _validate_interval(start_ms: int, end_ms: int, duration_ms: int, label: str) -> None:
    if start_ms < 0 or end_ms <= start_ms or end_ms > duration_ms:
        raise MultimodalRejected(f"{label} evidence is outside the media timeline")


def _validate_confidence(value: float, label: str) -> None:
    if not 0 <= value <= 1:
        raise MultimodalRejected(f"{label} confidence is outside 0..1")


def _risk_flags(cues: Sequence[TimelineCue]) -> tuple[str, ...]:
    chunks = [text for cue in cues for text in (cue.transcript, *cue.ocr_text)]
    combined = " ".join(chunks)
    lowered = combined.lower()
    risks: list[str] = []
    if "ignore previous instructions" in lowered or "忽略之前" in combined:
        risks.append("PROMPT_INJECTION_DRAFT")
    if any(keyword in combined for keyword in ("诊断", "保证治愈", "绝对有效")):
        risks.append("HIGH_IMPACT_CLAIM_DRAFT")
    return tuple(risks)
