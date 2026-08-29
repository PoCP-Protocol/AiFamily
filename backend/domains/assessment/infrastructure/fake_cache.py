"""In-memory fake cache — test double for `QueryCachePort`. Supports a
controllable clock so tests can assert TTL expiry without real sleeps.
Not for production use — the real adapter (Redis) is a separate,
un-implemented follow-up (see task report); this fake exists only to let
`CachedAssessmentQueryHandler`'s cache-hit/cache-miss/TTL-expiry behavior be
unit-tested now, per migration plan's "FakeProvider" requirement.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeQueryCache:
    _store: dict[str, tuple[dict, float]] = field(default_factory=dict)  # key -> (value, expires_at)
    _now: float = 0.0

    def advance_time(self, seconds: float) -> None:
        self._now += seconds

    async def get(self, key: str) -> dict | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if self._now >= expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        self._store[key] = (value, self._now + ttl_seconds)
