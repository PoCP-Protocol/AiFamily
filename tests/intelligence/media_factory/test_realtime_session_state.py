"""Session state machine and audio chunk sequencing (FAMILY-REALTIME-001).

The interesting assertions here are the negative ones. A realtime session that
half-accepts audio after being closed does not fail visibly — it produces a
stream that stops for no stated reason, which is the hardest class of realtime
bug to diagnose. So every illegal move must raise at the boundary.
"""

from __future__ import annotations

import pytest

from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunk,
    AudioChunkRejectedError,
    InvalidSessionTransitionError,
)
from backend.intelligence.media_factory.realtime.sequencing import AudioChunkSequencer
from backend.intelligence.media_factory.realtime.session_state import (
    ACTIVE_TURN_STATES,
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    RealtimeSessionState,
    SessionStateMachine,
)

_S = RealtimeSessionState

PCM16_20MS_AT_16K = b"\x00\x01" * 320


def _chunk(sequence: int, *, turn_id: str = "t1", is_final: bool = False) -> AudioChunk:
    return AudioChunk(
        session_id="s1",
        turn_id=turn_id,
        sequence=sequence,
        presentation_time_ms=sequence * 20,
        payload=PCM16_20MS_AT_16K,
        is_final=is_final,
    )


# ------------------------------------------------------------------ state machine


def test_every_required_state_exists() -> None:
    assert {s.value for s in RealtimeSessionState} == {
        "CREATED",
        "PREPARING",
        "READY",
        "RECEIVING_AUDIO",
        "GENERATING",
        "TURN_COMPLETING",
        "CANCELLED",
        "CLOSED",
        "ERROR",
    }


def test_transition_table_covers_every_state() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(RealtimeSessionState)
    assert set(TERMINAL_STATES) == {_S.CLOSED}
    assert set(ACTIVE_TURN_STATES) == {_S.RECEIVING_AUDIO, _S.GENERATING, _S.TURN_COMPLETING}


def test_happy_path_transitions_are_deterministic() -> None:
    machine = SessionStateMachine(session_id="s1")
    assert machine.state is _S.CREATED
    for target in (
        _S.PREPARING,
        _S.READY,
        _S.RECEIVING_AUDIO,
        _S.GENERATING,
        _S.TURN_COMPLETING,
        _S.READY,
        _S.CLOSED,
    ):
        machine.transition_to(target)
    assert machine.state is _S.CLOSED
    assert machine.is_terminal is True
    assert machine.history[0] is _S.CREATED
    assert machine.history[-1] is _S.CLOSED


@pytest.mark.parametrize(
    ("path", "illegal"),
    [
        ((), _S.READY),
        ((), _S.RECEIVING_AUDIO),
        ((), _S.GENERATING),
        ((_S.PREPARING,), _S.RECEIVING_AUDIO),
        ((_S.PREPARING, _S.READY), _S.GENERATING),
        ((_S.PREPARING, _S.READY), _S.TURN_COMPLETING),
        ((_S.PREPARING, _S.READY, _S.RECEIVING_AUDIO), _S.PREPARING),
        ((_S.PREPARING, _S.READY, _S.RECEIVING_AUDIO), _S.READY),
        ((_S.CANCELLED,), _S.READY),
        ((_S.CANCELLED,), _S.RECEIVING_AUDIO),
        ((_S.ERROR,), _S.READY),
        ((_S.CLOSED,), _S.READY),
        ((_S.CLOSED,), _S.CLOSED),
    ],
)
def test_invalid_transitions_fail_explicitly(
    path: tuple[RealtimeSessionState, ...], illegal: RealtimeSessionState
) -> None:
    machine = SessionStateMachine(session_id="s1")
    for step in path:
        machine.transition_to(step)
    assert machine.can_transition_to(illegal) is False
    with pytest.raises(InvalidSessionTransitionError, match="INVALID_SESSION_TRANSITION"):
        machine.transition_to(illegal)
    # A refused transition must not have moved the machine.
    assert machine.state is (path[-1] if path else _S.CREATED)


def test_closed_is_absorbing() -> None:
    machine = SessionStateMachine(session_id="s1")
    machine.transition_to(_S.CLOSED)
    assert ALLOWED_TRANSITIONS[_S.CLOSED] == frozenset()


def test_cancelled_only_leads_to_closed() -> None:
    """V0 has no turn-level barge-in; cancel ends the session (ADR-0019)."""
    assert ALLOWED_TRANSITIONS[_S.CANCELLED] == frozenset({_S.CLOSED})


def test_require_names_the_expected_states() -> None:
    machine = SessionStateMachine(session_id="s1")
    machine.require(_S.CREATED)
    with pytest.raises(InvalidSessionTransitionError, match="INVALID_SESSION_STATE"):
        machine.require(_S.READY, _S.GENERATING)
    manifest = machine.to_manifest()
    assert manifest["state"] == "CREATED"
    assert manifest["is_terminal"] is False


# --------------------------------------------------------------------- sequencing


def test_ordered_chunks_are_consumed_immediately() -> None:
    sequencer = AudioChunkSequencer(session_id="s1", turn_id="t1")
    for sequence in range(4):
        acceptance, released = sequencer.offer(_chunk(sequence))
        assert acceptance.disposition == "ACCEPTED"
        assert [c.sequence for c in released] == [sequence]
        assert acceptance.next_expected_sequence == sequence + 1
        assert acceptance.buffered_chunks == 0
    assert sequencer.consumed_chunks == 4
    assert sequencer.missing_sequences() == ()


def test_out_of_order_chunks_buffer_then_release_in_order() -> None:
    sequencer = AudioChunkSequencer(session_id="s1", turn_id="t1")
    acceptance, released = sequencer.offer(_chunk(2))
    assert acceptance.disposition == "REORDERED_BUFFERED"
    assert released == ()
    assert acceptance.buffered_chunks == 1

    acceptance, released = sequencer.offer(_chunk(1))
    assert acceptance.disposition == "REORDERED_BUFFERED"
    assert released == ()

    # The gap filler releases everything it unblocked, in sequence order.
    acceptance, released = sequencer.offer(_chunk(0))
    assert acceptance.disposition == "ACCEPTED"
    assert [c.sequence for c in released] == [0, 1, 2]
    assert acceptance.next_expected_sequence == 3
    assert acceptance.buffered_chunks == 0
    assert sequencer.consumed_chunks == 3
    assert sequencer.missing_sequences() == ()


def test_duplicate_chunks_are_ignored_idempotently() -> None:
    sequencer = AudioChunkSequencer(session_id="s1", turn_id="t1")
    sequencer.offer(_chunk(0))
    sequencer.offer(_chunk(1))

    acceptance, released = sequencer.offer(_chunk(0))
    assert acceptance.disposition == "DUPLICATE_IGNORED"
    assert acceptance.accepted is True
    assert released == ()
    assert sequencer.consumed_chunks == 2

    # A duplicate of a chunk still sitting in the reorder buffer is also a duplicate.
    sequencer.offer(_chunk(4))
    acceptance, released = sequencer.offer(_chunk(4))
    assert acceptance.disposition == "DUPLICATE_IGNORED"
    assert acceptance.buffered_chunks == 1


def test_chunks_beyond_the_reorder_window_are_refused() -> None:
    sequencer = AudioChunkSequencer(session_id="s1", turn_id="t1", window=2)
    acceptance, released = sequencer.offer(_chunk(9))
    assert acceptance.disposition == "REJECTED_OUT_OF_WINDOW"
    assert acceptance.accepted is False
    assert released == ()
    assert acceptance.buffered_chunks == 0


def test_flush_releases_the_gap_and_reports_what_never_arrived() -> None:
    sequencer = AudioChunkSequencer(session_id="s1", turn_id="t1")
    sequencer.offer(_chunk(0))
    sequencer.offer(_chunk(2))
    sequencer.offer(_chunk(3, is_final=True))
    assert sequencer.final_chunk_seen is True

    released = sequencer.flush()
    assert [c.sequence for c in released] == [2, 3]
    assert sequencer.missing_sequences() == (1,)
    assert sequencer.consumed_chunks == 3


def test_sequencer_rejects_chunks_from_another_session_or_turn() -> None:
    sequencer = AudioChunkSequencer(session_id="s1", turn_id="t1")
    with pytest.raises(AudioChunkRejectedError, match="turn_id"):
        sequencer.offer(_chunk(0, turn_id="other-turn"))
    with pytest.raises(AudioChunkRejectedError, match="session_id"):
        sequencer.offer(
            AudioChunk(
                session_id="other-session",
                turn_id="t1",
                sequence=0,
                presentation_time_ms=0,
                payload=PCM16_20MS_AT_16K,
            )
        )
