from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.product_intelligence.api.course_routes import (
    configure_course_system_repository,
    router,
)
from backend.domains.product_intelligence.api.dependencies import get_actor_context
from backend.domains.product_intelligence.application.context import ActorContext
from backend.domains.product_intelligence.domain.course_system import (
    CourseSystem,
    CourseSystemStage,
)
from backend.domains.product_intelligence.infrastructure.course_system_repository import (
    InMemoryCourseSystemRepository,
)


def test_course_system_read_route_is_tenant_scoped() -> None:
    system = CourseSystem(
        system_id="course-system:family-growth",
        version=1,
        tenant_scope="tenant-a",
        product_package_version_ref="product-package:family-growth@v1",
        stages=tuple(
            CourseSystemStage(
                stage_id=f"S{index}",
                title=f"阶段 {index}",
                lesson_start=(index - 1) * 4 + 1,
                lesson_end=index * 4,
                outcome=f"产出 {index}",
            )
            for index in range(1, 7)
        ),
    )
    configure_course_system_repository(InMemoryCourseSystemRepository((system,)))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id="human", actor_type="HUMAN", tenant_scope="tenant-a"
    )
    response = TestClient(app).get(
        "/product-intelligence/courses/system/course-system:family-growth"
    )
    assert response.status_code == 200
    assert response.json()["stages"][-1]["lesson_end"] == 24

    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id="human", actor_type="HUMAN", tenant_scope="tenant-b"
    )
    assert (
        TestClient(app)
        .get("/product-intelligence/courses/system/course-system:family-growth")
        .status_code
        == 404
    )
