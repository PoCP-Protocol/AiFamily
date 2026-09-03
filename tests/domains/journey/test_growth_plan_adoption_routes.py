from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.journey.api.growth_plan_adoption_routes import (
    GrowthPlanAdoptionHttpDependencies,
    GrowthPlanAuthenticationError,
    build_growth_plan_adoption_router,
)
from backend.domains.journey.application.growth_plan_adoption import (
    AdoptedGrowthPlan,
    GrowthPlanActor,
    GrowthPlanAdoptionService,
    GuardianGrowthPlanPolicy,
    ValidatedGrowthPlanDraft,
)
from backend.domains.journey.domain.errors import JourneyConflictError


class DraftReader:
    async def load_validated_draft(self, **_: object) -> ValidatedGrowthPlanDraft:
        return ValidatedGrowthPlanDraft(
            draft_ref="draft:1",
            version=2,
            tenant_id="tenant-a",
            family_id="family-a",
            subject_refs=("guardian-a", "child-a"),
            status="VALIDATED_DRAFT",
            model_run_ref="run:1",
            provenance_ref="provenance:1",
            content_sha256="b" * 64,
            output={
                "result_status": "PLAN_DRAFT",
                "information_needed": [],
                "title": "重新建立可以商量的晚间节奏",
                "family_goal": {"statement": "减少晚间安排升级为争执"},
                "why_this_plan": "方案从家庭已有的一次成功协商经验出发。",
                "duration": {"days": 42, "rationale": "覆盖六个学习周"},
                "stages": [{"stage_id": "understand"}, {"stage_id": "co-design"}],
                "adjustable_choices": [{"choice_id": "rhythm"}],
                "unknowns_to_watch": ["疲劳与冲突的关系"],
                "review_rhythm": {"frequency": "weekly"},
                "limitations": ["仍需家庭持续校正"],
            },
        )


class Repository:
    def __init__(self) -> None:
        self.plan: AdoptedGrowthPlan | None = None
        self.receipt: tuple[str, AdoptedGrowthPlan] | None = None

    async def get_current(self, **_: str) -> AdoptedGrowthPlan | None:
        return self.plan

    async def adopt_once(
        self,
        *,
        plan: AdoptedGrowthPlan,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> tuple[AdoptedGrowthPlan, bool, bool]:
        if self.receipt:
            old_fingerprint, stored = self.receipt
            if old_fingerprint != request_fingerprint:
                raise JourneyConflictError("idempotency_conflict")
            return stored, True, True
        self.plan = plan
        self.receipt = (request_fingerprint, plan)
        return plan, True, False


def app() -> FastAPI:
    service = GrowthPlanAdoptionService(DraftReader(), Repository(), GuardianGrowthPlanPolicy())

    async def resolve_actor(authorization: str | None, family_id: str) -> GrowthPlanActor:
        if authorization == "Bearer guardian":
            return GrowthPlanActor("guardian-a", "tenant-a", family_id)
        if authorization == "Bearer other-family":
            return GrowthPlanActor("guardian-a", "tenant-a", "family-b")
        if authorization == "Bearer ai":
            return GrowthPlanActor("agent-a", "tenant-a", family_id, "AI")
        raise GrowthPlanAuthenticationError()

    value = FastAPI()
    value.include_router(
        build_growth_plan_adoption_router(
            GrowthPlanAdoptionHttpDependencies(resolve_actor, service)
        )
    )
    return value


def test_http_adopt_and_readback_preserve_generated_duration_and_provenance() -> None:
    with TestClient(app()) as client:
        adopted = client.post(
            "/families/family-a/growth/generative-plan/adopt",
            headers={"Authorization": "Bearer guardian", "Idempotency-Key": "adopt-1"},
            json={"draft_ref": "draft:1", "draft_version": 2},
        )
        assert adopted.status_code == 200, adopted.text
        assert adopted.json()["plan"]["duration"]["days"] == 42
        assert adopted.json()["plan"]["provenance_ref"] == "provenance:1"

        current = client.get(
            "/families/family-a/growth/generative-plan",
            headers={"Authorization": "Bearer guardian"},
        )
        assert current.status_code == 200
        assert current.json()["plan"]["draft_ref"] == "draft:1"


def test_http_auth_scope_idempotency_and_human_gate_fail_closed() -> None:
    with TestClient(app()) as client:
        assert client.get("/families/family-a/growth/generative-plan").status_code == 401
        assert (
            client.get(
                "/families/family-a/growth/generative-plan",
                headers={"Authorization": "Bearer other-family"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/families/family-a/growth/generative-plan/adopt",
                headers={"Authorization": "Bearer guardian"},
                json={"draft_ref": "draft:1", "draft_version": 2},
            ).status_code
            == 400
        )
        rejected = client.post(
            "/families/family-a/growth/generative-plan/adopt",
            headers={"Authorization": "Bearer ai", "Idempotency-Key": "adopt-ai"},
            json={"draft_ref": "draft:1", "draft_version": 2},
        )
        assert rejected.status_code == 403
        assert rejected.json()["detail"] == "growth_plan_adoption_requires_guardian"
