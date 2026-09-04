"""RealtimeAvatarProvider / RealtimeAvatarSession protocols and registry (ADR-0019).

This is the seam that has to survive Ditto being replaced. Nothing below names
an engine, exposes an engine's tuning parameters, or takes a filesystem path:
identities arrive as opaque locators and leave as opaque handles, and audio
arrives in the one shape every provider must accept.

The operations are deliberately narrow — nine verbs — because every additional
verb is a thing a future provider must implement to be swappable.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.intelligence.media_factory.realtime.contracts import (
    AudioChunk,
    AudioChunkAcceptance,
    AvatarFrame,
    IdentitySpec,
    PreparedIdentity,
    RealtimeAvatarError,
    RealtimeProviderCapabilities,
    RealtimeSessionSpec,
    TurnCompletion,
)
from backend.intelligence.media_factory.realtime.metrics import RealtimeMetrics
from backend.intelligence.media_factory.realtime.protocol import RealtimeEvent
from backend.intelligence.media_factory.realtime.session_state import RealtimeSessionState


@runtime_checkable
class RealtimeAvatarSession(Protocol):
    """One live avatar session: chunked audio in, progressive frames out."""

    session_id: str

    @property
    def state(self) -> RealtimeSessionState: ...

    @property
    def turn_id(self) -> str | None: ...

    def push_audio_chunk(self, chunk: AudioChunk) -> AudioChunkAcceptance: ...

    def end_turn(self) -> TurnCompletion: ...

    def read_frame(self) -> AvatarFrame | None: ...

    def cancel(self, *, reason: str) -> None: ...

    def close(self) -> None: ...

    def metrics(self) -> RealtimeMetrics: ...

    def events(self) -> tuple[RealtimeEvent, ...]: ...


@runtime_checkable
class RealtimeAvatarProvider(Protocol):
    """A replaceable realtime avatar engine adapter."""

    provider_id: str

    def capabilities(self) -> RealtimeProviderCapabilities: ...

    def health(self) -> dict[str, object]: ...

    def prepare_identity(self, spec: IdentitySpec) -> PreparedIdentity: ...

    def start_session(self, spec: RealtimeSessionSpec) -> RealtimeAvatarSession: ...

    def close(self) -> None: ...


class RealtimeAvatarProviderRegistry:
    """In-process provider selection. An unknown id fails closed.

    Kept separate from `AvatarProviderRegistry` (offline Gate1) on purpose: a
    single registry holding both would let an offline benchmark provider be
    handed to the realtime orchestrator, which is the exact conflation ADR-0018
    §3 froze against.
    """

    def __init__(self) -> None:
        self._providers: dict[str, RealtimeAvatarProvider] = {}

    def register(self, provider: RealtimeAvatarProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> RealtimeAvatarProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise RealtimeAvatarError(f"unknown realtime avatar provider: {provider_id}")
        return provider

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def gate_eligible_ids(self) -> tuple[str, ...]:
        """Providers whose own capabilities claim realtime-gate eligibility."""
        return tuple(
            sorted(
                provider_id
                for provider_id, provider in self._providers.items()
                if provider.capabilities().realtime_gate_eligible
            )
        )
