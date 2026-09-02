"""Provider-neutral creator publishing contract for a synthetic-only sandbox.

The contract accepts opaque creator and session references from the canonical
platform. It deliberately does not implement identity, consent, audit,
deletion, or another business ledger. Publish capabilities are ephemeral
media permissions and are never business facts.
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
from typing import Protocol


class ProducerState(StrEnum):
    INGESTING = "INGESTING"
    LIVE = "LIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class CreatorContractError(RuntimeError):
    """Base error for fail-closed creator publishing operations."""


class DeviceCheckFailed(CreatorContractError):
    pass


class PublishCapabilityExpired(CreatorContractError):
    pass


class PublishCapabilityConsumed(CreatorContractError):
    pass


class PublishScopeMismatch(CreatorContractError):
    pass


class PublishCapabilityInvalid(CreatorContractError):
    pass


class IdempotencyConflict(CreatorContractError):
    pass


class InvalidProducerTransition(CreatorContractError):
    pass


class ProviderFailure(CreatorContractError):
    pass


class StopSwitchEngaged(CreatorContractError):
    pass


@dataclass(frozen=True, slots=True)
class ProducerDevice:
    """Synthetic device declaration; this sandbox never opens real hardware."""

    device_ref: str
    camera_ready: bool = True
    microphone_ready: bool = True
    uplink_ready: bool = True
    source: str = "synthetic"
    fixture_only: bool = True

    def validate_sandbox_boundary(self) -> None:
        if self.source != "synthetic" or not self.fixture_only:
            raise DeviceCheckFailed("only fixture_only synthetic producer devices are admitted")
        if not self.device_ref.strip():
            raise DeviceCheckFailed("device_ref is required")


@dataclass(frozen=True, slots=True)
class DeviceCheck:
    device_ref: str
    camera_ready: bool
    microphone_ready: bool
    uplink_ready: bool
    provider_ref: str
    source: str = "synthetic"
    fixture_only: bool = True

    @property
    def passed(self) -> bool:
        return self.camera_ready and self.microphone_ready and self.uplink_ready


@dataclass(frozen=True, slots=True)
class PublishCapability:
    token: str
    creator_ref: str
    session_ref: str
    expires_at: float
    source: str = "synthetic"
    fixture_only: bool = True


@dataclass(slots=True)
class ProducerSession:
    producer_session_ref: str
    creator_ref: str
    session_ref: str
    device_ref: str
    provider_ref: str
    idempotency_key: str
    state: ProducerState = ProducerState.INGESTING
    history: list[ProducerState] = field(default_factory=lambda: [ProducerState.INGESTING])
    source: str = "synthetic"
    fixture_only: bool = True

    _ALLOWED: dict[ProducerState, frozenset[ProducerState]] = field(
        default_factory=lambda: {
            ProducerState.INGESTING: frozenset(
                {ProducerState.LIVE, ProducerState.STOPPED, ProducerState.FAILED}
            ),
            ProducerState.LIVE: frozenset(
                {
                    ProducerState.INGESTING,
                    ProducerState.PAUSED,
                    ProducerState.ENDED,
                    ProducerState.STOPPED,
                    ProducerState.FAILED,
                }
            ),
            ProducerState.PAUSED: frozenset(
                {
                    ProducerState.INGESTING,
                    ProducerState.ENDED,
                    ProducerState.STOPPED,
                    ProducerState.FAILED,
                }
            ),
            ProducerState.FAILED: frozenset({ProducerState.INGESTING, ProducerState.STOPPED}),
            ProducerState.ENDED: frozenset(),
            ProducerState.STOPPED: frozenset(),
        },
        repr=False,
    )

    def transition(self, next_state: ProducerState) -> None:
        if next_state not in self._ALLOWED[self.state]:
            raise InvalidProducerTransition(f"{self.state.value} -> {next_state.value}")
        self.state = next_state
        self.history.append(next_state)


class CreatorPublishProvider(Protocol):
    """Provider SPI that can be mapped to any media runtime."""

    provider_ref: str

    def check_device(self, device: ProducerDevice) -> DeviceCheck: ...

    def begin_publish(self, producer_session: ProducerSession) -> None: ...

    def pause(self, producer_session: ProducerSession) -> None: ...

    def resume(self, producer_session: ProducerSession) -> None: ...

    def reconnect(self, producer_session: ProducerSession) -> None: ...

    def end(self, producer_session: ProducerSession) -> None: ...

    def stop(self, producer_session: ProducerSession) -> None: ...


class CreatorMediaAdapter(Protocol):
    def device_check(self, device: ProducerDevice) -> DeviceCheck: ...

    def publish_capability(
        self, creator_ref: str, session_ref: str, ttl_seconds: int = 15
    ) -> PublishCapability: ...

    def start_publish(
        self,
        capability_token: str,
        creator_ref: str,
        session_ref: str,
        device: ProducerDevice,
        idempotency_key: str,
    ) -> ProducerSession: ...

    def pause(self, producer_session_ref: str) -> None: ...

    def resume(self, producer_session_ref: str) -> None: ...

    def connection_lost(self, producer_session_ref: str) -> None: ...

    def reconnect(self, producer_session_ref: str) -> None: ...

    def end(self, producer_session_ref: str) -> None: ...

    def stop_switch(self) -> None: ...


def _encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


class PublishCapabilityAuthority:
    """Local HMAC authority using a fixed, non-production sandbox secret."""

    def __init__(
        self,
        secret: bytes = b"xiaojudeng-creator-synthetic-only",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret = secret
        self._clock = clock
        self._consumed: set[str] = set()
        self._revoked_sessions: set[str] = set()

    def issue(self, creator_ref: str, session_ref: str, ttl_seconds: int = 15) -> PublishCapability:
        if not creator_ref.strip() or not session_ref.strip():
            raise ValueError("creator_ref and session_ref are required")
        if not 0 < ttl_seconds <= 60:
            raise ValueError("sandbox publish TTL must be between 1 and 60 seconds")
        now = self._clock()
        expires_at = now + ttl_seconds
        claims = {
            "aud": "media-sandbox-creator",
            "creator_ref": creator_ref,
            "exp": expires_at,
            "iat": now,
            "jti": uuid.uuid4().hex,
            "session_ref": session_ref,
        }
        encoded = _encode(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        signature = _encode(
            hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return PublishCapability(
            token=f"{encoded}.{signature}",
            creator_ref=creator_ref,
            session_ref=session_ref,
            expires_at=expires_at,
        )

    def verify(
        self,
        token: str,
        creator_ref: str,
        session_ref: str,
        *,
        consume: bool,
    ) -> dict[str, object]:
        claims = self._inspect(token)
        if claims["creator_ref"] != creator_ref or claims["session_ref"] != session_ref:
            raise PublishScopeMismatch("publish capability scope mismatch")
        if session_ref in self._revoked_sessions:
            raise StopSwitchEngaged("publishing for this session has been stopped")
        jti = str(claims["jti"])
        if consume and jti in self._consumed:
            raise PublishCapabilityConsumed("publish capability is one-time")
        if consume:
            self._consumed.add(jti)
        return claims

    def revoke_session(self, session_ref: str) -> None:
        self._revoked_sessions.add(session_ref)

    def _inspect(self, token: str) -> dict[str, object]:
        try:
            encoded, supplied_signature = token.split(".", 1)
            expected_signature = _encode(
                hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise PublishCapabilityInvalid("invalid publish capability signature")
            claims = json.loads(_decode(encoded))
            if claims.get("aud") != "media-sandbox-creator":
                raise PublishCapabilityInvalid("invalid publish capability audience")
            if self._clock() >= float(claims["exp"]):
                raise PublishCapabilityExpired("publish capability expired")
            for required in ("creator_ref", "session_ref", "jti"):
                if not isinstance(claims.get(required), str) or not claims[required]:
                    raise PublishCapabilityInvalid("publish capability has incomplete scope")
            return claims
        except (PublishCapabilityInvalid, PublishCapabilityExpired):
            raise
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PublishCapabilityInvalid("malformed publish capability") from exc


class SyntheticCreatorProvider:
    """Deterministic, network-free provider used only by contract tests."""

    provider_ref = "synthetic-creator-provider"

    def __init__(self) -> None:
        self._failures: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    def fail_next(self, operation: str) -> None:
        self._failures.add(operation)

    def check_device(self, device: ProducerDevice) -> DeviceCheck:
        self._maybe_fail("device_check")
        device.validate_sandbox_boundary()
        result = DeviceCheck(
            device_ref=device.device_ref,
            camera_ready=device.camera_ready,
            microphone_ready=device.microphone_ready,
            uplink_ready=device.uplink_ready,
            provider_ref=self.provider_ref,
        )
        self.calls.append(("device_check", device.device_ref))
        return result

    def begin_publish(self, producer_session: ProducerSession) -> None:
        self._record("begin_publish", producer_session)

    def pause(self, producer_session: ProducerSession) -> None:
        self._record("pause", producer_session)

    def resume(self, producer_session: ProducerSession) -> None:
        self._record("resume", producer_session)

    def reconnect(self, producer_session: ProducerSession) -> None:
        self._record("reconnect", producer_session)

    def end(self, producer_session: ProducerSession) -> None:
        self._record("end", producer_session)

    def stop(self, producer_session: ProducerSession) -> None:
        self._record("stop", producer_session)

    def _record(self, operation: str, producer_session: ProducerSession) -> None:
        self._maybe_fail(operation)
        self.calls.append((operation, producer_session.producer_session_ref))

    def _maybe_fail(self, operation: str) -> None:
        if operation in self._failures:
            self._failures.remove(operation)
            raise ProviderFailure(f"synthetic provider failure during {operation}")


class SyntheticCreatorMediaAdapter:
    """In-memory adapter proving provider-neutral publishing invariants."""

    def __init__(
        self,
        provider: CreatorPublishProvider | None = None,
        authority: PublishCapabilityAuthority | None = None,
    ) -> None:
        self.provider = provider or SyntheticCreatorProvider()
        self.authority = authority or PublishCapabilityAuthority()
        self.sessions: dict[str, ProducerSession] = {}
        self._idempotent_starts: dict[tuple[str, str, str], tuple[str, str]] = {}
        self._stop_engaged = False
        self._sequence = 0

    def device_check(self, device: ProducerDevice) -> DeviceCheck:
        if self._stop_engaged:
            raise StopSwitchEngaged("manual stop switch is engaged")
        result = self.provider.check_device(device)
        if not result.passed:
            raise DeviceCheckFailed("camera, microphone, and uplink must all pass")
        return result

    def publish_capability(
        self, creator_ref: str, session_ref: str, ttl_seconds: int = 15
    ) -> PublishCapability:
        if self._stop_engaged:
            raise StopSwitchEngaged("manual stop switch is engaged")
        return self.authority.issue(creator_ref, session_ref, ttl_seconds)

    def start_publish(
        self,
        capability_token: str,
        creator_ref: str,
        session_ref: str,
        device: ProducerDevice,
        idempotency_key: str,
    ) -> ProducerSession:
        if self._stop_engaged:
            raise StopSwitchEngaged("manual stop switch is engaged")
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")

        key = (creator_ref, session_ref, idempotency_key)
        fingerprint = self._fingerprint(capability_token, device)
        existing = self._idempotent_starts.get(key)
        if existing is not None:
            existing_fingerprint, producer_session_ref = existing
            if existing_fingerprint != fingerprint:
                raise IdempotencyConflict("idempotency key was reused with different input")
            self.authority.verify(
                capability_token,
                creator_ref,
                session_ref,
                consume=False,
            )
            return self.sessions[producer_session_ref]

        self.authority.verify(capability_token, creator_ref, session_ref, consume=True)
        check = self.device_check(device)
        self._sequence += 1
        producer_session = ProducerSession(
            producer_session_ref=f"producer.synthetic.{self._sequence}",
            creator_ref=creator_ref,
            session_ref=session_ref,
            device_ref=check.device_ref,
            provider_ref=check.provider_ref,
            idempotency_key=idempotency_key,
        )
        self.sessions[producer_session.producer_session_ref] = producer_session
        self._idempotent_starts[key] = (fingerprint, producer_session.producer_session_ref)
        try:
            self.provider.begin_publish(producer_session)
        except ProviderFailure:
            producer_session.transition(ProducerState.FAILED)
            raise
        producer_session.transition(ProducerState.LIVE)
        return producer_session

    def pause(self, producer_session_ref: str) -> None:
        producer_session = self._active(producer_session_ref, {ProducerState.LIVE})
        self._provider_operation(producer_session, self.provider.pause)
        producer_session.transition(ProducerState.PAUSED)

    def resume(self, producer_session_ref: str) -> None:
        producer_session = self._active(producer_session_ref, {ProducerState.PAUSED})
        producer_session.transition(ProducerState.INGESTING)
        self._provider_operation(producer_session, self.provider.resume)
        producer_session.transition(ProducerState.LIVE)

    def connection_lost(self, producer_session_ref: str) -> None:
        producer_session = self._active(
            producer_session_ref,
            {ProducerState.LIVE, ProducerState.PAUSED},
        )
        producer_session.transition(ProducerState.INGESTING)

    def reconnect(self, producer_session_ref: str) -> None:
        producer_session = self._active(
            producer_session_ref,
            {ProducerState.INGESTING, ProducerState.FAILED},
        )
        if producer_session.state is ProducerState.FAILED:
            producer_session.transition(ProducerState.INGESTING)
        self._provider_operation(producer_session, self.provider.reconnect)
        producer_session.transition(ProducerState.LIVE)

    def end(self, producer_session_ref: str) -> None:
        producer_session = self._active(
            producer_session_ref,
            {ProducerState.LIVE, ProducerState.PAUSED},
        )
        self._provider_operation(producer_session, self.provider.end)
        producer_session.transition(ProducerState.ENDED)
        self.authority.revoke_session(producer_session.session_ref)

    def stop_switch(self) -> None:
        self._stop_engaged = True
        first_failure: ProviderFailure | None = None
        for producer_session in self.sessions.values():
            if producer_session.state in {ProducerState.ENDED, ProducerState.STOPPED}:
                continue
            try:
                self.provider.stop(producer_session)
            except ProviderFailure as exc:
                first_failure = first_failure or exc
            finally:
                if producer_session.state is not ProducerState.STOPPED:
                    producer_session.transition(ProducerState.STOPPED)
                self.authority.revoke_session(producer_session.session_ref)
        if first_failure is not None:
            raise first_failure

    def _active(
        self,
        producer_session_ref: str,
        allowed_states: set[ProducerState],
    ) -> ProducerSession:
        if self._stop_engaged:
            raise StopSwitchEngaged("manual stop switch is engaged")
        try:
            producer_session = self.sessions[producer_session_ref]
        except KeyError as exc:
            raise PublishScopeMismatch("unknown producer session") from exc
        if producer_session.state not in allowed_states:
            allowed = ", ".join(sorted(state.value for state in allowed_states))
            raise InvalidProducerTransition(
                f"{producer_session.state.value} not in allowed states: {allowed}"
            )
        return producer_session

    @staticmethod
    def _provider_operation(
        producer_session: ProducerSession,
        operation: Callable[[ProducerSession], None],
    ) -> None:
        try:
            operation(producer_session)
        except ProviderFailure:
            if producer_session.state is not ProducerState.FAILED:
                producer_session.transition(ProducerState.FAILED)
            raise

    @staticmethod
    def _fingerprint(capability_token: str, device: ProducerDevice) -> str:
        material = "|".join(
            (
                capability_token,
                device.device_ref,
                str(device.camera_ready),
                str(device.microphone_ready),
                str(device.uplink_ready),
                device.source,
                str(device.fixture_only),
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
