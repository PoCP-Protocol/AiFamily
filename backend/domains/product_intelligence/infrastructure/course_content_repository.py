"""In-memory `CourseContentRepository` — dev/test wiring, not production.

No SQLAlchemy mapping exists yet for `CourseContent` (this PR stands up the
aggregate and its Human Gate lifecycle; a durable mapping is separate,
tracked follow-up work, the same "route mounted, persistence pending"
posture `dependencies.py::get_repository` already documents for the rest of
this domain). Process-local storage here mirrors
`apps/family_api/dev_wiring.py`'s `FakeServiceRepository` convention: one
instance per process so a draft submitted by one request is visible to the
next.
"""

from __future__ import annotations

from ..domain.course_content import CourseContent
from ..domain.errors import ProductIntelligenceNotFoundError


class InMemoryCourseContentRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, CourseContent] = {}

    async def save_course_content(self, course: CourseContent) -> None:
        self._by_id[course.id] = course

    async def load_course_content(self, course_id: str, tenant_scope: str) -> CourseContent:
        course = self._by_id.get(course_id)
        if course is None or course.tenant_scope != tenant_scope:
            raise ProductIntelligenceNotFoundError("course_content_not_found")
        return course

    async def list_published_course_content(self, tenant_scope: str) -> list[CourseContent]:
        return [
            course
            for course in self._by_id.values()
            if course.tenant_scope == tenant_scope and course.status == "PUBLISHED"
        ]


__all__ = ["InMemoryCourseContentRepository"]
