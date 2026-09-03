"""Course content: create draft -> submit for review -> human decides ->
published course is queryable.

Covers the chain the task description asks for in business terms: "能不能
真的写一门课的草稿，让它过审核流程，最终查到一门'已发布'的课". Exercised at
both the application-service layer (direct calls) and the HTTP layer
(mounted via `create_app()` dev wiring), so a regression in either the
domain rules or the route wiring is caught.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.domains.product_intelligence.application.context import ActorContext
from backend.domains.product_intelligence.application.course_publication import (
    COURSE_CONTENT_AUTHOR_PERMISSION,
    COURSE_CONTENT_REVIEW_PERMISSION,
    create_course_content_draft,
    decide_course_content_review,
    list_published_course_content,
    submit_course_content_for_review,
)
from backend.domains.product_intelligence.domain.course_content import CourseLesson
from backend.domains.product_intelligence.domain.errors import (
    ProductIntelligenceForbiddenError,
    ProductIntelligenceValidationError,
)
from backend.domains.product_intelligence.infrastructure.course_content_repository import (
    InMemoryCourseContentRepository,
)
from backend.intelligence.human_gate.gate import InMemoryHumanGate


def _lesson(sequence: int = 1) -> CourseLesson:
    return CourseLesson(
        lesson_id=f"lesson-{sequence}",
        sequence=sequence,
        title="第一课：认识情绪",
        knowledge_point="情绪没有对错，只有需要被看见",
        action_task="今晚请孩子用一句话说出今天的心情",
    )


def _author_context(tenant: str = "tenant-a") -> ActorContext:
    return ActorContext(
        actor_id="author-1",
        actor_type="HUMAN",
        tenant_scope=tenant,
        permissions=frozenset({COURSE_CONTENT_AUTHOR_PERMISSION}),
    )


def _reviewer_context(tenant: str = "tenant-a") -> ActorContext:
    return ActorContext(
        actor_id="reviewer-1",
        actor_type="HUMAN",
        tenant_scope=tenant,
        permissions=frozenset({COURSE_CONTENT_REVIEW_PERMISSION}),
    )


async def _create_draft(repo, context):
    return await create_course_content_draft(
        repo,
        context,
        title="21天亲子情绪陪伴课",
        problem_statement="家长常常不知道如何回应孩子的情绪表达",
        assessment_criteria=["家长能识别孩子三种基本情绪信号"],
        learning_goal="家长掌握一套简单可持续的情绪陪伴动作",
        lessons=[_lesson(1), _lesson(2)],
        review_cadence="每周复盘一次",
        outcome_metrics=["家庭情绪对话频次提升"],
        content_accuracy_claim_refs=["evidence-claim:content-accuracy:1"],
    )


class TestCourseContentApplicationChain:
    async def test_draft_review_publish_and_list_published(self) -> None:
        repo = InMemoryCourseContentRepository()
        gate = InMemoryHumanGate()

        draft = await _create_draft(repo, _author_context())
        assert draft.status == "DRAFT"

        submission = await submit_course_content_for_review(
            repo, gate, _author_context(), course_content_id=draft.id
        )
        assert submission.course.status == "UNDER_REVIEW"
        assert submission.task.status == "OPEN"

        decision = await decide_course_content_review(
            repo,
            gate,
            _reviewer_context(),
            task_id=submission.task.task_id,
            course_content_id=draft.id,
            approved=True,
            reason="内容核验通过，可以发布",
        )
        assert decision.course.status == "PUBLISHED"
        assert decision.course.published_at is not None

        published = await list_published_course_content(repo, _author_context())
        assert [course.id for course in published] == [draft.id]

    async def test_review_requires_review_permission_not_author_permission(self) -> None:
        repo = InMemoryCourseContentRepository()
        gate = InMemoryHumanGate()
        draft = await _create_draft(repo, _author_context())
        submission = await submit_course_content_for_review(
            repo, gate, _author_context(), course_content_id=draft.id
        )
        with pytest.raises(ProductIntelligenceForbiddenError):
            await decide_course_content_review(
                repo,
                gate,
                _author_context(),  # author, not reviewer
                task_id=submission.task.task_id,
                course_content_id=draft.id,
                approved=True,
                reason="尝试越权发布",
            )

    async def test_rejected_review_returns_course_to_draft_not_published(self) -> None:
        repo = InMemoryCourseContentRepository()
        gate = InMemoryHumanGate()
        draft = await _create_draft(repo, _author_context())
        submission = await submit_course_content_for_review(
            repo, gate, _author_context(), course_content_id=draft.id
        )
        decision = await decide_course_content_review(
            repo,
            gate,
            _reviewer_context(),
            task_id=submission.task.task_id,
            course_content_id=draft.id,
            approved=False,
            reason="内容准确性证据不足",
        )
        assert decision.course.status == "DRAFT"
        published = await list_published_course_content(repo, _author_context())
        assert published == []

    async def test_lessons_required_and_content_accuracy_claim_refs_required(self) -> None:
        repo = InMemoryCourseContentRepository()
        with pytest.raises(ProductIntelligenceValidationError):
            await create_course_content_draft(
                repo,
                _author_context(),
                title="缺章节的课程",
                problem_statement="问题陈述",
                assessment_criteria=["标准一"],
                learning_goal="目标",
                lessons=[],
                review_cadence="每周",
                outcome_metrics=["指标一"],
                content_accuracy_claim_refs=["evidence-claim:1"],
            )
        with pytest.raises(ProductIntelligenceValidationError):
            await create_course_content_draft(
                repo,
                _author_context(),
                title="缺证据的课程",
                problem_statement="问题陈述",
                assessment_criteria=["标准一"],
                learning_goal="目标",
                lessons=[_lesson(1)],
                review_cadence="每周",
                outcome_metrics=["指标一"],
                content_accuracy_claim_refs=[],
            )

    async def test_published_list_is_tenant_scoped(self) -> None:
        repo = InMemoryCourseContentRepository()
        gate = InMemoryHumanGate()
        draft = await _create_draft(repo, _author_context("tenant-a"))
        submission = await submit_course_content_for_review(
            repo, gate, _author_context("tenant-a"), course_content_id=draft.id
        )
        await decide_course_content_review(
            repo,
            gate,
            _reviewer_context("tenant-a"),
            task_id=submission.task.task_id,
            course_content_id=draft.id,
            approved=True,
            reason="通过",
        )
        other_tenant_published = await list_published_course_content(
            repo, _author_context("tenant-b")
        )
        assert other_tenant_published == []


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "dev")


def test_http_chain_draft_submit_review_and_published_listing() -> None:
    from backend.apps.family_api.dev_wiring import reset_dev_state
    from backend.apps.family_api.main import create_app

    reset_dev_state()
    client = TestClient(create_app())

    draft_body = {
        "title": "90天成长陪伴计划",
        "problem_statement": "家庭缺少可持续的成长陪伴节奏",
        "assessment_criteria": ["家庭能坚持每周复盘"],
        "learning_goal": "建立每周固定的家庭成长复盘习惯",
        "lessons": [
            {
                "lesson_id": "lesson-1",
                "sequence": 1,
                "title": "第一课：设定家庭小目标",
                "knowledge_point": "小目标比大目标更容易坚持",
                "action_task": "本周设定一个五分钟就能做到的小目标",
            }
        ],
        "review_cadence": "每周一次",
        "outcome_metrics": ["家庭复盘完成率"],
        "content_accuracy_claim_refs": ["evidence-claim:content-accuracy:http-1"],
    }
    create_response = client.post("/product-intelligence/courses", json=draft_body)
    assert create_response.status_code == 200, create_response.text
    course_id = create_response.json()["id"]
    assert create_response.json()["status"] == "DRAFT"

    submit_response = client.post(
        f"/product-intelligence/courses/{course_id}/submit-for-review", json={}
    )
    assert submit_response.status_code == 200, submit_response.text
    assert submit_response.json()["course"]["status"] == "UNDER_REVIEW"
    task_id = submit_response.json()["task_id"]

    decide_response = client.post(
        f"/product-intelligence/courses/{course_id}/review-decision",
        json={"task_id": task_id, "approved": True, "reason": "内容核验通过"},
    )
    assert decide_response.status_code == 200, decide_response.text
    assert decide_response.json()["course"]["status"] == "PUBLISHED"

    published_response = client.get("/product-intelligence/courses/published")
    assert published_response.status_code == 200, published_response.text
    published_ids = [item["id"] for item in published_response.json()]
    assert course_id in published_ids

    get_response = client.get(f"/product-intelligence/courses/{course_id}")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "PUBLISHED"
