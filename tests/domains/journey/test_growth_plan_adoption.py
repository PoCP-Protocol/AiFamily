from __future__ import annotations

from dataclasses import replace

import pytest

from backend.domains.journey.application.growth_plan_adoption import (
    AdoptedGrowthPlan,
    AdoptGrowthPlanCommand,
    GrowthPlanActor,
    GrowthPlanAdoptionService,
    GuardianGrowthPlanPolicy,
    ValidatedGrowthPlanDraft,
)
from backend.domains.journey.domain.errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
)


class DraftReader:
    def __init__(self, draft: ValidatedGrowthPlanDraft | None) -> None:
        self.draft = draft

    async def load_validated_draft(self, **_: object) -> ValidatedGrowthPlanDraft | None:
        return self.draft


class Repository:
    def __init__(self) -> None:
        self.current: AdoptedGrowthPlan | None = None
        self.receipts: dict[str, tuple[str, AdoptedGrowthPlan]] = {}

    async def get_current(self, **_: str) -> AdoptedGrowthPlan | None:
        return self.current

    async def adopt_once(
        self,
        *,
        plan: AdoptedGrowthPlan,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> tuple[AdoptedGrowthPlan, bool, bool]:
        receipt = self.receipts.get(idempotency_key)
        if receipt:
            fingerprint, stored = receipt
            if fingerprint != request_fingerprint:
                raise JourneyConflictError("idempotency_conflict")
            return stored, True, True
        if self.current and self.current.draft_ref != plan.draft_ref:
            raise JourneyConflictError("active_growth_plan_already_exists")
        self.current = self.current or plan
        self.receipts[idempotency_key] = (request_fingerprint, self.current)
        return self.current, self.current is plan, False


def plan_output() -> dict:
    return {
        "result_status": "PLAN_DRAFT",
        "information_needed": [],
        "title": "把晚间冲突变成可以共同商量的家庭节奏",
        "family_goal": {
            "statement": "晚间学习安排能在不升级争执的情况下完成协商",
            "observable_signs": ["家长先听完再回应"],
            "evidence_refs": ["evidence:conversation-1"],
        },
        "why_this_plan": "家庭已经有一次成功协商经验，方案从复制例外经验开始。",
        "duration": {"days": 35, "rationale": "需要跨过五个完整的学习周观察稳定性。"},
        "stages": [
            {
                "stage_id": "listen-before-plan",
                "title": "先理解分歧发生在哪里",
                "purpose": "让双方对问题形成共同语言",
                "practices": [{"description": "晚饭后由家长完整听孩子讲一次当天最难的安排"}],
                "child_participation_mode": "OPTIONAL",
                "signals": [{"signal_type": "OUTCOME", "description": "能复述彼此关注"}],
                "reflection_question": "哪一次对话没有进入争辩？",
                "evidence_refs": ["evidence:conversation-1"],
                "knowledge_refs": ["knowledge:active-listening:v3"],
            },
            {
                "stage_id": "co-design-rhythm",
                "title": "共同设计可执行节奏",
                "purpose": "形成双方都愿意尝试的安排",
                "practices": [{"description": "共同选择一个最容易发生冲突的时间点重新设计"}],
                "child_participation_mode": "ASSENT_REQUIRED",
                "signals": [{"signal_type": "STOP", "description": "对话明显升级时暂停"}],
                "reflection_question": "哪些安排真正减轻了双方负担？",
                "evidence_refs": ["evidence:conversation-1"],
                "knowledge_refs": ["knowledge:collaborative-problem-solving:v2"],
            },
        ],
        "adjustable_choices": [
            {
                "choice_id": "meeting-time",
                "question": "家庭更愿意在哪个时间复盘？",
                "options": ["周五晚", "周日午后"],
                "target_stage_ids": ["co-design-rhythm"],
            }
        ],
        "unknowns_to_watch": ["冲突是否集中在疲劳程度较高的日期"],
        "review_rhythm": {"frequency": "每周一次", "questions": ["什么有效？", "什么要调整？"]},
        "limitations": ["当前只基于家长确认的信息与已审核知识"],
    }


def draft(**changes: object) -> ValidatedGrowthPlanDraft:
    value = ValidatedGrowthPlanDraft(
        draft_ref="draft:family-a:1",
        version=3,
        tenant_id="tenant-a",
        family_id="family-a",
        subject_refs=("guardian-a", "child-a"),
        status="VALIDATED_DRAFT",
        model_run_ref="model-run:42",
        provenance_ref="provenance:42",
        content_sha256="a" * 64,
        output=plan_output(),
    )
    return replace(value, **changes)


def service(value: ValidatedGrowthPlanDraft | None) -> tuple[GrowthPlanAdoptionService, Repository]:
    repository = Repository()
    return (
        GrowthPlanAdoptionService(DraftReader(value), repository, GuardianGrowthPlanPolicy()),
        repository,
    )


@pytest.mark.asyncio
async def test_guardian_adopts_dynamic_generated_draft_and_reads_it_back() -> None:
    application, _ = service(draft())
    actor = GrowthPlanActor("guardian-a", "tenant-a", "family-a")
    response = await application.adopt(
        AdoptGrowthPlanCommand(actor, "draft:family-a:1", 3, "adopt-1")
    )

    assert response["created"] is True
    assert response["plan"]["duration"] == {
        "days": 35,
        "rationale": "需要跨过五个完整的学习周观察稳定性。",
    }
    assert [stage["stage_id"] for stage in response["plan"]["stages"]] == [
        "listen-before-plan",
        "co-design-rhythm",
    ]
    assert response["plan"]["boundary"] == "HUMAN_ADOPTED_GENERATIVE_DRAFT_NOT_AI_CREATED_FACT"
    assert (await application.get_current(actor))["plan"]["draft_version"] == 3


@pytest.mark.asyncio
async def test_adoption_replays_same_request_and_rejects_key_reuse_for_another_version() -> None:
    application, _ = service(draft())
    actor = GrowthPlanActor("guardian-a", "tenant-a", "family-a")
    command = AdoptGrowthPlanCommand(actor, "draft:family-a:1", 3, "adopt-1")
    first = await application.adopt(command)
    replay = await application.adopt(command)

    assert replay["plan"]["plan_id"] == first["plan"]["plan_id"]
    assert replay["idempotency_replayed"] is True

    with pytest.raises(JourneyConflictError, match="idempotency_conflict"):
        await application.adopt(replace(command, draft_version=4))


@pytest.mark.asyncio
async def test_scope_human_gate_and_validated_draft_are_fail_closed() -> None:
    actor = GrowthPlanActor("guardian-a", "tenant-a", "family-a")
    missing, _ = service(None)
    with pytest.raises(JourneyNotFoundError):
        await missing.adopt(AdoptGrowthPlanCommand(actor, "missing", 1, "adopt-1"))

    wrong_scope, _ = service(draft(family_id="family-b"))
    with pytest.raises(JourneyForbiddenError, match="growth_plan_draft_scope_denied"):
        await wrong_scope.adopt(AdoptGrowthPlanCommand(actor, "draft:family-a:1", 3, "adopt-2"))

    ai_actor, _ = service(draft())
    with pytest.raises(JourneyForbiddenError, match="requires_guardian"):
        await ai_actor.adopt(
            AdoptGrowthPlanCommand(
                replace(actor, actor_type="AI"), "draft:family-a:1", 3, "adopt-3"
            )
        )

    need_more, _ = service(draft(output={"result_status": "NEEDS_MORE_INFORMATION"}))
    with pytest.raises(JourneyConflictError, match="not_adoptable"):
        await need_more.adopt(AdoptGrowthPlanCommand(actor, "draft:family-a:1", 3, "adopt-4"))


@pytest.mark.asyncio
async def test_plan_content_is_not_replaced_by_a_fixed_horizon_or_template() -> None:
    application, _ = service(draft())
    response = await application.adopt(
        AdoptGrowthPlanCommand(
            GrowthPlanActor("guardian-a", "tenant-a", "family-a"),
            "draft:family-a:1",
            3,
            "adopt-dynamic",
        )
    )

    encoded = str(response["plan"])
    assert "35" in encoded
    assert "90天" not in encoded
    assert "21天" not in encoded
    assert "小行动" not in encoded
