"""Cache port — the application layer depends on this Protocol, never on a
concrete Redis client. Per
`architecture/SHARDING_KEY_REGISTRY.md` ("cache reads, never writes"), only
read projections use this; mutation handlers never touch it.
"""
from __future__ import annotations

from typing import Protocol


class QueryCachePort(Protocol):
    async def get(self, key: str) -> dict | None: ...

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None: ...
