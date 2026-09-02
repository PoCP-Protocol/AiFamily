"""Provider-neutral bridge between Live Control and MediaAdapter sandbox ports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"
LIVE_ATTENDANCE_PURPOSE = "live_attendance"


class MediaBridgeRejected(RuntimeError):
    """The requested control-to-media operation failed closed."""


class MediaProviderUnavailable(MediaBridgeRejected):
    pass


class MediaBindingConflict(MediaBridgeRejected):
    pass


class ReviewStatus(StrEnum):
    APPROVED = "APPROVED"
    DRAFT = "DRAFT"
    WITHDRAWN = "WITHDRAWN"


class SessionStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    ENDED = "ENDED"
    WITHDRAWN = "WITHDRAWN"


class BindingStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class LiveSessionProjection:
    tenant_id: str
    family_id: str
    session_ref: str
    review_status: ReviewStatus
    status: SessionStatus
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if self.source != SANDBOX_SOURCE or not self.fixture_only:
            raise ValueError("control projection must remain synthetic")
        if not all((self.tenant_id, self.family_id, self.session_ref)):
            raise ValueError("control projection identity is required")


@dataclass(frozen=True, slots=True)
class AdultPlaybackContext:
    tenant_id: str
    family_id: str
    guardian_id: str
    purpose: str
    consent_ref: str


@dataclass(frozen=True, slots=True)
class PlaybackCapabilityView:
    token: str
    media_session_ref: str
    family_id: str
    ttl_seconds: int
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


@dataclass(frozen=True, slots=True)
class MediaBinding:
    session_ref: str
    media_session_ref: str
    tenant_id: str
    family_id: str
    provider_ref: str
    status: BindingStatus
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


class MediaRuntimePort(Protocol):
    """MediaAdapter boundary; no business truth is owned by the provider."""

    def start(self, *, session_ref: str, family_id: str, source_ref: str) -> tuple[str, str]: ...

    def issue_playback(
        self, *, media_session_ref: str, family_id: str, ttl_seconds: int
    ) -> PlaybackCapabilityView: ...

    def revoke(self, *, media_session_ref: str, reason: str) -> None: ...


class MediaBindingStorePort(Protocol):
    def find(self, session_ref: str) -> MediaBinding | None: ...

    def command(self, idempotency_key: str) -> tuple[str, MediaBinding] | None: ...

    def commit_started(
        self, *, binding: MediaBinding, idempotency_key: str, fingerprint: str
    ) -> None: ...

    def commit_revoked(
        self, *, binding: MediaBinding, idempotency_key: str, fingerprint: str
    ) -> None: ...


class InMemoryMediaBindingStore:
    """Disposable receipts only; this is not a canonical media or audit ledger."""

    def __init__(self) -> None:
        self.bindings: dict[str, MediaBinding] = {}
        self.commands: dict[str, tuple[str, MediaBinding]] = {}
        self.receipts: list[dict[str, object]] = []
        self.fail_next_commit = False

    def find(self, session_ref: str) -> MediaBinding | None:
        return self.bindings.get(session_ref)

    def command(self, idempotency_key: str) -> tuple[str, MediaBinding] | None:
        return self.commands.get(idempotency_key)

    def commit_started(
        self, *, binding: MediaBinding, idempotency_key: str, fingerprint: str
    ) -> None:
        self._commit(binding, idempotency_key, fingerprint, "MEDIA_BOUND")

    def commit_revoked(
        self, *, binding: MediaBinding, idempotency_key: str, fingerprint: str
    ) -> None:
        self._commit(binding, idempotency_key, fingerprint, "MEDIA_REVOKED")

    def _commit(
        self,
        binding: MediaBinding,
        idempotency_key: str,
        fingerprint: str,
        action: str,
    ) -> None:
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("synthetic binding commit failure")
        self.bindings[binding.session_ref] = binding
        self.commands[idempotency_key] = (fingerprint, binding)
        self.receipts.append(
            {
                "action": action,
                "session_ref": binding.session_ref,
                "media_session_ref": binding.media_session_ref,
                "source": SANDBOX_SOURCE,
                "fixture_only": True,
                "audit_mode": "SANDBOX_RECEIPT_ONLY",
                "external_effect": False,
            }
        )


class ControlMediaBridge:
    """Orchestrate media capabilities from control truth without copying it."""

    def __init__(self, *, media: MediaRuntimePort, store: MediaBindingStorePort) -> None:
        self._media = media
        self._store = store

    def start(
        self,
        *,
        session: LiveSessionProjection,
        source_ref: str,
        operator_id: str,
        idempotency_key: str,
    ) -> MediaBinding:
        if not operator_id.startswith("human:"):
            raise MediaBridgeRejected("only a human live operator may start media")
        self._require_live(session)
        if not source_ref.startswith("synthetic:"):
            raise MediaBridgeRejected("only synthetic media sources are admitted")
        fingerprint = command_fingerprint(
            "START", session.session_ref, session.family_id, source_ref
        )
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay
        if self._store.find(session.session_ref) is not None:
            raise MediaBindingConflict("control session already has a media binding")
        try:
            media_session_ref, provider_ref = self._media.start(
                session_ref=session.session_ref,
                family_id=session.family_id,
                source_ref=source_ref,
            )
        except Exception as exc:
            raise MediaProviderUnavailable("media provider start failed") from exc
        binding = MediaBinding(
            session_ref=session.session_ref,
            media_session_ref=media_session_ref,
            tenant_id=session.tenant_id,
            family_id=session.family_id,
            provider_ref=provider_ref,
            status=BindingStatus.ACTIVE,
        )
        try:
            self._store.commit_started(
                binding=binding,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
        except Exception:
            self._media.revoke(
                media_session_ref=media_session_ref,
                reason="compensate failed control binding commit",
            )
            raise
        return binding

    def authorize_playback(
        self,
        *,
        session: LiveSessionProjection,
        adult: AdultPlaybackContext,
        ttl_seconds: int = 15,
    ) -> PlaybackCapabilityView:
        self._require_live(session)
        if session.tenant_id != adult.tenant_id or session.family_id != adult.family_id:
            raise MediaBridgeRejected("playback crossed tenant/family scope")
        if (
            adult.purpose != LIVE_ATTENDANCE_PURPOSE
            or not adult.consent_ref
            or not adult.guardian_id
        ):
            raise MediaBridgeRejected("active purpose Consent is required")
        binding = self._store.find(session.session_ref)
        if binding is None or binding.status is not BindingStatus.ACTIVE:
            raise MediaBridgeRejected("active media binding is unavailable")
        if binding.family_id != adult.family_id or binding.tenant_id != adult.tenant_id:
            raise MediaBridgeRejected("binding scope mismatch")
        try:
            return self._media.issue_playback(
                media_session_ref=binding.media_session_ref,
                family_id=adult.family_id,
                ttl_seconds=ttl_seconds,
            )
        except Exception as exc:
            raise MediaProviderUnavailable("playback capability unavailable") from exc

    def stop(
        self,
        *,
        session: LiveSessionProjection,
        actor_id: str,
        reason: str,
        idempotency_key: str,
    ) -> MediaBinding:
        if not actor_id.startswith(("human:operator", "human:moderator")):
            raise MediaBridgeRejected("only human operations may stop media")
        if not reason.strip():
            raise ValueError("stop reason is required")
        fingerprint = command_fingerprint("STOP", session.session_ref, session.family_id, reason)
        replay = self._replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay
        binding = self._store.find(session.session_ref)
        if binding is None:
            raise MediaBridgeRejected("media binding is unavailable")
        if binding.tenant_id != session.tenant_id or binding.family_id != session.family_id:
            raise MediaBridgeRejected("binding scope mismatch")
        if binding.status is BindingStatus.REVOKED:
            return binding
        try:
            self._media.revoke(media_session_ref=binding.media_session_ref, reason=reason)
        except Exception as exc:
            raise MediaProviderUnavailable("media revoke failed closed") from exc
        revoked = MediaBinding(
            session_ref=binding.session_ref,
            media_session_ref=binding.media_session_ref,
            tenant_id=binding.tenant_id,
            family_id=binding.family_id,
            provider_ref=binding.provider_ref,
            status=BindingStatus.REVOKED,
        )
        self._store.commit_revoked(
            binding=revoked,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
        return revoked

    def _replay(self, idempotency_key: str, fingerprint: str) -> MediaBinding | None:
        if not idempotency_key:
            raise ValueError("idempotency key is required")
        previous = self._store.command(idempotency_key)
        if previous is None:
            return None
        previous_fingerprint, binding = previous
        if previous_fingerprint != fingerprint:
            raise MediaBindingConflict("idempotency key payload conflict")
        return binding

    @staticmethod
    def _require_live(session: LiveSessionProjection) -> None:
        if session.review_status is not ReviewStatus.APPROVED:
            raise MediaBridgeRejected("session is not approved")
        if session.status is not SessionStatus.LIVE:
            raise MediaBridgeRejected("session is not live")


def command_fingerprint(action: str, session_ref: str, family_id: str, value: str) -> str:
    return sha256(f"{action}:{session_ref}:{family_id}:{value}".encode()).hexdigest()
