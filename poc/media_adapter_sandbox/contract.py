"""Synthetic-only MediaAdapter contract and capability primitives.

This module is deliberately self-contained.  It models media runtime state,
short-lived playback capabilities, and fail-closed scope checks without
creating a second identity, consent, audit, deletion, ledger, or AI runtime.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class MediaState(StrEnum):
    NEW = "NEW"
    LIVE = "LIVE"
    DISCONNECTED = "DISCONNECTED"
    RESTARTED = "RESTARTED"
    ENDED = "ENDED"
    STOPPED = "STOPPED"
    REVOKED = "REVOKED"
    FAILED = "FAILED"


class FaultKind(StrEnum):
    PROVIDER_FAILURE = "provider_failure"
    DISCONNECT = "disconnect"
    RESTART = "restart"
    STOP_SWITCH = "stop_switch"


class CapabilityError(RuntimeError):
    """Base error for a rejected playback capability."""


class CapabilityExpired(CapabilityError):
    pass


class CapabilityReplay(CapabilityError):
    pass


class CapabilityRevoked(CapabilityError):
    pass


class CapabilityScopeMismatch(CapabilityError):
    pass


class ProviderFailure(RuntimeError):
    pass


class InvalidTransition(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SyntheticSource:
    path: Path
    source: str = "synthetic"
    fixture_only: bool = True

    def validate(self) -> None:
        if self.source != "synthetic" or not self.fixture_only:
            raise ValueError("only fixture_only synthetic sources are admitted")
        if not self.path.is_file() or self.path.stat().st_size == 0:
            raise ValueError(f"synthetic source is missing or empty: {self.path}")


@dataclass(frozen=True, slots=True)
class PlaybackCapability:
    token: str
    media_session_ref: str
    family_ref: str
    expires_at: float


@dataclass(slots=True)
class MediaSession:
    media_session_ref: str
    family_ref: str
    source: SyntheticSource
    state: MediaState = MediaState.NEW
    provider_ref: str = "fake-provider"
    history: list[MediaState] = field(default_factory=lambda: [MediaState.NEW])

    _ALLOWED: dict[MediaState, frozenset[MediaState]] = field(
        default_factory=lambda: {
            MediaState.NEW: frozenset({MediaState.LIVE, MediaState.FAILED}),
            MediaState.LIVE: frozenset(
                {
                    MediaState.DISCONNECTED,
                    MediaState.ENDED,
                    MediaState.STOPPED,
                    MediaState.REVOKED,
                    MediaState.FAILED,
                }
            ),
            MediaState.DISCONNECTED: frozenset(
                {MediaState.RESTARTED, MediaState.STOPPED, MediaState.REVOKED, MediaState.FAILED}
            ),
            MediaState.RESTARTED: frozenset(
                {MediaState.LIVE, MediaState.STOPPED, MediaState.REVOKED, MediaState.FAILED}
            ),
            MediaState.ENDED: frozenset({MediaState.STOPPED, MediaState.REVOKED}),
            MediaState.STOPPED: frozenset(),
            MediaState.REVOKED: frozenset(),
            MediaState.FAILED: frozenset(),
        },
        repr=False,
    )

    def transition(self, next_state: MediaState) -> None:
        if next_state not in self._ALLOWED[self.state]:
            raise InvalidTransition(f"{self.state.value} -> {next_state.value}")
        self.state = next_state
        self.history.append(next_state)


class MediaAdapter(Protocol):
    """Provider-neutral contract used by the sandbox player and tests."""

    def start(self, source: SyntheticSource, family_ref: str) -> MediaSession: ...

    def playback_capability(
        self, media_session_ref: str, family_ref: str, ttl_seconds: int = 15
    ) -> PlaybackCapability: ...

    def playback_bytes(self, capability_token: str) -> bytes: ...

    def disconnect(self, media_session_ref: str) -> None: ...

    def reconnect(self, media_session_ref: str) -> None: ...

    def stop(self, media_session_ref: str) -> None: ...

    def revoke(self, media_session_ref: str) -> None: ...

    def stop_switch(self) -> None: ...


def _encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


class CapabilityAuthority:
    """HMAC capability authority local to the synthetic sandbox only."""

    def __init__(
        self,
        secret: bytes = b"synthetic-sandbox-only-secret",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret = secret
        self._clock = clock
        self._revoked_sessions: set[str] = set()
        self._revoked_tokens: set[str] = set()
        self._consumed_tokens: set[str] = set()

    def issue(
        self, media_session_ref: str, family_ref: str, ttl_seconds: int = 15
    ) -> PlaybackCapability:
        if not 0 < ttl_seconds <= 60:
            raise ValueError("sandbox playback TTL must be between 1 and 60 seconds")
        now = self._clock()
        expires_at = now + ttl_seconds
        claims = {
            "aud": "media-sandbox-player",
            "jti": uuid.uuid4().hex,
            "media_session_ref": media_session_ref,
            "family_ref": family_ref,
            "iat": now,
            "exp": expires_at,
        }
        encoded_claims = _encode(
            json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        signature = _encode(
            hmac.new(self._secret, encoded_claims.encode("ascii"), hashlib.sha256).digest()
        )
        return PlaybackCapability(
            token=f"{encoded_claims}.{signature}",
            media_session_ref=media_session_ref,
            family_ref=family_ref,
            expires_at=expires_at,
        )

    def inspect(self, token: str) -> dict[str, object]:
        try:
            encoded_claims, encoded_signature = token.split(".", 1)
            expected_signature = _encode(
                hmac.new(self._secret, encoded_claims.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(encoded_signature, expected_signature):
                raise CapabilityError("invalid capability signature")
            claims = json.loads(_decode(encoded_claims))
        except (ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CapabilityError("malformed playback capability") from exc
        if claims.get("aud") != "media-sandbox-player":
            raise CapabilityError("invalid capability audience")
        if self._clock() >= float(claims["exp"]):
            raise CapabilityExpired("playback capability expired")
        return claims

    def verify(
        self,
        token: str,
        media_session_ref: str,
        family_ref: str,
        consume: bool = True,
    ) -> dict[str, object]:
        claims = self.inspect(token)
        jti = str(claims["jti"])
        if claims["media_session_ref"] != media_session_ref or claims["family_ref"] != family_ref:
            raise CapabilityScopeMismatch("capability scope does not match requested media")
        if media_session_ref in self._revoked_sessions or jti in self._revoked_tokens:
            raise CapabilityRevoked("playback capability revoked")
        if consume and jti in self._consumed_tokens:
            raise CapabilityReplay("playback capability replay rejected")
        if consume:
            self._consumed_tokens.add(jti)
        return claims

    def revoke_session(self, media_session_ref: str) -> None:
        self._revoked_sessions.add(media_session_ref)

    def revoke_token(self, token: str) -> None:
        claims = self.inspect(token)
        self._revoked_tokens.add(str(claims["jti"]))
