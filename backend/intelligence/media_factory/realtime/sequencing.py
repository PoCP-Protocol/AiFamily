"""Audio chunk ordering for realtime turns.

A browser microphone over a lossy transport does not deliver chunks in order,
and a retry delivers the same chunk twice. Both are normal, and neither may be
allowed to corrupt a turn: motion generation consumes audio strictly in
sequence, so out-of-order arrivals must wait for their gap to fill and repeats
must be dropped without being counted twice.

This is provider-neutral on purpose — every provider needs identical reordering
semantics, and re-deriving them per engine is how two providers end up with two
different definitions of "duplicate".
"""

from __future__ import annotations

from collections.abc import Iterator

from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunk,
    AudioChunkAcceptance,
    AudioChunkRejectedError,
    ChunkDisposition,
)


class AudioChunkSequencer:
    """Per-turn reorder buffer with duplicate suppression.

    `next_expected_sequence` is the contract's cursor. A chunk at the cursor is
    consumed immediately, together with any buffered successors the arrival just
    unblocked. A chunk beyond the cursor is buffered while it is inside
    `window`; beyond the window it is refused, because an unbounded buffer turns
    packet loss into memory growth. A chunk below the cursor was already
    consumed, so it is ignored idempotently.
    """

    def __init__(self, *, session_id: str, turn_id: str, window: int = 8) -> None:
        if window < 0:
            raise AudioChunkRejectedError("reorder window must be >= 0")
        self.session_id = session_id
        self.turn_id = turn_id
        self.window = window
        self._next_expected = 0
        self._buffer: dict[int, AudioChunk] = {}
        self._consumed = 0
        self._seen: set[int] = set()
        self._final_seen = False

    @property
    def next_expected_sequence(self) -> int:
        return self._next_expected

    @property
    def buffered_chunks(self) -> int:
        return len(self._buffer)

    @property
    def consumed_chunks(self) -> int:
        return self._consumed

    @property
    def final_chunk_seen(self) -> bool:
        return self._final_seen

    def offer(self, chunk: AudioChunk) -> tuple[AudioChunkAcceptance, tuple[AudioChunk, ...]]:
        """Offer one chunk; return its disposition and whatever it released."""
        if chunk.session_id != self.session_id:
            raise AudioChunkRejectedError(
                f"chunk session_id {chunk.session_id!r} does not match session {self.session_id!r}"
            )
        if chunk.turn_id != self.turn_id:
            raise AudioChunkRejectedError(
                f"chunk turn_id {chunk.turn_id!r} does not match open turn {self.turn_id!r}"
            )

        disposition: ChunkDisposition
        released: tuple[AudioChunk, ...] = ()

        if chunk.sequence < self._next_expected or chunk.sequence in self._buffer:
            disposition = "DUPLICATE_IGNORED"
        elif chunk.sequence == self._next_expected:
            self._buffer[chunk.sequence] = chunk
            released = tuple(self._drain())
            disposition = "ACCEPTED"
        elif self.window and chunk.sequence > self._next_expected + self.window:
            disposition = "REJECTED_OUT_OF_WINDOW"
        else:
            self._buffer[chunk.sequence] = chunk
            disposition = "REORDERED_BUFFERED"

        if disposition != "REJECTED_OUT_OF_WINDOW":
            self._seen.add(chunk.sequence)
            if chunk.is_final:
                self._final_seen = True

        acceptance = AudioChunkAcceptance(
            session_id=self.session_id,
            turn_id=self.turn_id,
            sequence=chunk.sequence,
            disposition=disposition,
            next_expected_sequence=self._next_expected,
            buffered_chunks=len(self._buffer),
            consumed_chunks=self._consumed,
        )
        return acceptance, released

    def flush(self) -> tuple[AudioChunk, ...]:
        """Release buffered chunks in order at end of turn, gaps and all.

        A turn ends when the caller says it ends. Whatever never arrived is a
        hole in the audio, not a reason to hold frames back forever — so the
        remaining chunks are released in sequence order and the missing ones are
        reported by `missing_sequences`.
        """
        released = [self._buffer.pop(seq) for seq in sorted(self._buffer)]
        self._consumed += len(released)
        if released:
            self._next_expected = max(self._next_expected, released[-1].sequence + 1)
        return tuple(released)

    def missing_sequences(self) -> tuple[int, ...]:
        highest = max(self._seen) if self._seen else -1
        return tuple(seq for seq in range(highest + 1) if seq not in self._seen)

    def _drain(self) -> Iterator[AudioChunk]:
        while self._next_expected in self._buffer:
            chunk = self._buffer.pop(self._next_expected)
            self._next_expected += 1
            self._consumed += 1
            yield chunk
