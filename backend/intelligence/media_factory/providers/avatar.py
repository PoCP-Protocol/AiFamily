"""AvatarProvider protocol and fail-closed registry."""

from __future__ import annotations

from typing import Protocol

from backend.intelligence.media_factory.contracts import (
    AvatarProviderCapabilities,
    AvatarRenderRequest,
    AvatarRenderResult,
    MediaFactoryError,
)


class AvatarProvider(Protocol):
    """Minimal offline Gate1 provider surface (ADR-0018)."""

    provider_id: str

    @property
    def capabilities(self) -> AvatarProviderCapabilities: ...

    def health(self) -> dict[str, object]: ...

    def prepare(self, *, source_image: object) -> dict[str, object]: ...

    def render(self, request: AvatarRenderRequest) -> AvatarRenderResult: ...


class AvatarProviderRegistry:
    """In-process provider selection. Missing id fails closed."""

    def __init__(self) -> None:
        self._providers: dict[str, AvatarProvider] = {}

    def register(self, provider: AvatarProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> AvatarProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise MediaFactoryError(f"unknown avatar provider: {provider_id}")
        return provider

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
