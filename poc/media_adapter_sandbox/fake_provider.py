"""A local provider double that accepts only synthetic media fixtures."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from poc.media_adapter_sandbox.contract import FaultKind, ProviderFailure, SyntheticSource
from poc.media_adapter_sandbox.fault_injector import FaultInjector


@dataclass(frozen=True, slots=True)
class ProviderHandle:
    provider_ref: str
    media_session_ref: str
    media_bytes: bytes
    sha256: str


class FakeMediaProvider:
    """In-process provider: no network, no credentials, no external side effects."""

    provider_ref = "fake-provider-synthetic"

    def __init__(self, faults: FaultInjector | None = None) -> None:
        self.faults = faults or FaultInjector()
        self._handles: dict[str, ProviderHandle] = {}

    def ingest(self, media_session_ref: str, source: SyntheticSource) -> ProviderHandle:
        source.validate()
        if self.faults.enabled(FaultKind.PROVIDER_FAILURE):
            raise ProviderFailure("synthetic provider failure injected")
        media_bytes = source.path.read_bytes()
        handle = ProviderHandle(
            provider_ref=self.provider_ref,
            media_session_ref=media_session_ref,
            media_bytes=media_bytes,
            sha256=hashlib.sha256(media_bytes).hexdigest(),
        )
        self._handles[media_session_ref] = handle
        return handle

    def media_bytes(self, media_session_ref: str) -> bytes:
        try:
            return self._handles[media_session_ref].media_bytes
        except KeyError as exc:
            raise ProviderFailure("provider has no admitted media session") from exc

    def remove(self, media_session_ref: str) -> None:
        self._handles.pop(media_session_ref, None)
