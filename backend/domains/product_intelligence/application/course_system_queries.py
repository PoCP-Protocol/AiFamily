"""Queries for the design-time course-system read model."""

from __future__ import annotations

from typing import Protocol

from ..domain.course_system import CourseSystem
from ..domain.errors import ProductIntelligenceNotFoundError


class CourseSystemRepository(Protocol):
    async def load_course_system(self, system_id: str, tenant_scope: str) -> CourseSystem: ...


async def get_course_system(
    repository: CourseSystemRepository, *, system_id: str, tenant_scope: str
) -> CourseSystem:
    try:
        return await repository.load_course_system(system_id, tenant_scope)
    except ProductIntelligenceNotFoundError:
        raise


__all__ = ["CourseSystemRepository", "get_course_system"]
