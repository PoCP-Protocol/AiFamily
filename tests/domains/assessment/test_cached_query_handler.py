"""Tests for `CachedAssessmentQueryHandler` — cache-hit/miss/TTL-expiry
behavior, and the "cache reads, never writes" boundary (mutation handlers
never receive a cache dependency, so there is nothing to test there beyond
absence — enforced by `AssessmentCommandHandler`'s constructor signature not
accepting one).
"""
from __future__ import annotations

import uuid

import pytest

from backend.domains.assessment.application.commands import (
    AssessmentCommandHandler,
    MutationMeta,
    SaveAssessmentResponseCommand,
    StartAssessmentCommand,
    SubmitAssessmentCommand,
)
from backend.domains.assessment.application.queries import GetUi02ProjectionQuery
from backend.domains.assessment.infrastructure.cached_query_handler import CachedAssessmentQueryHandler
from backend.domains.assessment.infrastructure.deterministic_interpretation import DeterministicInterpretationAdapter
from backend.domains.assessment.infrastructure.fake_cache import FakeQueryCache
from backend.domains.assessment.infrastructure.fake_repository import FakeAssessmentRepository

TENANT_ID = "tenant-1"


def _meta(key: str) -> MutationMeta:
    return MutationMeta(correlation_id="corr-1", idempotency_key=key, source="test")


@pytest.fixture
def repo() -> FakeAssessmentRepository:
    repository = FakeAssessmentRepository()
    family_id = str(uuid.uuid4())
    repository.seed_family(TENANT_ID, family_id)
    child_id = str(uuid.uuid4())
    repository.seed_subject(family_id, child_id, "小明")
    repository._test_family_id = family_id  # type: ignore[attr-defined]
    repository._test_child_id = child_id  # type: ignore[attr-defined]
    return repository


@pytest.fixture
def cache() -> FakeQueryCache:
    return FakeQueryCache()


@pytest.fixture
def cached_handler(repo, cache) -> CachedAssessmentQueryHandler:
    return CachedAssessmentQueryHandler(repo, DeterministicInterpretationAdapter(), cache, ttl_seconds=30)


class _CountingRepositoryWrapper:
    """Wraps a repository and counts calls to `load_assessable_subjects`, a
    representative real-query call inside `get_ui02_projection`, to prove
    cache hits skip the underlying query entirely.
    """

    def __init__(self, inner: FakeAssessmentRepository):
        self._inner = inner
        self.load_assessable_subjects_call_count = 0

    async def load_assessable_subjects(self, family_id: str):
        self.load_assessable_subjects_call_count += 1
        return await self._inner.load_assessable_subjects(family_id)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TestCachedQueryHandler:
    async def test_cache_miss_then_hit_skips_underlying_query(self, repo, cache):
        counting_repo = _CountingRepositoryWrapper(repo)
        handler = CachedAssessmentQueryHandler(counting_repo, DeterministicInterpretationAdapter(), cache, ttl_seconds=30)
        query = GetUi02ProjectionQuery(repo._test_family_id, TENANT_ID, "actor-1")

        first = await handler.get_ui02_projection(query)
        assert counting_repo.load_assessable_subjects_call_count == 1

        second = await handler.get_ui02_projection(query)
        assert counting_repo.load_assessable_subjects_call_count == 1  # cache hit — no second query
        assert second == first

    async def test_ttl_expiry_forces_fresh_query(self, repo, cache):
        counting_repo = _CountingRepositoryWrapper(repo)
        handler = CachedAssessmentQueryHandler(counting_repo, DeterministicInterpretationAdapter(), cache, ttl_seconds=30)
        query = GetUi02ProjectionQuery(repo._test_family_id, TENANT_ID, "actor-1")

        await handler.get_ui02_projection(query)
        assert counting_repo.load_assessable_subjects_call_count == 1

        cache.advance_time(31)
        await handler.get_ui02_projection(query)
        assert counting_repo.load_assessable_subjects_call_count == 2  # TTL expired — fresh query

    async def test_cache_is_scoped_per_tenant_and_family(self, repo, cache):
        counting_repo = _CountingRepositoryWrapper(repo)
        handler = CachedAssessmentQueryHandler(counting_repo, DeterministicInterpretationAdapter(), cache, ttl_seconds=30)
        other_family_id = str(uuid.uuid4())
        repo.seed_family(TENANT_ID, other_family_id)

        await handler.get_ui02_projection(GetUi02ProjectionQuery(repo._test_family_id, TENANT_ID, "actor-1"))
        await handler.get_ui02_projection(GetUi02ProjectionQuery(other_family_id, TENANT_ID, "actor-1"))
        assert counting_repo.load_assessable_subjects_call_count == 2  # different cache keys, both miss

    async def test_stale_cache_does_not_reflect_writes_within_ttl_window(self, repo, cache):
        """Documents the accepted tradeoff: a write inside the TTL window is
        NOT reflected until the cache expires. This is the passive-expiry
        design's known staleness bound, asserted explicitly rather than left
        implicit — see module docstring for the justification.
        """
        command_handler = AssessmentCommandHandler(repo)
        cached_handler = CachedAssessmentQueryHandler(repo, DeterministicInterpretationAdapter(), cache, ttl_seconds=30)
        query = GetUi02ProjectionQuery(repo._test_family_id, TENANT_ID, "actor-1")

        before = await cached_handler.get_ui02_projection(query)
        assert len(before["sessions"]) == 0

        await command_handler.start(
            StartAssessmentCommand(repo._test_family_id, TENANT_ID, "actor-1", repo._test_child_id, None, _meta("w1"))
        )

        stale = await cached_handler.get_ui02_projection(query)
        assert len(stale["sessions"]) == 0  # still stale — within TTL window, by design

        cache.advance_time(31)
        fresh = await cached_handler.get_ui02_projection(query)
        assert len(fresh["sessions"]) == 1  # after TTL expiry, reflects the write
