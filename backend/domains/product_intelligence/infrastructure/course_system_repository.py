"""Explicitly design-time in-memory CourseSystem read model."""

from __future__ import annotations

from ..domain.course_system import CourseSystem, CourseSystemStage
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


def development_course_system_repository() -> InMemoryCourseSystemRepository:
    """Return explicitly design-time data for local Web/API development."""
    system = CourseSystem(
        system_id="course-system:family-growth",
        version=1,
        tenant_scope="dev-tenant",
        product_package_version_ref="product-package:family-growth@v1",
        stages=tuple(
            CourseSystemStage(
                stage_id=f"S{index}",
                title=title,
                lesson_start=(index - 1) * 4 + 1,
                lesson_end=index * 4,
                outcome=outcome,
            )
            for index, (title, outcome) in enumerate(
                (
                    ("家庭觉察", "家庭问题地图"),
                    ("关系连接", "沟通与关系行动卡"),
                    ("成长目标", "家庭成长目标树"),
                    ("日常行动", "21 天行动计划"),
                    ("能力进阶", "90 天成长路径"),
                    ("复盘共创", "复盘报告与下一周期需求"),
                ),
                start=1,
            )
        ),
    )
    return InMemoryCourseSystemRepository((system,))


__all__ = ["InMemoryCourseSystemRepository", "development_course_system_repository"]
