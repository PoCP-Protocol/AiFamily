"""Shared realtime session machinery.

Every provider needs the same turn lifecycle: open a turn on the first audio
chunk, reorder and deduplicate arrivals, hand consumed audio to the engine,
publish frames progressively, close the turn, and refuse everything once the
session is cancelled or closed. Only the "hand consumed audio to the engine"
step differs per provider, so that is the single abstract method
(`_generate_frames`); the rest lives here so two providers cannot drift into two
different definitions of what a turn is.

This class is not part of the public contract — `provider.py` is. A future
provider may subclass it or implement `RealtimeAvatarSession` from scratch.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Sequence

from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunk,
    AudioChunkAcceptance,
    AvatarFrame,
    FrameFormat,
    RealtimeAvatarError,
    RealtimeSessionSpec,
    TurnCompletion,
)
from backend.intelligence.media_factory.realtime.metrics import (
    RealtimeMetrics,
    RealtimeMetricsRecorder,
)
from backend.intelligence.media_factory.realtime.protocol import (
    RealtimeEvent,
    RealtimeEventEmitter,
    RealtimeEventType,
    frame_event_payload,
)
from backend.intelligence.media_factory.realtime.sequencing import AudioChunkSequencer
from backend.intelligence.media_factory.realtime.session_state import (
    RealtimeSessionState,
    SessionStateMachine,
)

_S = RealtimeSessionState


class BaseRealtimeAvatarSession(ABC):
    """Turn lifecycle, state machine, reordering, events and metrics."""

    def __init__(
        self,
        *,
        spec: RealtimeSessionSpec,
        provider_id: str,
        metrics_recorder: RealtimeMetricsRecorder,
        real_neural_inference: bool,
        frame_format: FrameFormat,
    ) -> None:
        self.session_id = spec.session_id
        self.provider_id = provider_id
        self.spec = spec
        self._machine = SessionStateMachine(session_id=spec.session_id)
        self._emitter = RealtimeEventEmitter(session_id=spec.session_id, trace_id=spec.trace_id)
        self._metrics = metrics_recorder
        self._real_neural_inference = real_neural_inference
        self._frame_format: FrameFormat = frame_format
        self._frames: deque[AvatarFrame] = deque()
        self._sequencer: AudioChunkSequencer | None = None
        self._turn_id: str | None = None
        self._frame_sequence = 0
        self._turn_frame_index = 0
        self._turn_audio_ms = 0
        self._turn_frames_emitted = 0
        self._cancel_reason: str | None = None

    # ---------------------------------------------------------------- lifecycle

    def start(self) -> None:
        """CREATED → PREPARING → READY, emitting `session.started`."""
        self._machine.transition_to(_S.PREPARING)
        self._machine.transition_to(_S.READY)
        self._emitter.emit(
            RealtimeEventType.SESSION_STARTED,
            payload={
                "provider_id": self.provider_id,
                "identity_handle": self.spec.identity_handle,
                "target_fps": self.spec.target_fps,
                "frame_format": self._frame_format,
                "real_neural_inference": self._real_neural_inference,
            },
        )

    @property
    def state(self) -> RealtimeSessionState:
        return self._machine.state

    @property
    def state_history(self) -> tuple[RealtimeSessionState, ...]:
        return self._machine.history

    @property
    def turn_id(self) -> str | None:
        return self._turn_id

    @property
    def queue_depth(self) -> int:
        return len(self._frames)

    # ------------------------------------------------------------------- audio

    def push_audio_chunk(self, chunk: AudioChunk) -> AudioChunkAcceptance:
        self._machine.require(_S.READY, _S.RECEIVING_AUDIO, _S.GENERATING)
        if chunk.session_id != self.session_id:
            raise RealtimeAvatarError(
                f"chunk session_id {chunk.session_id!r} does not belong to session "
                f"{self.session_id!r}"
            )

        if self._machine.state is _S.READY:
            self._open_turn(chunk.turn_id)
        elif self._turn_id != chunk.turn_id:
            raise RealtimeAvatarError(
                f"chunk turn_id {chunk.turn_id!r} arrived while turn {self._turn_id!r} "
                "is still open; call end_turn() first"
            )

        if self._machine.state is _S.GENERATING:
            self._machine.transition_to(_S.RECEIVING_AUDIO)

        sequencer = self._require_open_turn()
        acceptance, released = sequencer.offer(chunk)
        self._metrics.record_audio_chunk()
        self._emitter.emit(
            RealtimeEventType.AUDIO_ACCEPTED,
            turn_id=chunk.turn_id,
            payload=acceptance.to_manifest() | {"duration_ms": chunk.duration_ms},
        )
        self._consume(released)
        self._metrics.set_queue_depth(len(self._frames))
        return acceptance

    def end_turn(self) -> TurnCompletion:
        self._machine.require(_S.RECEIVING_AUDIO, _S.GENERATING)
        sequencer = self._require_open_turn()
        turn_id = str(self._turn_id)

        self._consume(sequencer.flush())
        self._machine.transition_to(_S.TURN_COMPLETING)

        completion = TurnCompletion(
            session_id=self.session_id,
            turn_id=turn_id,
            audio_chunks_consumed=sequencer.consumed_chunks,
            audio_duration_ms=self._turn_audio_ms,
            frames_emitted=self._turn_frames_emitted,
            first_frame_emitted=self._emitter.first_frame_emitted_for(turn_id),
        )
        self._emitter.emit(
            RealtimeEventType.TURN_COMPLETED,
            turn_id=turn_id,
            payload=completion.to_manifest()
            | {"missing_audio_sequences": list(sequencer.missing_sequences())},
        )
        self._machine.transition_to(_S.READY)
        self._sequencer = None
        self._turn_id = None
        return completion

    # ------------------------------------------------------------------ frames

    def read_frame(self) -> AvatarFrame | None:
        """Pop the next frame, or None when none is available yet.

        None means "not yet", never "done": turn completion is reported by
        `end_turn`/`turn.completed`, so a consumer polling for frames cannot
        mistake an empty queue for the end of a reply.
        """
        self._machine.require(_S.READY, _S.RECEIVING_AUDIO, _S.GENERATING, _S.TURN_COMPLETING)
        if not self._frames:
            return None
        frame = self._frames.popleft()
        self._metrics.set_queue_depth(len(self._frames))
        return frame

    # ------------------------------------------------------------ termination

    def cancel(self, *, reason: str) -> None:
        """Cancel the session. Idempotent — a barge-in may race with a close."""
        if self._machine.state in {_S.CANCELLED, _S.CLOSED}:
            return
        dropped = len(self._frames)
        self._frames.clear()
        if dropped:
            self._metrics.record_dropped_frame(dropped)
        self._metrics.set_queue_depth(0)
        self._cancel_reason = reason
        self._machine.transition_to(_S.CANCELLED)
        self._emitter.emit(
            RealtimeEventType.SESSION_CANCELLED,
            payload={
                "reason": reason,
                "turn_id": self._turn_id,
                "dropped_frames": dropped,
            },
        )
        self._sequencer = None
        self._turn_id = None

    def close(self) -> None:
        """Close the session. Idempotent."""
        if self._machine.state is _S.CLOSED:
            return
        dropped = len(self._frames)
        self._frames.clear()
        if dropped:
            self._metrics.record_dropped_frame(dropped)
        self._metrics.set_queue_depth(0)
        self._machine.transition_to(_S.CLOSED)
        self._emitter.emit(
            RealtimeEventType.SESSION_CLOSED,
            payload={"dropped_frames": dropped, "cancel_reason": self._cancel_reason},
        )
        self._sequencer = None
        self._turn_id = None

    def fail(self, message: str) -> None:
        """Move the session to ERROR and emit `provider.error`."""
        if self._machine.state is not _S.ERROR:
            self._machine.transition_to(_S.ERROR)
        self._emitter.emit(
            RealtimeEventType.PROVIDER_ERROR,
            payload={"provider_id": self.provider_id, "message": message},
        )

    # ---------------------------------------------------------------- reporting

    def metrics(self) -> RealtimeMetrics:
        return self._metrics.snapshot()

    def events(self) -> tuple[RealtimeEvent, ...]:
        return self._emitter.events

    def event_envelopes(self) -> tuple[dict[str, object], ...]:
        return tuple(event.to_envelope() for event in self._emitter.events)

    # ----------------------------------------------------------------- internals

    def _require_open_turn(self) -> AudioChunkSequencer:
        if self._sequencer is None:
            raise RealtimeAvatarError(
                f"session {self.session_id!r} has no open turn — push an audio chunk first"
            )
        return self._sequencer

    def _open_turn(self, turn_id: str) -> None:
        self._sequencer = AudioChunkSequencer(
            session_id=self.session_id,
            turn_id=turn_id,
            window=self.spec.reorder_window,
        )
        self._turn_id = turn_id
        self._turn_frame_index = 0
        self._turn_audio_ms = 0
        self._turn_frames_emitted = 0
        self._metrics.start_turn()
        self._machine.transition_to(_S.RECEIVING_AUDIO)

    def _consume(self, chunks: Sequence[AudioChunk]) -> None:
        if not chunks:
            return
        for chunk in chunks:
            self._turn_audio_ms += chunk.duration_ms

        if self._machine.state is not _S.GENERATING:
            self._machine.transition_to(_S.GENERATING)
        frames = self._generate_frames(chunks)
        self._metrics.record_motion_ready()

        for frame in frames:
            self._frames.append(frame)
            self._turn_frames_emitted += 1
            self._metrics.record_frame()
            if frame.is_first_frame:
                # A latency marker, not a substitute for the frame's own event.
                self._emitter.emit(
                    RealtimeEventType.AVATAR_FIRST_FRAME,
                    turn_id=frame.turn_id,
                    payload=frame_event_payload(frame),
                )
            self._emitter.emit(
                RealtimeEventType.AVATAR_FRAME,
                turn_id=frame.turn_id,
                payload=frame_event_payload(frame),
                binary_ref=frame.payload_ref,
            )

    def _build_frame(
        self,
        *,
        payload: bytes | None = None,
        payload_ref: str | None = None,
    ) -> AvatarFrame:
        index = self._turn_frame_index
        frame = AvatarFrame(
            session_id=self.session_id,
            turn_id=str(self._turn_id),
            frame_index=index,
            sequence=self._frame_sequence,
            presentation_time_ms=int(round(index * 1000 / self.spec.target_fps)),
            width=self.spec.frame_width,
            height=self.spec.frame_height,
            frame_format=self._frame_format,
            payload=payload,
            payload_ref=payload_ref,
            is_first_frame=index == 0,
            real_neural_inference=self._real_neural_inference,
        )
        self._turn_frame_index += 1
        self._frame_sequence += 1
        return frame

    @abstractmethod
    def _generate_frames(self, chunks: Sequence[AudioChunk]) -> Sequence[AvatarFrame]:
        """Turn consumed audio into frames. The only provider-specific step."""
