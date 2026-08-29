"""Read-side cache decorator for `AssessmentQueryHandler` — per
`architecture/SHARDING_KEY_REGISTRY.md` "Read/write separation + caching":
wraps only the two highest-frequency read projections (UI-02/UI-03), never
touches mutation paths. Passive short-TTL expiry, not active invalidation on
write — justified below.

Why passive expiry, not active invalidation on write:
Assessment writes (start/save_response/submit/decide) are low-frequency
relative to reads (a parent submits an assessment once per session; the
UI-02/UI-03 projection may be polled/re-rendered many times while composing
answers or reviewing a hypothesis). Actively invalidating on every write
would require the mutation handlers to know about the cache (violating the
"cache reads, never writes" boundary — mutation code would need a cache
dependency it otherwise has no reason to hold) and adds a failure mode
(cache invalidation missed → stale read) that is strictly worse than a
bounded staleness window. A short TTL (default 30s) bounds the staleness to
a window well under what a family would notice as "my answer didn't save",
while keeping the mutation handlers cache-agnostic.
"""
from __future__ import annotations

from ..application.ports import AssessmentInterpretationPort, AssessmentRepositoryPort
from ..application.queries import AssessmentQueryHandler, GetUi02ProjectionQuery, GetUi03ProjectionQuery
from ..application.query_cache_port import QueryCachePort

DEFAULT_TTL_SECONDS = 30


def _ui02_cache_key(tenant_id: str, family_id: str) -> str:
    return f"assessment:ui02:{tenant_id}:{family_id}"


def _ui03_cache_key(tenant_id: str, family_id: str) -> str:
    return f"assessment:ui03:{tenant_id}:{family_id}"


class CachedAssessmentQueryHandler:
    """Same public interface as `AssessmentQueryHandler` — callers (the API
    layer) depend on this or the uncached handler interchangeably.
    """

    def __init__(
        self,
        repository: AssessmentRepositoryPort,
        interpretation: AssessmentInterpretationPort,
        cache: QueryCachePort,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ):
        self._inner = AssessmentQueryHandler(repository, interpretation)
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    async def get_ui02_projection(self, query: GetUi02ProjectionQuery) -> dict:
        key = _ui02_cache_key(query.tenant_id, query.family_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached
        result = await self._inner.get_ui02_projection(query)
        await self._cache.set(key, result, self._ttl_seconds)
        return result

    async def get_ui03_projection(self, query: GetUi03ProjectionQuery) -> dict:
        key = _ui03_cache_key(query.tenant_id, query.family_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached
        result = await self._inner.get_ui03_projection(query)
        await self._cache.set(key, result, self._ttl_seconds)
        return result
