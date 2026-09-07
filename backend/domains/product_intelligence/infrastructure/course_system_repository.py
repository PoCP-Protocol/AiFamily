"""Explicitly design-time in-memory CourseSystem read model."""

from __future__ import annotations

from ..domain.course_system import CourseSystem
from ..domain.errors import ProductIntelligenceNotFoundError


class InMemoryCourseSystemRepository:
    def __init__(self, systems: tuple[CourseSystem, ...] = ()) -> None:
        self._by_key = {(system.tenant_scope, system.system_id): system for system in systems}

    async def load_course_system(self, system_id: str, tenant_scope: str) -> CourseSystem:
        system = self._by_key.get((tenant_scope, system_id))
        if system is None:
            raise ProductIntelligenceNotFoundError("course_system_not_found")
        return system


__all__ = ["InMemoryCourseSystemRepository"]
