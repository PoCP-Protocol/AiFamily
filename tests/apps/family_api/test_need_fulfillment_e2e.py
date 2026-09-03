"""End-to-end walk of the real parent-help business scenario.

A parent describes a real struggle ("homework keeps dragging on, we need
someone to help"), the platform records it, confirms understanding, learns
urgency, and matches it to a real, already-existing teacher service offering
(`TEACHER_LI` / `TEACHER_ZHANG`, seeded by
`backend.domains.service.application.master_data.ensure_mobile_master_data`,
the same catalogue the mobile SERVICE journey books against). This is one
HTTP request sequence against the dev-wired FastAPI app, not four isolated
unit tests: the assertion that matters is that the solution draft's
`resolved_components` names a real supply reference, proving the match
actually happened rather than only exercising each step in isolation.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api import dev_wiring
from backend.apps.family_api.dev_wiring import reset_dev_state
from backend.apps.family_api.main import create_app
from backend.domains.family_need.api import ai_coach_dependencies as family_need_ai_coach_deps
from backend.domains.family_need.domain.value_objects import SupplyShape
from backend.intelligence.model_gateway.gateway import build_gateway
from backend.intelligence.model_gateway.provider_registry import default_provider_registry
from backend.intelligence.model_gateway.providers.fake import FakeProvider

_COACH_USE_CASE = "FAMILY_AI_COACH_SOCRATIC_PERSPECTIVE"


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "dev")
    reset_dev_state()


def _auth(client: TestClient, family: str) -> dict[str, str]:
    response = client.post(
        "/auth/account-session",
        json={"external_ref": f"guardian-1:{family}"},
        headers={"idempotency-key": f"auth:{family}"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_parent_help_request_reaches_a_real_teacher_service_offering() -> None:
    """Signal -> clarify -> profile -> solution draft, matched to real supply."""

    client = TestClient(create_app())
    family_id = "family-need-e2e"
    auth = _auth(client, family_id)
    subject = f"dev-child:{family_id}"

    # 1. The parent describes the problem in their own words.
    signal_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "孩子做作业总是拖拖拉拉，需要有人帮忙",
            "statement": "孩子做作业拖延，家长需要陪伴式的督促帮助",
            "desired_outcome": "孩子能按时、专注地完成作业",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e:signal"},
    )
    assert signal_response.status_code == 201, signal_response.text
    signal_payload = signal_response.json()
    need = signal_payload["need"]
    need_id = need["need_id"]
    assert need["status"] == "CAPTURED"

    # 2. The family confirms the system understood correctly.
    clarify_response = client.post(
        f"/families/{family_id}/needs/{need_id}/clarify",
        json={
            "statement": need["statement"],
            "desired_outcome": need["desired_outcome"],
            "expected_version": need["version"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e:clarify"},
    )
    assert clarify_response.status_code == 200, clarify_response.text
    clarified_need = clarify_response.json()["need"]
    assert clarified_need["status"] == "CONFIRMED"

    # 3. The system learns urgency/complexity/risk and that a SERVICE (a
    #    teacher's help), not a product, is what the family wants.
    profile_response = client.post(
        f"/families/{family_id}/needs/{need_id}/profile",
        json={
            "expected_need_version": clarified_need["version"],
            "urgency": "SOON",
            "complexity": "SIMPLE",
            "risk_level": "LOW",
            "preferred_shapes": ["SERVICE"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e:profile"},
    )
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()["profile"]

    # 4. The system drafts a solution against a real, already-admitted
    #    teacher offering from the shared service catalogue.
    draft_response = client.post(
        f"/families/{family_id}/needs/{need_id}/solution-drafts",
        json={
            "profile_id": profile["profile_id"],
            "expected_profile_version": profile["version"],
            "shape": "SERVICE",
            "component_refs": [
                # "COMMUNICATION" is the seeded offering ref for provider
                # TEACHER_LI (李老师亲子沟通支持) in
                # `ensure_mobile_master_data` — the same catalogue the mobile
                # SERVICE journey books against.
                {"component_id": "COMMUNICATION", "shape": "SERVICE", "version": "1"}
            ],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e:draft"},
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_payload = draft_response.json()

    # The whole point of the scenario: a real supply reference was matched,
    # not a resource gap.
    assert draft_payload["resource_gap"] is None
    assert draft_payload["resolved_components"], draft_payload
    resolved = draft_payload["resolved_components"][0]
    assert resolved["component_id"] == "COMMUNICATION"
    assert resolved["shape"] == "SERVICE"
    assert draft_payload["draft"]["status"] == "DRAFT"


def test_low_intensity_family_profile_gets_universal_tier_and_product_match() -> None:
    """A calm, low-risk, simple request is graded UNIVERSAL (Triple P Level 1)
    and matches self-help PRODUCT catalogue content, not a real person."""

    client = TestClient(create_app())
    family_id = "family-need-e2e-universal"
    auth = _auth(client, family_id)
    subject = f"dev-child:{family_id}"

    signal_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "想找一些亲子共读的小方法，不着急",
            "statement": "家长希望获取一些亲子共读的通用建议",
            "desired_outcome": "找到适合日常使用的共读小工具",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-universal:signal"},
    )
    assert signal_response.status_code == 201, signal_response.text
    need = signal_response.json()["need"]
    need_id = need["need_id"]

    clarify_response = client.post(
        f"/families/{family_id}/needs/{need_id}/clarify",
        json={
            "statement": need["statement"],
            "desired_outcome": need["desired_outcome"],
            "expected_version": need["version"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-universal:clarify"},
    )
    assert clarify_response.status_code == 200, clarify_response.text
    clarified_need = clarify_response.json()["need"]

    # Lowest urgency, lowest complexity, lowest risk -> UNIVERSAL (Level 1).
    profile_response = client.post(
        f"/families/{family_id}/needs/{need_id}/profile",
        json={
            "expected_need_version": clarified_need["version"],
            "urgency": "WHEN_READY",
            "complexity": "SIMPLE",
            "risk_level": "LOW",
            "preferred_shapes": ["PRODUCT"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-universal:profile"},
    )
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()["profile"]
    assert profile["intervention_tier"] == "UNIVERSAL"

    draft_response = client.post(
        f"/families/{family_id}/needs/{need_id}/solution-drafts",
        json={
            "profile_id": profile["profile_id"],
            "expected_profile_version": profile["version"],
            "shape": "PRODUCT",
            "component_refs": [
                # Seeded self-help product ref from
                # `ensure_mobile_product_master_data` (亲子阅读工具包).
                {
                    "component_id": "PRODUCT_PARENT_CHILD_READING_TOOLKIT",
                    "shape": "PRODUCT",
                    "version": "1",
                }
            ],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-universal:draft"},
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_payload = draft_response.json()

    assert draft_payload["resource_gap"] is None
    resolved = draft_payload["resolved_components"][0]
    assert resolved["component_id"] == "PRODUCT_PARENT_CHILD_READING_TOOLKIT"
    assert resolved["shape"] == "PRODUCT"
    assert draft_payload["draft"]["requires_human_case_review"] is False
    assert draft_payload["draft"]["human_case_review_note"] is None


def test_highest_risk_family_profile_is_flagged_for_human_case_review() -> None:
    """A HUMAN_REVIEW_REQUIRED risk profile is graded ENHANCED_SUPPORT (Triple
    P Level 5) and the resulting solution draft must carry an explicit
    "pending human case review" marker rather than looking auto-fulfilled."""

    client = TestClient(create_app())
    family_id = "family-need-e2e-enhanced"
    auth = _auth(client, family_id)
    subject = f"dev-child:{family_id}"

    signal_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "家里最近发生了让孩子很害怕的事情，我们需要专业人员介入",
            "statement": "家庭出现让孩子恐惧的严重状况，需要专业人员评估介入",
            "desired_outcome": "孩子得到专业、安全的支持",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-enhanced:signal"},
    )
    assert signal_response.status_code == 201, signal_response.text
    need = signal_response.json()["need"]
    need_id = need["need_id"]

    clarify_response = client.post(
        f"/families/{family_id}/needs/{need_id}/clarify",
        json={
            "statement": need["statement"],
            "desired_outcome": need["desired_outcome"],
            "expected_version": need["version"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-enhanced:clarify"},
    )
    assert clarify_response.status_code == 200, clarify_response.text
    clarified_need = clarify_response.json()["need"]

    # risk_level at the ceiling always wins -> ENHANCED_SUPPORT (Level 5),
    # and NeedProfile requires a human confirmer at this risk level.
    profile_response = client.post(
        f"/families/{family_id}/needs/{need_id}/profile",
        json={
            "expected_need_version": clarified_need["version"],
            "urgency": "NOW",
            "complexity": "CROSS_DOMAIN",
            "risk_level": "HUMAN_REVIEW_REQUIRED",
            "preferred_shapes": ["SERVICE"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-enhanced:profile"},
    )
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()["profile"]
    assert profile["intervention_tier"] == "ENHANCED_SUPPORT"

    draft_response = client.post(
        f"/families/{family_id}/needs/{need_id}/solution-drafts",
        json={
            "profile_id": profile["profile_id"],
            "expected_profile_version": profile["version"],
            "shape": "SERVICE",
            "component_refs": [
                {"component_id": "COMMUNICATION", "shape": "SERVICE", "version": "1"}
            ],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-enhanced:draft"},
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_payload = draft_response.json()

    assert draft_payload["resource_gap"] is None
    assert draft_payload["draft"]["requires_human_case_review"] is True
    assert draft_payload["draft"]["human_case_review_note"] is not None
    assert "PENDING_HUMAN_CASE_REVIEW" in draft_payload["draft"]["human_case_review_note"]


def test_low_intensity_family_profile_matches_a_real_published_course() -> None:
    """A calm, low-risk request whose profile prefers SOLUTION must resolve
    the one genuinely-published course ("告别作业磨蹭", seeded through the
    real DRAFT -> UNDER_REVIEW -> PUBLISHED Human Gate lifecycle by
    `dev_wiring._seed_dev_published_course`), not fall back to a resource
    gap."""

    client = TestClient(create_app())
    family_id = "family-need-e2e-course-solution"
    auth = _auth(client, family_id)
    subject = f"dev-child:{family_id}"

    signal_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "孩子做作业总是拖拖拉拉，想找一套课程慢慢引导，不着急找人",
            "statement": "家长希望通过一套课程帮孩子改善作业拖延",
            "desired_outcome": "孩子能按时、专注地完成作业",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-course:signal"},
    )
    assert signal_response.status_code == 201, signal_response.text
    need = signal_response.json()["need"]
    need_id = need["need_id"]

    clarify_response = client.post(
        f"/families/{family_id}/needs/{need_id}/clarify",
        json={
            "statement": need["statement"],
            "desired_outcome": need["desired_outcome"],
            "expected_version": need["version"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-course:clarify"},
    )
    assert clarify_response.status_code == 200, clarify_response.text
    clarified_need = clarify_response.json()["need"]

    # Lowest urgency, lowest complexity, lowest risk -> UNIVERSAL/LIGHT_GUIDANCE
    # (Triple P Level 1/2), preferring a SOLUTION (a course), not a real person.
    profile_response = client.post(
        f"/families/{family_id}/needs/{need_id}/profile",
        json={
            "expected_need_version": clarified_need["version"],
            "urgency": "WHEN_READY",
            "complexity": "SIMPLE",
            "risk_level": "LOW",
            "preferred_shapes": ["SOLUTION"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-course:profile"},
    )
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()["profile"]
    assert profile["intervention_tier"] in {"UNIVERSAL", "LIGHT_GUIDANCE"}

    draft_response = client.post(
        f"/families/{family_id}/needs/{need_id}/solution-drafts",
        json={
            "profile_id": profile["profile_id"],
            "expected_profile_version": profile["version"],
            "shape": "SOLUTION",
            "component_refs": [
                # The one course seeded through the real Human Gate lifecycle
                # in `dev_wiring._seed_dev_published_course` ("告别作业磨蹭").
                {
                    "component_id": dev_wiring.DEV_SEEDED_COURSE_ID,
                    "shape": "SOLUTION",
                    "version": "3",
                }
            ],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-course:draft"},
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_payload = draft_response.json()

    # The whole point of the scenario: a real published course was matched,
    # not a resource gap.
    assert draft_payload["resource_gap"] is None
    assert draft_payload["resolved_components"], draft_payload
    resolved = draft_payload["resolved_components"][0]
    assert resolved["component_id"] == dev_wiring.DEV_SEEDED_COURSE_ID
    assert resolved["shape"] == "SOLUTION"
    assert draft_payload["draft"]["status"] == "DRAFT"

    # The rest of the loop: the family actually finishes the matched course,
    # and that fact must reach the growth journey the same way a completed
    # service booking already does.
    before_snapshot = dev_wiring._journey_outcome_loop.snapshot(
        tenant_id=family_id, family_id=family_id
    )
    before_task_ids = {action.task_id for action in before_snapshot.actions}
    assert f"course-completion:{dev_wiring.DEV_SEEDED_COURSE_ID}" not in before_task_ids

    complete_response = client.post(
        f"/families/{family_id}/needs/{need_id}/courses/"
        f"{dev_wiring.DEV_SEEDED_COURSE_ID}/complete-and-review",
        json={"day_number": 1},
        headers={**auth, "idempotency-key": "e2e-course:complete"},
    )
    assert complete_response.status_code == 200, complete_response.text
    complete_payload = complete_response.json()
    assert complete_payload["course_completion"]["course_content_id"] == (
        dev_wiring.DEV_SEEDED_COURSE_ID
    )
    journey_action = complete_payload["journey_action"]
    assert journey_action["task_id"] == f"course-completion:{dev_wiring.DEV_SEEDED_COURSE_ID}"
    assert journey_action["status"] == "COMPLETED"

    # The hard proof: querying the family's growth journey directly shows a
    # new record for this exact course — finishing it really left a trace in
    # the child's growth history, not just an HTTP 200.
    after_snapshot = dev_wiring._journey_outcome_loop.snapshot(
        tenant_id=family_id, family_id=family_id
    )
    matching_actions = [
        action
        for action in after_snapshot.actions
        if action.task_id == f"course-completion:{dev_wiring.DEV_SEEDED_COURSE_ID}"
    ]
    assert len(matching_actions) == 1, after_snapshot.actions
    assert matching_actions[0].status.value == "COMPLETED"


def test_confirmed_draft_is_really_booked_and_completion_reaches_the_growth_journey() -> None:
    """The full loop this vertical slice exists for: a parent's confirmed
    solution draft must turn into a real teacher booking (not a null
    `booking_id`), and once that booking is marked delivered, the family's
    growth journey must carry a new, queryable trace of it — otherwise the
    "need -> match -> book -> deliver -> review" chain is fiction past the
    draft step."""

    client = TestClient(create_app())
    family_id = "family-need-e2e-fulfil"
    auth = _auth(client, family_id)
    subject = f"dev-child:{family_id}"

    signal_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "孩子做作业总是拖拖拉拉，需要有人帮忙",
            "statement": "孩子做作业拖延，家长需要陪伴式的督促帮助",
            "desired_outcome": "孩子能按时、专注地完成作业",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fulfil:signal"},
    )
    assert signal_response.status_code == 201, signal_response.text
    need = signal_response.json()["need"]
    need_id = need["need_id"]

    clarify_response = client.post(
        f"/families/{family_id}/needs/{need_id}/clarify",
        json={
            "statement": need["statement"],
            "desired_outcome": need["desired_outcome"],
            "expected_version": need["version"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fulfil:clarify"},
    )
    assert clarify_response.status_code == 200, clarify_response.text

    # A draft with commercial_intent=True requires the need's emotional gate
    # to have already reached E3 (value confirmed) per `assert_commercial_gate`
    # (economic choice follows proven value — E3 must precede any commercial
    # draft). There is no HTTP step for this yet, so advance the gate the same
    # way the domain models it: a human-actor fact recorded directly against
    # the need aggregate, before profiling so the profile's `need_version`
    # snapshot stays bound to the need's current version.
    from backend.domains.family_need.domain.value_objects import ActorType, EmotionalGate

    async def _advance_value_gate() -> str:
        need_entity = await dev_wiring._family_need_repository.get_need(
            tenant_id=family_id, family_id=family_id, need_id=need_id
        )
        advanced_need = need_entity.advance_emotional_gate(
            EmotionalGate.E3_VALUE_CONFIRMED,
            actor_id=f"guardian-1:{family_id}",
            actor_type=ActorType.FAMILY_GUARDIAN,
        )
        await dev_wiring._family_need_repository.save_need(advanced_need)
        return advanced_need.version

    need_version_after_gate = asyncio.run(_advance_value_gate())

    profile_response = client.post(
        f"/families/{family_id}/needs/{need_id}/profile",
        json={
            "expected_need_version": need_version_after_gate,
            "urgency": "SOON",
            "complexity": "SIMPLE",
            "risk_level": "LOW",
            "preferred_shapes": ["SERVICE"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fulfil:profile"},
    )
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()["profile"]

    # The draft signals commercial intent up front: the family is not just
    # browsing a match, it wants this teacher service booked for real.
    draft_response = client.post(
        f"/families/{family_id}/needs/{need_id}/solution-drafts",
        json={
            "profile_id": profile["profile_id"],
            "expected_profile_version": profile["version"],
            "shape": "SERVICE",
            "component_refs": [
                {"component_id": "COMMUNICATION", "shape": "SERVICE", "version": "1"}
            ],
            "commercial_intent": True,
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fulfil:draft"},
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_payload = draft_response.json()
    assert draft_payload["resource_gap"] is None
    draft_id = draft_payload["draft"]["draft_id"]
    assert draft_payload["draft"]["commercial_intent"] is True

    # The family confirms: this must actually create a real booking, not
    # just flip a status flag.
    confirm_response = client.post(
        f"/families/{family_id}/needs/{need_id}/solution-drafts/{draft_id}/confirm",
        json={"subject_person_id": subject},
        headers={**auth, "idempotency-key": "e2e-fulfil:confirm"},
    )
    assert confirm_response.status_code == 200, confirm_response.text
    confirm_payload = confirm_response.json()
    fulfillment = confirm_payload["fulfillment"]
    assert fulfillment is not None, confirm_payload
    assert fulfillment["succeeded"] is True, fulfillment
    booking_id = fulfillment["booking_id"]
    assert booking_id is not None, fulfillment
    booking_service_record_id = fulfillment["booking_service_record_id"]
    assert booking_service_record_id is not None, fulfillment

    # N4: the assignment plan returned in this same response must now name
    # the *real* resource fulfilment assigned this need to — not merely the
    # family's authorization to attempt it. Before this, only the booking
    # record itself (looked up separately) could answer "what was this need
    # actually assigned to".
    assignment_plan = confirm_payload["assignment_plan"]
    assert assignment_plan["resolved_slot_id"] is not None, assignment_plan
    assert assignment_plan["resolved_slot_id"] == fulfillment["availability_slot_id"]
    assert assignment_plan["resolved_booking_ref"] == booking_service_record_id

    # The hard proof: querying the assignment plan directly (not just reading
    # the confirm response) shows the same resolved facts — this really is a
    # queryable, persisted record of the actual assignment outcome.
    async def _get_assignment_plan():
        return await dev_wiring._family_need_repository.get_assignment_plan(
            tenant_id=family_id, family_id=family_id, plan_id=assignment_plan["plan_id"]
        )

    persisted_plan = asyncio.run(_get_assignment_plan())
    assert persisted_plan is not None
    assert persisted_plan.resolved_slot_id == fulfillment["availability_slot_id"]
    assert persisted_plan.resolved_booking_ref == booking_service_record_id

    # Snapshot the family's growth journey before delivery: no action fact
    # tied to this booking should exist yet.
    before_snapshot = dev_wiring._journey_outcome_loop.snapshot(
        tenant_id=family_id, family_id=family_id
    )
    before_task_ids = {action.task_id for action in before_snapshot.actions}
    assert f"booking-service-record:{booking_service_record_id}" not in before_task_ids

    # The service session actually happens; mark it delivered and leave a
    # growth-journey trace.
    complete_response = client.post(
        f"/families/{family_id}/needs/{need_id}/bookings/{booking_service_record_id}/complete-and-review",
        json={"day_number": 3},
        headers={**auth, "idempotency-key": "e2e-fulfil:complete"},
    )
    assert complete_response.status_code == 200, complete_response.text
    complete_payload = complete_response.json()
    assert complete_payload["service_record"]["booking_service_record_id"] == (
        booking_service_record_id
    )
    journey_action = complete_payload["journey_action"]
    assert journey_action["task_id"] == f"booking-service-record:{booking_service_record_id}"
    assert journey_action["status"] == "COMPLETED"
    assert journey_action["day_number"] == 3

    # The hard proof: querying the family's growth journey directly shows a
    # new record for this exact booking — the service delivery really left a
    # trace in the child's growth history, not just an HTTP 200.
    after_snapshot = dev_wiring._journey_outcome_loop.snapshot(
        tenant_id=family_id, family_id=family_id
    )
    matching_actions = [
        action
        for action in after_snapshot.actions
        if action.task_id == f"booking-service-record:{booking_service_record_id}"
    ]
    assert len(matching_actions) == 1, after_snapshot.actions
    assert matching_actions[0].status.value == "COMPLETED"
    assert matching_actions[0].action_id == journey_action["action_id"]

    # N6/N7: the missing half of the loop. `complete_booking_and_review`
    # above only recorded that delivery *happened* (a service-side fact).
    # Whether it actually helped the family is a distinct fact, and only the
    # family may confirm it.
    confirm_outcome_response = client.post(
        f"/families/{family_id}/needs/{need_id}/outcomes/confirm",
        json={
            "fulfillment_ref": booking_service_record_id,
            "decision": "HELPED",
            "family_note": "老师这次真的帮到孩子专心写完了作业",
        },
        headers={**auth, "idempotency-key": "e2e-fulfil:confirm-outcome"},
    )
    assert confirm_outcome_response.status_code == 200, confirm_outcome_response.text
    confirm_outcome_payload = confirm_outcome_response.json()
    assert confirm_outcome_payload["outcome"]["decision"] == "HELPED"
    assert "recommended_next_action" not in confirm_outcome_payload
    outcome_journey_action = confirm_outcome_payload["journey_action"]
    assert outcome_journey_action["task_id"] == (
        f"family-confirmed-outcome:{booking_service_record_id}"
    )
    # Distinct prefix from the service-completion record above — a reader of
    # the journey can tell "the family said this" apart from "the system
    # recorded delivery" at a glance.
    assert outcome_journey_action["task_id"] != journey_action["task_id"]

    # The hard proof: the family's confirmation really left its own trace in
    # the growth journey, separate from the service-delivery trace.
    after_outcome_snapshot = dev_wiring._journey_outcome_loop.snapshot(
        tenant_id=family_id, family_id=family_id
    )
    outcome_actions = [
        action
        for action in after_outcome_snapshot.actions
        if action.task_id == f"family-confirmed-outcome:{booking_service_record_id}"
    ]
    assert len(outcome_actions) == 1, after_outcome_snapshot.actions
    assert outcome_actions[0].status.value == "COMPLETED"


def test_family_confirms_did_not_help_and_gets_an_honest_retriage_suggestion() -> None:
    """A negative result must be recorded as honestly as a positive one: the
    response carries an explicit `recommended_next_action` pointer back
    toward re-triage, and the journey still records the family's fact — the
    platform does not hide or special-case a "did not help" verdict."""

    client = TestClient(create_app())
    family_id = "family-need-e2e-outcome-negative"
    auth = _auth(client, family_id)
    subject = f"dev-child:{family_id}"

    signal_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "孩子做作业总是拖拖拉拉，需要有人帮忙",
            "statement": "孩子做作业拖延，家长需要陪伴式的督促帮助",
            "desired_outcome": "孩子能按时、专注地完成作业",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-outcome-neg:signal"},
    )
    assert signal_response.status_code == 201, signal_response.text
    need = signal_response.json()["need"]
    need_id = need["need_id"]

    clarify_response = client.post(
        f"/families/{family_id}/needs/{need_id}/clarify",
        json={
            "statement": need["statement"],
            "desired_outcome": need["desired_outcome"],
            "expected_version": need["version"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-outcome-neg:clarify"},
    )
    assert clarify_response.status_code == 200, clarify_response.text

    from backend.domains.family_need.domain.value_objects import ActorType, EmotionalGate

    async def _advance_value_gate() -> int:
        need_entity = await dev_wiring._family_need_repository.get_need(
            tenant_id=family_id, family_id=family_id, need_id=need_id
        )
        advanced_need = need_entity.advance_emotional_gate(
            EmotionalGate.E3_VALUE_CONFIRMED,
            actor_id=f"guardian-1:{family_id}",
            actor_type=ActorType.FAMILY_GUARDIAN,
        )
        await dev_wiring._family_need_repository.save_need(advanced_need)
        return advanced_need.version

    need_version_after_gate = asyncio.run(_advance_value_gate())

    profile_response = client.post(
        f"/families/{family_id}/needs/{need_id}/profile",
        json={
            "expected_need_version": need_version_after_gate,
            "urgency": "SOON",
            "complexity": "SIMPLE",
            "risk_level": "LOW",
            "preferred_shapes": ["SERVICE"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-outcome-neg:profile"},
    )
    assert profile_response.status_code == 200, profile_response.text
    profile = profile_response.json()["profile"]

    draft_response = client.post(
        f"/families/{family_id}/needs/{need_id}/solution-drafts",
        json={
            "profile_id": profile["profile_id"],
            "expected_profile_version": profile["version"],
            "shape": "SERVICE",
            "component_refs": [
                {"component_id": "COMMUNICATION", "shape": "SERVICE", "version": "1"}
            ],
            "commercial_intent": True,
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-outcome-neg:draft"},
    )
    assert draft_response.status_code == 200, draft_response.text
    draft_id = draft_response.json()["draft"]["draft_id"]

    confirm_response = client.post(
        f"/families/{family_id}/needs/{need_id}/solution-drafts/{draft_id}/confirm",
        json={"subject_person_id": subject},
        headers={**auth, "idempotency-key": "e2e-outcome-neg:confirm"},
    )
    assert confirm_response.status_code == 200, confirm_response.text
    fulfillment = confirm_response.json()["fulfillment"]
    booking_service_record_id = fulfillment["booking_service_record_id"]
    assert booking_service_record_id is not None, fulfillment

    complete_response = client.post(
        f"/families/{family_id}/needs/{need_id}/bookings/{booking_service_record_id}"
        "/complete-and-review",
        json={"day_number": 5},
        headers={**auth, "idempotency-key": "e2e-outcome-neg:complete"},
    )
    assert complete_response.status_code == 200, complete_response.text

    # The family's honest verdict: this did not actually help.
    confirm_outcome_response = client.post(
        f"/families/{family_id}/needs/{need_id}/outcomes/confirm",
        json={
            "fulfillment_ref": booking_service_record_id,
            "decision": "DID_NOT_HELP",
            "family_note": "孩子还是没能按时完成作业",
            "draft_id": draft_id,
        },
        headers={**auth, "idempotency-key": "e2e-outcome-neg:confirm-outcome"},
    )
    assert confirm_outcome_response.status_code == 200, confirm_outcome_response.text
    confirm_outcome_payload = confirm_outcome_response.json()
    assert confirm_outcome_payload["outcome"]["decision"] == "DID_NOT_HELP"
    # The core promise: a negative result gets an explicit, honest pointer
    # back toward re-triage, not silence.
    assert confirm_outcome_payload["recommended_next_action"] == "N8_RETRIAGE_SUGGESTED"

    # N8 (product side): a de-identified, cross-family "this component did
    # not help" signal must now exist for the exact SERVICE component
    # ("COMMUNICATION") this draft matched — queryable by the product
    # team's own endpoint, entirely separate from the family's own private
    # re-triage signal below.
    candidates_response = client.get("/product-intelligence/improvement-candidates")
    assert candidates_response.status_code == 200, candidates_response.text
    candidates_payload = candidates_response.json()
    matching_candidates = [
        item
        for item in candidates_payload["candidates"]
        if item["component_id"] == "COMMUNICATION" and item["decision"] == "DID_NOT_HELP"
    ]
    assert len(matching_candidates) == 1, candidates_payload
    candidate = matching_candidates[0]
    assert candidate["component_shape"] == "SERVICE"

    # The hard privacy proof: nothing about this specific family appears in
    # the candidate record or the raw response body — no family_id/tenant_id
    # field exists on the record at all, and neither this family's id nor its
    # free-text note leaked into any string value on the wire.
    assert "family_id" not in candidate
    assert "tenant_id" not in candidate
    assert "child_id" not in candidate
    assert "family_note" not in candidate
    raw_body = candidates_response.text
    assert family_id not in raw_body
    assert subject not in raw_body
    assert "孩子还是没能按时完成作业" not in raw_body

    # The negative result is not hidden from the growth journey either.
    outcome_journey_action = confirm_outcome_payload["journey_action"]
    assert outcome_journey_action["task_id"] == (
        f"family-confirmed-outcome:{booking_service_record_id}"
    )
    after_snapshot = dev_wiring._journey_outcome_loop.snapshot(
        tenant_id=family_id, family_id=family_id
    )
    matching_actions = [
        action
        for action in after_snapshot.actions
        if action.task_id == f"family-confirmed-outcome:{booking_service_record_id}"
    ]
    assert len(matching_actions) == 1, after_snapshot.actions
    assert matching_actions[0].status.value == "COMPLETED"


def test_ai_or_system_actor_cannot_confirm_a_family_outcome() -> None:
    """The single most important rule this endpoint exists to enforce: an AI
    or SYSTEM actor must never be able to confirm a family outcome — that
    fact belongs to the family alone (R9). Exercised directly against
    `FamilyNeedApplicationService.confirm_outcome`, the same call the HTTP
    route makes, so the assertion is about the business rule itself and not
    merely about the dev HTTP wiring (which only ever issues FAMILY_GUARDIAN
    sessions and therefore cannot be used to construct an AI/SYSTEM request)."""

    import pytest

    from backend.domains.family_need.domain.errors import FamilyNeedForbiddenError
    from backend.domains.family_need.domain.value_objects import (
        ActorType,
        DataClass,
        FamilyOutcomeDecision,
        NeedContext,
    )

    client = TestClient(create_app())
    family_id = "family-need-e2e-outcome-ai-denied"
    auth = _auth(client, family_id)
    subject = f"dev-child:{family_id}"

    signal_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "孩子做作业总是拖拖拉拉，需要有人帮忙",
            "statement": "孩子做作业拖延，家长需要陪伴式的督促帮助",
            "desired_outcome": "孩子能按时、专注地完成作业",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-outcome-ai:signal"},
    )
    assert signal_response.status_code == 201, signal_response.text
    need_id = signal_response.json()["need"]["need_id"]

    # SYSTEM: a context can be constructed (only AI is blocked at
    # `NeedContext` construction time), so this exercises
    # `confirm_outcome`'s explicit `assert_family_outcome_confirmer` gate.
    system_context = NeedContext(
        tenant_id=family_id,
        family_id=family_id,
        purpose="FAMILY_NEED",
        consent_version="v1",
        data_class=DataClass.MINOR_PERSONAL_DATA,
        actor_id="system-actor",
        actor_type=ActorType.SYSTEM,
    )
    with pytest.raises(FamilyNeedForbiddenError):
        asyncio.run(
            dev_wiring._family_need_service.confirm_outcome(
                context=system_context,
                need_id=need_id,
                fulfillment_ref="booking-service-record:whatever",
                decision=FamilyOutcomeDecision.HELPED,
            )
        )

    # AI: `NeedContext` itself refuses to be constructed with actor_type=AI
    # (R9 enforced one layer earlier, at the context boundary) — an even
    # stronger guarantee than a per-call check. Confirms the AI path is
    # unreachable by any means, not merely rejected inside one method.
    with pytest.raises(ValueError, match="ai_cannot_write_family_need_fact"):
        NeedContext(
            tenant_id=family_id,
            family_id=family_id,
            purpose="FAMILY_NEED",
            consent_version="v1",
            data_class=DataClass.MINOR_PERSONAL_DATA,
            actor_id="ai-actor",
            actor_type=ActorType.AI,
        )


def test_course_catalog_covers_all_six_blueprint_systems() -> None:
    """The course catalog is not one demo course — it is the platform
    blueprint's full six-system, four-course-each library (24 courses total),
    each one really published through the same DRAFT -> UNDER_REVIEW ->
    PUBLISHED state machine `_seed_dev_published_course` uses for the
    flagship "告别作业磨蹭" course. This proves the catalog actually reaches
    24 real, matchable rows — not just that the seeding function returns
    without raising."""

    # The catalog seed is lazy: it runs inside `_dev_family_need_actor`, the
    # first time a request actually resolves a family_need actor — not at
    # `create_app()` time. One real signal-capture call, same first step
    # every other scenario in this file takes, is what triggers it.
    client = TestClient(create_app())
    family_id = "family-need-e2e-course-catalog"
    auth = _auth(client, family_id)
    signal_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "想了解一下有没有课程能帮到我们",
            "statement": "家庭想先看看有没有课程资料能自助学习",
            "desired_outcome": "找到合适的课程资料",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [f"dev-child:{family_id}"],
        },
        headers={**auth, "idempotency-key": "e2e-course-catalog:signal"},
    )
    assert signal_response.status_code == 201, signal_response.text

    published = asyncio.run(
        dev_wiring._course_content_repository.list_published_course_content(
            dev_wiring.DEV_COURSE_CATALOG_TENANT_SCOPE
        )
    )
    published_ids = {course.id for course in published}

    # 6 systems x 4 courses = 24, and none of them are stray duplicates of the
    # flagship or of each other.
    assert len(published_ids) == 24, published_ids

    representative_ids = {
        "正向养育基础": dev_wiring.DEV_SEEDED_COURSE_ID_PARENTING_BASICS,
        "学习成长": dev_wiring.DEV_SEEDED_COURSE_ID,
        "数字生活": dev_wiring.DEV_SEEDED_COURSE_ID_DIGITAL_LIFE,
        "情绪与成长": dev_wiring.DEV_SEEDED_COURSE_ID_EMOTION,
        "青春期": dev_wiring.DEV_SEEDED_COURSE_ID_ADOLESCENCE,
    }
    for system, course_id in representative_ids.items():
        assert course_id in published_ids, f"missing a real published course for {system}"

    # The hard proof each representative course is actually resolvable by
    # the same adapter family_need's solution-draft matching depends on, not
    # merely present in a list.
    adapter = dev_wiring.CourseSupplyAdapter(dev_wiring._list_published_courses_for_dev)
    for system, course_id in representative_ids.items():
        course = next(c for c in published if c.id == course_id)
        resolved = asyncio.run(
            adapter.resolve_component(
                tenant_id="irrelevant-to-this-adapter",
                region="CN",
                locale="zh-CN",
                shape=SupplyShape.SOLUTION,
                component_id=course_id,
                version=str(course.version),
            )
        )
        assert resolved is not None, f"{system} course did not resolve: {course_id}"


def test_self_help_failure_escalates_to_real_teacher_through_fgcn_human_gate() -> None:
    """The core business scenario this file exists to prove end-to-end:

    A family already tried self-help (booked/completed a real teacher
    session once) and honestly confirmed it did NOT help
    (N6/N7 `DID_NOT_HELP` -> N8 re-triage). When the family's *new* need is
    then matched to a real teacher again and confirmed, that escalation must
    not go straight to `service_booking` — it must first pass through FGCN's
    own AI-suggests/human-approves Human Gate. The response must carry real
    FGCN case/assignment identifiers, not just a booking id, and the booking
    must still actually succeed once FGCN authorizes it.
    """

    client = TestClient(create_app())
    family_id = "family-need-e2e-fgcn-escalation"
    auth = _auth(client, family_id)
    subject = f"dev-child:{family_id}"

    # --- Round 1: self-help attempt that does not help -------------------
    signal_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "孩子做作业总是拖拖拉拉，需要有人帮忙",
            "statement": "孩子做作业拖延，家长需要陪伴式的督促帮助",
            "desired_outcome": "孩子能按时、专注地完成作业",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fgcn:signal-1"},
    )
    assert signal_response.status_code == 201, signal_response.text
    need_1 = signal_response.json()["need"]
    need_1_id = need_1["need_id"]

    clarify_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/clarify",
        json={
            "statement": need_1["statement"],
            "desired_outcome": need_1["desired_outcome"],
            "expected_version": need_1["version"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fgcn:clarify-1"},
    )
    assert clarify_response.status_code == 200, clarify_response.text

    from backend.domains.family_need.domain.value_objects import ActorType, EmotionalGate

    async def _advance_value_gate(need_id: str) -> int:
        need_entity = await dev_wiring._family_need_repository.get_need(
            tenant_id=family_id, family_id=family_id, need_id=need_id
        )
        advanced_need = need_entity.advance_emotional_gate(
            EmotionalGate.E3_VALUE_CONFIRMED,
            actor_id=f"guardian-1:{family_id}",
            actor_type=ActorType.FAMILY_GUARDIAN,
        )
        await dev_wiring._family_need_repository.save_need(advanced_need)
        return advanced_need.version

    need_1_version = asyncio.run(_advance_value_gate(need_1_id))

    profile_1_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/profile",
        json={
            "expected_need_version": need_1_version,
            "urgency": "SOON",
            "complexity": "SIMPLE",
            "risk_level": "LOW",
            "preferred_shapes": ["SERVICE"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fgcn:profile-1"},
    )
    assert profile_1_response.status_code == 200, profile_1_response.text
    profile_1 = profile_1_response.json()["profile"]

    draft_1_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/solution-drafts",
        json={
            "profile_id": profile_1["profile_id"],
            "expected_profile_version": profile_1["version"],
            "shape": "SERVICE",
            "component_refs": [
                {"component_id": "COMMUNICATION", "shape": "SERVICE", "version": "1"}
            ],
            "commercial_intent": True,
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fgcn:draft-1"},
    )
    assert draft_1_response.status_code == 200, draft_1_response.text
    draft_1_id = draft_1_response.json()["draft"]["draft_id"]

    confirm_1_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/solution-drafts/{draft_1_id}/confirm",
        json={"subject_person_id": subject},
        headers={**auth, "idempotency-key": "e2e-fgcn:confirm-1"},
    )
    assert confirm_1_response.status_code == 200, confirm_1_response.text
    fulfillment_1 = confirm_1_response.json()["fulfillment"]
    assert fulfillment_1["succeeded"] is True, fulfillment_1
    # This first, ordinary match has no self-help-failure evidence yet, so
    # FGCN must be skipped entirely — direct booking, exactly as before.
    assert fulfillment_1["fgcn_case_id"] is None, fulfillment_1
    booking_service_record_id_1 = fulfillment_1["booking_service_record_id"]
    assert booking_service_record_id_1 is not None, fulfillment_1

    complete_1_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/bookings/{booking_service_record_id_1}"
        "/complete-and-review",
        json={"day_number": 5},
        headers={**auth, "idempotency-key": "e2e-fgcn:complete-1"},
    )
    assert complete_1_response.status_code == 200, complete_1_response.text

    # The family's honest verdict: self-help (this first teacher match) did
    # not actually solve it.
    confirm_outcome_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/outcomes/confirm",
        json={
            "fulfillment_ref": booking_service_record_id_1,
            "decision": "DID_NOT_HELP",
            "family_note": "孩子还是没能按时完成作业",
        },
        headers={**auth, "idempotency-key": "e2e-fgcn:confirm-outcome-1"},
    )
    assert confirm_outcome_response.status_code == 200, confirm_outcome_response.text
    outcome_payload = confirm_outcome_response.json()
    assert outcome_payload["outcome"]["decision"] == "DID_NOT_HELP"
    assert outcome_payload["recommended_next_action"] == "N8_RETRIAGE_SUGGESTED"

    # --- Round 2 (N8 re-triage): the platform's own N8 re-triage signal
    # (already captured by `confirm_outcome` above, `causation_id=need_1_id`)
    # profiles as SERVICE again, and this confirmation must go through
    # FGCN's Human Gate before booking. ---
    need_2_id = outcome_payload["retriage_signal_need_id"]
    assert need_2_id is not None, outcome_payload

    async def _get_need(need_id: str):
        return await dev_wiring._family_need_repository.get_need(
            tenant_id=family_id, family_id=family_id, need_id=need_id
        )

    need_2_entity = asyncio.run(_get_need(need_2_id))
    assert need_2_entity.context.causation_id == need_1_id

    # The master-data catalogue seeds exactly one bookable slot per offering
    # (`ensure_mobile_master_data`); round 1 above already consumed it. A
    # second, real slot on the same real offering is added here so round 2's
    # escalation can actually be booked too — this is not a fabricated
    # provider or offering, just a second real slot on the one already used.
    async def _seed_second_slot() -> None:
        from datetime import UTC, datetime, timedelta

        offerings = await dev_wiring._repository.list_offerings(family_id)
        offering = next(item for item in offerings if item.service_offering_ref == "COMMUNICATION")
        starts = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=5, hours=10)
        from backend.domains.service.domain.entities import AvailabilitySlot

        await dev_wiring._repository.save_slot(
            AvailabilitySlot(
                availability_slot_id=f"e2e-fgcn-slot-{family_id}",
                tenant_id=family_id,
                provider_id=offering.provider_id,
                service_offering_id=offering.service_offering_id,
                availability_slot_ref="E2E_FGCN_SLOT_001",
                starts_at=starts,
                ends_at=starts + timedelta(hours=1),
                channel="VIDEO",
                capacity=1,
                reserved_count=0,
                created_at=starts,
                updated_at=starts,
            )
        )

    asyncio.run(_seed_second_slot())

    clarify_2_response = client.post(
        f"/families/{family_id}/needs/{need_2_id}/clarify",
        json={
            "statement": need_2_entity.statement,
            "desired_outcome": need_2_entity.desired_outcome,
            "expected_version": need_2_entity.version,
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fgcn:clarify-2"},
    )
    assert clarify_2_response.status_code == 200, clarify_2_response.text

    need_2_version = asyncio.run(_advance_value_gate(need_2_id))

    profile_2_response = client.post(
        f"/families/{family_id}/needs/{need_2_id}/profile",
        json={
            "expected_need_version": need_2_version,
            "urgency": "SOON",
            "complexity": "SIMPLE",
            "risk_level": "LOW",
            "preferred_shapes": ["SERVICE"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fgcn:profile-2"},
    )
    assert profile_2_response.status_code == 200, profile_2_response.text
    profile_2 = profile_2_response.json()["profile"]

    draft_2_response = client.post(
        f"/families/{family_id}/needs/{need_2_id}/solution-drafts",
        json={
            "profile_id": profile_2["profile_id"],
            "expected_profile_version": profile_2["version"],
            "shape": "SERVICE",
            "component_refs": [
                {"component_id": "COMMUNICATION", "shape": "SERVICE", "version": "1"}
            ],
            "commercial_intent": True,
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-fgcn:draft-2"},
    )
    assert draft_2_response.status_code == 200, draft_2_response.text
    draft_2_id = draft_2_response.json()["draft"]["draft_id"]

    confirm_2_response = client.post(
        f"/families/{family_id}/needs/{need_2_id}/solution-drafts/{draft_2_id}/confirm",
        json={"subject_person_id": subject},
        headers={**auth, "idempotency-key": "e2e-fgcn:confirm-2"},
    )
    assert confirm_2_response.status_code == 200, confirm_2_response.text
    confirm_2_payload = confirm_2_response.json()
    fulfillment_2 = confirm_2_payload["fulfillment"]
    assert fulfillment_2 is not None, confirm_2_payload

    # The core proof: this second, escalated confirmation really carries FGCN
    # case/assignment facts — an AI suggested the candidate and a guardian's
    # Human Gate approval is what actually produced the assignment. It is not
    # a bare booking id.
    assert fulfillment_2["fgcn_case_id"] is not None, fulfillment_2
    assert fulfillment_2["fgcn_task_id"] is not None, fulfillment_2
    assert fulfillment_2["fgcn_assignment_id"] is not None, fulfillment_2
    assert fulfillment_2["fgcn_assignee_ref"] == "TEACHER_LI", fulfillment_2

    # And the booking itself still really succeeded once FGCN authorized it —
    # the human gate strengthens authorization, it does not replace booking.
    assert fulfillment_2["succeeded"] is True, fulfillment_2
    booking_service_record_id_2 = fulfillment_2["booking_service_record_id"]
    assert booking_service_record_id_2 is not None, fulfillment_2
    assert booking_service_record_id_2 != booking_service_record_id_1


def test_ai_coach_sees_a_real_prior_course_completion_not_a_brand_new_family() -> None:
    """The Maven "Care Advocate" promise this task exists to prove: once a
    family has really completed a course (a genuine journey action fact, not
    a fabricated one), a *later* AI Coach call for this same family — even on
    a brand-new need — must carry that history in `family_context`, not treat
    the family as never seen before.

    Wires a real, response-returning `FakeProvider` for this test only (the
    dev-wired default fake responds with an empty/schema-invalid payload,
    which is fine for the fulfillment-only scenarios above but would make
    this test fail closed before it could inspect the payload)."""

    client = TestClient(create_app())
    family_id = "family-need-e2e-coach-journey"
    auth = _auth(client, family_id)
    subject = f"dev-child:{family_id}"

    fake_provider = FakeProvider(
        provider_id="fake-deterministic",
        responses_by_use_case={
            _COACH_USE_CASE: {
                "reflection": "听起来这件事让你有点担心。",
                "guiding_question": "你觉得是什么让孩子这次愿意开始写作业？",
            }
        },
    )
    gateway = build_gateway(
        environment="test",
        providers={"fake-deterministic": fake_provider},
        registry=default_provider_registry(),
    )
    app = client.app
    app.dependency_overrides[family_need_ai_coach_deps.get_ai_coach_deps] = lambda: (
        family_need_ai_coach_deps.AiCoachDeps(
            gateway=gateway,
            repository=dev_wiring._family_need_repository,
            provider_id="fake-deterministic",
            outcome_loop=dev_wiring._journey_outcome_loop,
        )
    )

    # 1. First need: the family completes a real, published course — this is
    #    the "family did something before" fact the coach must later see.
    signal_1_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "孩子做作业总是拖拖拉拉，想找一套课程慢慢引导，不着急找人",
            "statement": "家长希望通过一套课程帮孩子改善作业拖延",
            "desired_outcome": "孩子能按时、专注地完成作业",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-coach-journey:signal-1"},
    )
    assert signal_1_response.status_code == 201, signal_1_response.text
    need_1 = signal_1_response.json()["need"]
    need_1_id = need_1["need_id"]

    clarify_1_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/clarify",
        json={
            "statement": need_1["statement"],
            "desired_outcome": need_1["desired_outcome"],
            "expected_version": need_1["version"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-coach-journey:clarify-1"},
    )
    assert clarify_1_response.status_code == 200, clarify_1_response.text
    clarified_need_1 = clarify_1_response.json()["need"]

    profile_1_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/profile",
        json={
            "expected_need_version": clarified_need_1["version"],
            "urgency": "WHEN_READY",
            "complexity": "SIMPLE",
            "risk_level": "LOW",
            "preferred_shapes": ["SOLUTION"],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-coach-journey:profile-1"},
    )
    assert profile_1_response.status_code == 200, profile_1_response.text
    profile_1 = profile_1_response.json()["profile"]

    draft_1_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/solution-drafts",
        json={
            "profile_id": profile_1["profile_id"],
            "expected_profile_version": profile_1["version"],
            "shape": "SOLUTION",
            "component_refs": [
                {
                    "component_id": dev_wiring.DEV_SEEDED_COURSE_ID,
                    "shape": "SOLUTION",
                    "version": "3",
                }
            ],
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "MINOR_PERSONAL_DATA",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-coach-journey:draft-1"},
    )
    assert draft_1_response.status_code == 200, draft_1_response.text
    assert draft_1_response.json()["resource_gap"] is None

    complete_1_response = client.post(
        f"/families/{family_id}/needs/{need_1_id}/courses/"
        f"{dev_wiring.DEV_SEEDED_COURSE_ID}/complete-and-review",
        json={"day_number": 1},
        headers={**auth, "idempotency-key": "e2e-coach-journey:complete-1"},
    )
    assert complete_1_response.status_code == 200, complete_1_response.text

    # 2. A *second, unrelated* need — the point is that the AI Coach call
    #    below is not asking about the course-completion need itself; it is
    #    a fresh conversation, and the family's course history must still
    #    show up.
    signal_2_response = client.post(
        f"/families/{family_id}/needs/signals",
        json={
            "raw_text": "孩子最近情绪有点低落，想聊聊",
            "statement": "家长想聊聊孩子最近的情绪状态",
            "desired_outcome": "了解怎么支持孩子",
            "source": "FAMILY_EXPRESSED",
            "purpose": "FAMILY_NEED",
            "consent_version": "v1",
            "data_class": "PUBLIC",
            "subject_person_ids": [subject],
        },
        headers={**auth, "idempotency-key": "e2e-coach-journey:signal-2"},
    )
    assert signal_2_response.status_code == 201, signal_2_response.text
    need_2_id = signal_2_response.json()["need"]["need_id"]

    # 3. The AI Coach call for this brand-new conversation must still see the
    #    family's real prior course-completion history in `family_context`.
    coach_response = client.post(
        f"/families/{family_id}/needs/{need_2_id}/ai-coach/messages",
        json={"parent_message": "孩子最近写作业还是很拖，我有点担心"},
        headers={**auth, "idempotency-key": "e2e-coach-journey:coach-msg-1"},
    )
    assert coach_response.status_code == 200, coach_response.text

    assert len(fake_provider.invocations) == 1
    sent_request = fake_provider.invocations[0]
    family_context = sent_request.payload["family_context"]
    assert "growth_journey_summary" in family_context
    summary = family_context["growth_journey_summary"]
    assert summary, "expected the family's real prior course completion in the summary"
    assert dev_wiring.DEV_SEEDED_COURSE_ID in summary
    assert "完成" in summary

    # And the hard proof this is not an artefact of this call alone: the same
    # fact is independently present in the process-local journey snapshot.
    snapshot = dev_wiring._journey_outcome_loop.snapshot(tenant_id=family_id, family_id=family_id)
    assert any(
        action.task_id == f"course-completion:{dev_wiring.DEV_SEEDED_COURSE_ID}"
        for action in snapshot.actions
    )
