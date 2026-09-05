"""Course-content-backed implementation of `SupplyReferencePort`.

Read-only, mirroring `commerce_supply_adapter.py` / `service_supply_adapter.py`.
This adapter never authors, submits, or reviews a `CourseContent`; it only
translates an already-`PUBLISHED` course into the family_need domain's own
`SolutionComponentRef`.

It depends only on the read-side `list_published_course_content` callable
(the same query `product_intelligence.application.course_publication`
exposes), never on a concrete repository, so the choice of persistence stays
with whoever wires this adapter (`dev_wiring.py` / production wiring).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ..domain.value_objects import ResourceGap, ResourceGapReason, SolutionComponentRef, SupplyShape

if TYPE_CHECKING:
    from ...product_intelligence.domain.course_content import CourseContent

# A `CourseContent` has no "shape" field at all — it is always course
# content. SOLUTION is the only family_need shape this adapter answers,
# distinguishing a multi-lesson course from a single PRODUCT or SERVICE.
_SUPPORTED_SHAPES = frozenset({SupplyShape.SOLUTION})


class PublishedCourseContentQuery(Protocol):
    """Read-only seam this adapter depends on, not a repository type.

    Matches `product_intelligence.application.course_publication
    .list_published_course_content`'s return shape without importing that
    module's `CourseContentRepository` protocol or any concrete repository.
    """

    async def __call__(self) -> list[CourseContent]: ...


class CourseSupplyAdapter:
    """Resolves `SupplyShape.SOLUTION` references against published courses."""

    def __init__(self, list_published_courses: PublishedCourseContentQuery) -> None:
        self._list_published_courses = list_published_courses

    async def resolve_component(
        self,
        *,
        tenant_id: str,
        region: str,
        locale: str,
        shape: SupplyShape,
        component_id: str,
        version: str,
    ) -> SolutionComponentRef | None:
        del tenant_id, region, locale  # not modelled by the course read model today.
        if shape not in _SUPPORTED_SHAPES:
            return None

        course = await self._find_published_course(component_id)
        if course is None:
            return None
        if version and str(course.version) != version:
            return None

        return SolutionComponentRef(
            component_id=course.id,
            shape=SupplyShape.SOLUTION,
            version=str(course.version),
        )

    async def check_resource_capacity(
        self,
        *,
        tenant_id: str,
        family_id: str,
        need_id: str = "",
        component_refs: tuple[SolutionComponentRef, ...],
    ) -> ResourceGap | None:
        del tenant_id, family_id
        published_by_id = {course.id: course for course in await self._list_published_courses()}
        for component_ref in component_refs:
            if component_ref.shape is not SupplyShape.SOLUTION:
                continue
            course = published_by_id.get(component_ref.component_id)
            if course is None or course.status != "PUBLISHED":
                return ResourceGap.now(
                    need_id,
                    ResourceGapReason.NO_CAPACITY,
                    f"course_content_not_available:{component_ref.component_id}",
                )
        return None

    async def get_resource_gap(
        self, *, need_id: str, reason: ResourceGapReason, detail: str
    ) -> ResourceGap:
        return ResourceGap.now(need_id, reason, detail)

    async def _find_published_course(self, component_id: str) -> CourseContent | None:
        courses = await self._list_published_courses()
        for course in courses:
            if course.id == component_id and course.status == "PUBLISHED":
                return course
        return None


__all__ = ["CourseSupplyAdapter", "PublishedCourseContentQuery"]
