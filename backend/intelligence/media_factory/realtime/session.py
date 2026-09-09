"""Shared realtime session machinery.

Every provider needs the same turn lifecycle: open a turn on the first audio
chunk, reorder and deduplicate arrivals, hand consumed audio to the engine,
publish frames progressively, close the turn, and refuse everything once the
session is cancelled or closed. Only the engine-facing steps differ per
provider, so those are the four hooks at the bottom of this file; the rest lives
here so two providers cannot drift into two different definitions of what a turn
is.

A frame may become available at three different moments — right after an audio
push, later while a consumer is polling, and during turn finalisation — and all
three go through `_publish_frames`. Counting frames, deciding which one is the
first of a turn and emitting the two frame events in three places is how a
stream ends up reporting a first frame twice, or not at all.

This class is not part of the public contract — `provider.py` is. A future
provider may subclass it or implement `RealtimeAvatarSession` from scratch.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import NoReturn

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

#: How many times the final drain may ask the engine before giving up.
#:
#: A safety bound, **not** a measured optimum: no real engine has ever been
#: drained through this path (REAL_DITTO_ONLINE_SMOKE=NOT_RUN), so there is
#: nothing to have measured. It exists because the alternative — looping until
#: the engine confirms — makes a silent remote node into a hung product.
#: FAMILY-REALTIME-002 is expected to replace it with a real deadline once a
#: transport exists to measure.
DEFAULT_MAX_FINAL_DRAIN_POLLS = 8


@dataclass(frozen=True, slots=True)
class FinalFrameBatch:
    """One step of a provider's final drain.

    `turn_complete` is the field that makes the drain terminable: without it an
    empty batch is indistinguishable from a finished turn, and the session layer
    is left choosing between hanging and claiming a completion it cannot see.
    """

    frames: tuple[AvatarFrame, ...] = ()
    turn_complete: bool = True


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
        max_final_drain_polls: int = DEFAULT_MAX_FINAL_DRAIN_POLLS,
    ) -> None:
        if max_final_drain_polls < 1:
            raise RealtimeAvatarError("max_final_drain_polls must be >= 1")
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
        self._max_final_drain_polls = max_final_drain_polls
        self._release_owner: Callable[[BaseRealtimeAvatarSession], None] | None = None

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

    def bind_owner(self, release: Callable[[BaseRealtimeAvatarSession], None]) -> None:
        """Let the provider that created this session reclaim its capacity.

        The callback fires once, on the first terminal transition. It hands back
        the session object rather than its id because nothing stops a caller from
        holding a session the provider has already replaced, and a stale handle
        closing itself must not evict a live namesake.
        """
        self._release_owner = release

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
        try:
            self._consume(released)
        except Exception as exc:
            self._fail_and_raise("AUDIO_PUSH_FAILED", exc)
        self._metrics.set_queue_depth(len(self._frames))
        return acceptance

    def end_turn(self) -> TurnCompletion:
        """Finalise the turn, in the one order that cannot strand audio or frames.

        The engine hears the last buffered audio, is then told the turn is over,
        and only then is drained; `turn.completed` is emitted last, so it can
        never announce a turn the engine has not been asked to finish.
        """
        self._machine.require(_S.RECEIVING_AUDIO, _S.GENERATING)
        sequencer = self._require_open_turn()
        turn_id = str(self._turn_id)

        try:
            self._consume(sequencer.flush())
            self._machine.transition_to(_S.TURN_COMPLETING)
            self._finalize_turn(turn_id)
            drain_complete, drain_polls = self._drain_final_frames(turn_id)
        except Exception as exc:
            self._fail_and_raise("TURN_FINALIZATION_FAILED", exc)

        if not drain_complete:
            # Reported on both channels rather than swallowed: a turn that ends
            # because we stopped asking is not the same event as a turn the
            # engine finished, and a consumer must be able to tell them apart.
            self._emit_provider_error(
                f"REMOTE_DRAIN_INCOMPLETE: turn {turn_id} was not confirmed drained "
                f"after {drain_polls} poll(s); frames may be missing"
            )

        completion = TurnCompletion(
            session_id=self.session_id,
            turn_id=turn_id,
            audio_chunks_consumed=sequencer.consumed_chunks,
            audio_duration_ms=self._turn_audio_ms,
            frames_emitted=self._turn_frames_emitted,
            first_frame_emitted=self._emitter.first_frame_emitted_for(turn_id),
            drain_complete=drain_complete,
        )
        self._emitter.emit(
            RealtimeEventType.TURN_COMPLETED,
            turn_id=turn_id,
            payload=completion.to_manifest()
            | {
                "missing_audio_sequences": list(sequencer.missing_sequences()),
                "final_drain_polls": drain_polls,
            },
        )
        self._machine.transition_to(_S.READY)
        self._sequencer = None
        self._turn_id = None
        return completion

    # ------------------------------------------------------------------ frames

    def read_frame(self) -> AvatarFrame | None:
        """Pop the next frame, or None when none is available yet.

        When nothing is buffered and a turn is open, the provider is asked once
        whether the engine has produced anything since the last look. That single
        poll is what makes the seam progressive: inference that finishes after
        the audio push returns would otherwise sit on the engine until an
        unrelated later push happened to collect it.

        None means "not yet", never "done": turn completion is reported by
        `end_turn`/`turn.completed`, so a consumer polling for frames cannot
        mistake an empty queue for the end of a reply.
        """
        self._machine.require(_S.READY, _S.RECEIVING_AUDIO, _S.GENERATING, _S.TURN_COMPLETING)
        if not self._frames and self._turn_id is not None:
            try:
                polled = self._poll_progressive_frames(self._turn_id)
            except Exception as exc:
                self._fail_and_raise("PROGRESSIVE_POLL_FAILED", exc)
            self._publish_frames(polled)
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
        self._release_ownership()

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
        self._release_ownership()

    def fail(self, message: str) -> None:
        """Move the session to ERROR and emit `provider.error`."""
        if self._machine.state is not _S.ERROR:
            self._machine.transition_to(_S.ERROR)
        self._emit_provider_error(message)
        self._release_ownership()

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
        self._publish_frames(frames)

    def _publish_frames(self, frames: Sequence[AvatarFrame]) -> None:
        """The one place a frame becomes visible to anyone.

        Audio push, progressive poll and final drain all arrive here, so frame
        counting, first-frame semantics, both frame events and queue depth have
        exactly one definition instead of three that agree until they do not.
        """
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
        self._metrics.set_queue_depth(len(self._frames))

    def _drain_final_frames(self, turn_id: str) -> tuple[bool, int]:
        """Ask the provider for terminal frames, a bounded number of times."""
        polls = 0
        while polls < self._max_final_drain_polls:
            polls += 1
            batch = self._poll_final_frames(turn_id)
            self._publish_frames(batch.frames)
            if batch.turn_complete:
                return True, polls
        return False, polls

    def _emit_provider_error(self, message: str) -> None:
        self._emitter.emit(
            RealtimeEventType.PROVIDER_ERROR,
            payload={"provider_id": self.provider_id, "message": message},
        )

    def _fail_and_raise(self, code: str, exc: BaseException) -> NoReturn:
        message = f"{code}: session {self.session_id} — {exc}"
        self.fail(message)
        raise RealtimeAvatarError(message) from exc

    def _release_ownership(self) -> None:
        release, self._release_owner = self._release_owner, None
        if release is not None:
            release(self)

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

    # ------------------------------------------------------------ provider hooks

    @abstractmethod
    def _generate_frames(self, chunks: Sequence[AudioChunk]) -> Sequence[AvatarFrame]:
        """Hand consumed audio to the engine, returning whatever it has *now*.

        Returning nothing is normal and not a failure: a real engine usually has
        produced nothing by the time the push returns.
        """

    def _poll_progressive_frames(self, turn_id: str) -> Sequence[AvatarFrame]:
        """Frames the engine finished since the last look. Default: none.

        An in-process provider that produces its frames synchronously has nothing
        to add here. A remote one does — this is the only path by which a frame
        that appeared 30 ms after the audio push reaches the consumer.
        """
        return ()

    def _finalize_turn(self, turn_id: str) -> None:
        """Tell the engine the turn is over.

        Default: nothing to tell — an in-process provider that generated its
        frames synchronously has no remote turn to close. Deliberately not
        abstract, so adding the hook does not break a provider that needs it.
        """
        return None

    def _poll_final_frames(self, turn_id: str) -> FinalFrameBatch:
        """One bounded step of the final drain. Default: already complete."""
        return FinalFrameBatch()
