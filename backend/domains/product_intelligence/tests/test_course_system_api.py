from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.product_intelligence.api.course_routes import (
    configure_course_content_gate,
    configure_course_content_repository,
    configure_course_system_repository,
    router,
)
from backend.domains.product_intelligence.api.dependencies import get_actor_context
from backend.domains.product_intelligence.application.context import ActorContext
from backend.domains.product_intelligence.domain.course_content import CourseContent, CourseLesson
from backend.domains.product_intelligence.domain.course_system import (
    CourseSystem,
    CourseSystemStage,
)
from backend.domains.product_intelligence.infrastructure.course_content_repository import (
    InMemoryCourseContentRepository,
)
from backend.domains.product_intelligence.infrastructure.course_system_repository import (
    InMemoryCourseSystemRepository,
)
from backend.intelligence.human_gate.gate import InMemoryHumanGate


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
    assert [
        (item["kind"], item["duration_days"], len(item["lesson_sequences"]))
        for item in response.json()["journey_bindings"]
    ] == [
        ("MICRO_CAMP", 21, 16),
        ("SCALE_PLAN", 90, 24),
    ]

    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id="human", actor_type="HUMAN", tenant_scope="tenant-b"
    )
    assert (
        TestClient(app)
        .get("/product-intelligence/courses/system/course-system:family-growth")
        .status_code
        == 404
    )


def test_course_draft_route_rejects_invalid_lineage_with_400() -> None:
    configure_course_content_repository(InMemoryCourseContentRepository())
    configure_course_content_gate(InMemoryHumanGate())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id="author",
        actor_type="HUMAN",
        tenant_scope="tenant-a",
        permissions=frozenset({"product_intelligence.course_content.author"}),
    )
    body = {
        "title": "课程",
        "problem_statement": "问题",
        "assessment_criteria": ["标准"],
        "learning_goal": "目标",
        "review_cadence": "每6节",
        "outcome_metrics": ["指标"],
        "content_accuracy_claim_refs": ["claim:1"],
        "course_system_version_ref": "course-system:family-growth@v1",
        "lessons": [
            {
                "lesson_id": f"lesson-{index:02d}",
                "sequence": index,
                "title": f"课时{index}",
                "knowledge_point": "知识",
                "action_task": "行动",
                "stage_id": f"S{(index - 1) // 4 + 1}",
                "bom_line_ref": f"courseware:family-growth:lesson-{index:02d}@v2"
                if index == 1
                else f"courseware:family-growth:lesson-{index:02d}@v1",
            }
            for index in range(1, 25)
        ],
    }
    response = TestClient(app).post("/product-intelligence/courses", json=body)
    assert response.status_code == 400
    assert response.json()["detail"] == "course_content_lesson_lineage_invalid"


def test_delivery_projection_route_returns_ready_for_complete_published_course() -> None:
    now = datetime.now(UTC)
    course = CourseContent(
        id="course-24",
        version=1,
        status="PUBLISHED",
        tenant_scope="tenant-a",
        created_by="author",
        created_at=now,
        updated_at=now,
        title="24课",
        course_system_version_ref="course-system:family-growth@v1",
        problem_statement="问题",
        assessment_criteria=("标准",),
        learning_goal="目标",
        lessons=tuple(
            CourseLesson(
                lesson_id=f"lesson-{index}",
                sequence=index,
                title=f"课时{index}",
                knowledge_point="知识",
                action_task="行动",
                media_asset_ids=(f"asset-{index}",),
                stage_id=f"S{(index - 1) // 4 + 1}",
                bom_line_ref=f"courseware:family-growth:lesson-{index:02d}@v1",
            )
            for index in range(1, 25)
        ),
        review_cadence="每周",
        outcome_metrics=("指标",),
        content_accuracy_claim_refs=("claim:1",),
        reviewed_by="reviewer",
        reviewed_at=now,
        review_reason="通过",
        published_at=now,
    )
    repository = InMemoryCourseContentRepository()
    import asyncio

    asyncio.run(repository.save_course_content(course))
    configure_course_content_repository(repository)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id="human", actor_type="HUMAN", tenant_scope="tenant-a"
    )
    response = TestClient(app).get("/product-intelligence/courses/course-24/delivery-projection")
    assert response.status_code == 200
    assert response.json()["ready_lessons"] == 24
    assert response.json()["publishable_to_service"] is True

    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id="other-human", actor_type="HUMAN", tenant_scope="tenant-b"
    )
    forbidden = TestClient(app).get("/product-intelligence/courses/course-24/delivery-projection")
    assert forbidden.status_code == 404
