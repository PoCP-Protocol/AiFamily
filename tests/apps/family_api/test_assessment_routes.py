"""HTTP acceptance tests for the UI-02 -> UI-03 chain.

Rewritten for the four-layer refactor. Three things changed and each broke the
previous version of this file:

1. Handler construction moved out of `api.py` into dependencies that raise by
   design, so the app is only callable with `dev_wiring` installed
   (`AIFAMILY_ENV=dev`). Without it every route returns 500.
2. `app.state.assessment.service.audit` no longer exists — audit is reached
   through `backend.platform.audit`, not through per-app state.
3. `subject_person_id` must be a UUID (`commands._is_uuid`). The old fixture
   passed `"child-a"`, which is why the "missing idempotency-key returns 400"
   assertion below used to pass for the wrong reason: the request was rejected
   for a malformed person id before the idempotency check was ever reached. Each
   assertion here now fails only for the reason it names.

A fourth mismatch, fixed here: the chain's third leg was written against an
endpoint and a receipt shape that do not exist. There is no
`POST .../assessments/{id}/growth-hypothesis` — the hypothesis is *read* from
`GET /ui/03/growth-hypothesis` (`routes.get_ui03_projection`), which is the
point: a hypothesis is a projection over submitted evidence, not something a
caller mints by POSTing. And the decision receipt from
`GrowthHypothesisCommandHandler.decide` carries `action` / `outcome` /
`hypothesis_ref` / `intent`, not `hypothesis` / `growth_intent`. The R9
assertions below therefore check R9 where it is actually expressed: the
projection's `fact_boundary` (the hypothesis stays non-canonical) and the
intent's `boundary` (a confirmation yields an intent, not an outcome).
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.apps.family_api.dev_wiring import reset_dev_state
from backend.apps.family_api.main import create_app
from backend.platform.persistence.session import DATABASE_URL_ENV_VAR

FAMILY = "family-a"
OTHER_FAMILY = "family-b"
UI03_TOP_LEVEL_KEYS = {
    "projection_version",
    "tenant_id",
    "family_id",
    "availability",
    "latest_assessment_session_id",
    "hypothesis",
    "named_actions",
    "ai_state",
}
UI03_HYPOTHESIS_KEYS = {
    "hypothesis_ref",
    "subject_person_id",
    "subject_display_name",
    "focus_ref",
    "need_type_ref",
    "need_type_version",
    "title",
    "statement",
    "required_capability_keys",
    "source_refs",
    "limitations",
    "generator",
    "model_draft_ref",
    "model_generator",
    "model_component_ref",
    "model_boundary_labels",
    "need_refs",
    "construct_refs",
    "action_candidate_refs",
    "fact_boundary",
    "scorecard",
}
UI03_SOURCE_REF_KEYS = {
    "assessment_session_id",
    "assessment_response_id",
    "assessment_evidence_id",
    "tool_ref",
    "tool_version",
    "assessment_submitted_at",
}
FORBIDDEN_SCORE_KEYS = {
    "score",
    "overall_score",
    "overall_band",
    "dimensions",
    "dimension_ref",
    "peer_reference",
    "ranking",
    "rank",
}


def _object_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_object_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_object_keys(item) for item in value), set())
    return set()


@pytest.fixture(autouse=True)
def _dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`create_app` only installs dev wiring when the environment says dev.

    Set before `create_app` is called, not after: the decision is made once at
    construction time. This file exercises the synthetic HTTP contract, so an
    ambient CI database URL must not silently replace its fake identity seam;
    real PostgreSQL behavior is covered by the dedicated E2E module.
    """
    monkeypatch.setenv("AIFAMILY_ENV", "dev")
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    reset_dev_state()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_dev_http_contract_fixture_isolates_ambient_database_url() -> None:
    database_url_is_present = DATABASE_URL_ENV_VAR in os.environ
    assert database_url_is_present is False


def _auth(client: TestClient, family: str = FAMILY, key: str = "auth-1") -> dict[str, str]:
    """Exchange a dev external_ref for a bearer token.

    The `<account>:<family>` convention is what binds the session to a family —
    the family is the segment after the colon.
    """
    response = client.post(
        "/auth/account-session",
        json={"external_ref": f"account-a:{family}"},
        headers={"idempotency-key": key},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _grant_assessment_consent(family_id: str, subject_person_id: str) -> None:
    """Grant the ASSESSMENT-purpose consent the domain now requires.

    Seeded from the test rather than from `dev_wiring`, deliberately: wiring a
    blanket "every subject has consented" into the dev app would be a consent
    bypass, and consent is exactly what this domain was missing before the
    refactor. A test that wants the happy path has to say which subject consented.
    """
    from backend.apps.family_api import dev_wiring

    dev_wiring._assessment_repository.consents.add((family_id, subject_person_id, "ASSESSMENT"))


def _seed_need_type_catalog() -> None:
    """Seed the FOCUS -> need-type row the hypothesis projection reads.

    `load_hypothesis_evidence` returns `None` unless the answered `FOCUS` option
    maps to a need type, so without this the UI-03 projection reports
    `NO_SUBMITTED_ASSESSMENT` even though a session was submitted. This is
    catalog reference data, not a permission: seeding it grants no access that
    the consent and family-scope checks would otherwise refuse.

    `PARENT_CHILD_COMMUNICATION` is one of the five options
    `fake_repository.default_tool()` offers for the `FOCUS` item (v4 item
    bank — see that function's docstring), which is why the response below
    answers it.
    """
    from backend.apps.family_api import dev_wiring

    dev_wiring._assessment_repository.seed_need_type(
        "PARENT_CHILD_COMMUNICATION",
        "NEED_PARENT_CHILD_COMMUNICATION",
        "亲子沟通支持",
        "先从倾听开始",
        ["LISTENING_COACH"],
    )


def test_http_chain_is_idempotent_end_to_end(client: TestClient) -> None:
    auth = _auth(client)
    subject = str(uuid.uuid4())
    _grant_assessment_consent(FAMILY, subject)
    _seed_need_type_catalog()

    start = client.post(
        f"/families/{FAMILY}/assessments/sessions",
        json={"subject_person_id": subject},
        headers={**auth, "idempotency-key": "start-1"},
    )
    assert start.status_code == 200, start.text

    # Same key, same payload: a replay must return the original receipt rather
    # than opening a second session. Comparing identity, not just the status — a
    # second session would also answer 200.
    replay = client.post(
        f"/families/{FAMILY}/assessments/sessions",
        json={"subject_person_id": subject},
        headers={**auth, "idempotency-key": "start-1"},
    )
    assert replay.status_code == 200
    # `replayed` is expected to differ: the receipt tells the caller this was a
    # replay rather than silently looking like a fresh write. Asserting the two
    # bodies were byte-identical would have forbidden that honesty.
    assert replay.json()["replayed"] is True
    assert start.json()["replayed"] is False
    assert (
        start.json()["session"]["assessment_session_id"]
        == replay.json()["session"]["assessment_session_id"]
    )

    session_id = start.json()["session"]["assessment_session_id"]

    # `FOCUS`, answered with one of the options `default_tool()` declares for it.
    # `save_response` validates the item against the session's tool version
    # (`commands.save_response` -> `tool.find_item` -> `assert_response_value`),
    # so an invented item_ref or a free-text answer to a SINGLE_CHOICE item is
    # rejected — and `FOCUS` is also the one item the hypothesis is derived from.
    response = client.post(
        f"/families/{FAMILY}/assessments/sessions/{session_id}/responses",
        json={
            "item_ref": "FOCUS",
            "response_type": "SINGLE_CHOICE",
            "response_value": "PARENT_CHILD_COMMUNICATION",
        },
        headers={**auth, "idempotency-key": "response-1"},
    )
    assert response.status_code == 200, response.text

    submit = client.post(
        f"/families/{FAMILY}/assessments/sessions/{session_id}/submit",
        json={},
        headers={**auth, "idempotency-key": "submit-1"},
    )
    assert submit.status_code == 200, submit.text

    # The hypothesis is read, not posted. There is no endpoint that creates one:
    # it is a projection over the submitted assessment, so the caller cannot
    # bring a hypothesis of its own into the decision step.
    projection = client.get(f"/families/{FAMILY}/ui/03/growth-hypothesis", headers=auth)
    assert projection.status_code == 200, projection.text
    assert projection.json()["availability"] == "READY"

    projection_body = projection.json()
    hypothesis = projection_body["hypothesis"]
    assert set(projection_body) == UI03_TOP_LEVEL_KEYS
    assert set(hypothesis) == UI03_HYPOTHESIS_KEYS
    assert set(hypothesis["source_refs"]) == UI03_SOURCE_REF_KEYS
    assert hypothesis["scorecard"] == {"generator": "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC"}
    assert _object_keys(projection_body).isdisjoint(FORBIDDEN_SCORE_KEYS)
    # R9, first half: the model's product is a hypothesis and says so about
    # itself. A projection that presented this as established fact is the exact
    # failure R9 exists to prevent.
    assert hypothesis["fact_boundary"] == "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS"

    decision = client.post(
        f"/families/{FAMILY}/growth-hypotheses/decisions",
        json={
            "assessment_session_id": session_id,
            "hypothesis_ref": hypothesis["hypothesis_ref"],
            "decision_type": "CONFIRM",
        },
        headers={**auth, "idempotency-key": "decision-1"},
    )
    assert decision.status_code == 200, decision.text

    # R9, second half: only the human CONFIRM crosses into canonical state, and
    # what it creates is an intent to act — not a recorded outcome.
    body = decision.json()
    assert body["action"] == "CONFIRM_GROWTH_HYPOTHESIS"
    assert body["outcome"] == "INTENT_CREATED"
    assert body["intent"]["boundary"] == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"

    # The read-only result projection (R9): it explains the submitted session
    # without exposing a score or a ranking, and without minting a second
    # canonical object.
    result = client.get(f"/families/{FAMILY}/assessments/results/latest", headers=auth)
    assert result.status_code == 200, result.text
    result_body = result.json()
    assert result_body["status"] == "READY"
    assert result_body["result"]["boundary"] == "FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS"
    assert result_body["result"]["ai"]["may_mutate_business_state"] is False

    # UI-04 is the next real family-facing seam: the confirmed intent must
    # project into a reviewable draft, and the guardian's selected choice must
    # be adopted and readable on a later HTTP request. This is still a dev
    # deterministic adapter, not proof of a production AI runtime.
    draft_response = client.get(f"/families/{FAMILY}/growth/generative-plan", headers=auth)
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()["plan"]
    assert draft["result_status"] == "PLAN_DRAFT"
    choice = draft["adjustable_choices"][0]
    selected_choices = {choice["choice_id"]: choice["options"][1]}

    adopted = client.post(
        f"/families/{FAMILY}/growth/generative-plan/adopt",
        json={
            "draft_ref": draft["draft_ref"],
            "draft_version": draft["draft_version"],
            "selected_choices": selected_choices,
        },
        headers={**auth, "idempotency-key": "ui04-adopt-1"},
    )
    assert adopted.status_code == 200, adopted.text
    assert adopted.json()["plan"]["status"] == "ACTIVE"
    assert adopted.json()["plan"]["selected_choices"] == selected_choices
    assert (
        adopted.json()["plan"]["boundary"] == "HUMAN_ADOPTED_GENERATIVE_DRAFT_NOT_AI_CREATED_FACT"
    )

    replay = client.post(
        f"/families/{FAMILY}/growth/generative-plan/adopt",
        json={
            "draft_ref": draft["draft_ref"],
            "draft_version": draft["draft_version"],
            "selected_choices": selected_choices,
        },
        headers={**auth, "idempotency-key": "ui04-adopt-1"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotency_replayed"] is True
    assert replay.json()["plan"]["plan_id"] == adopted.json()["plan"]["plan_id"]

    readback = client.get(f"/families/{FAMILY}/growth/generative-plan", headers=auth)
    assert readback.status_code == 200, readback.text
    assert readback.json()["plan"]["status"] == "ACTIVE"
    assert readback.json()["plan"]["selected_choices"] == selected_choices

    cross_family = client.get(f"/families/{OTHER_FAMILY}/growth/generative-plan", headers=auth)
    assert cross_family.status_code == 403


def test_ui01_home_projects_the_same_family_scope_as_ui02(client: TestClient) -> None:
    auth = _auth(client, key="home-auth-1")
    response = client.get(f"/families/{FAMILY}/ui/01/home", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["projection_version"] == "UI01_FAMILY_HOME_V1"
    assert body["entry_state"] == "READY"
    assert body["assessment_campaign"]["state"] == "AVAILABLE"
    assert body["growth_help"]["subjects"][0]["availability"] == "AVAILABLE"
    assert body["primary_action"]["task_state"] == "NOT_STARTED"


def test_ui01_home_rejects_cross_family_access(client: TestClient) -> None:
    auth = _auth(client, family=FAMILY, key="home-auth-2")
    response = client.get(f"/families/{OTHER_FAMILY}/ui/01/home", headers=auth)
    assert response.status_code == 403


def test_result_projection_is_unavailable_before_any_submission(client: TestClient) -> None:
    auth = _auth(client)

    result = client.get(f"/families/{FAMILY}/assessments/results/latest", headers=auth)

    assert result.status_code == 200, result.text
    assert result.json()["status"] == "NO_RESULT"
    assert result.json()["result"] is None


def test_result_projection_cross_family_request_is_rejected(client: TestClient) -> None:
    auth = _auth(client)

    result = client.get(f"/families/{OTHER_FAMILY}/assessments/results/latest", headers=auth)

    assert result.status_code == 403


def test_missing_credential_is_401_not_403(client: TestClient) -> None:
    """No usable credential and wrong-family credential are different answers.

    Collapsing them would tell a caller holding a valid token for family A that
    family B does not exist.
    """
    assert client.get(f"/families/{FAMILY}/ui/02/assessment").status_code == 401


def test_cross_family_request_is_rejected(client: TestClient) -> None:
    auth = _auth(client, family=FAMILY)
    assert client.get(f"/families/{OTHER_FAMILY}/ui/02/assessment", headers=auth).status_code == 403


def test_mutation_without_idempotency_key_is_rejected(client: TestClient) -> None:
    """Fails for the stated reason only.

    `subject_person_id` is a real UUID here so the request survives payload
    validation and is rejected by the missing-key check. The previous version
    passed a non-UUID and so never reached that check.
    """
    auth = _auth(client)
    response = client.post(
        f"/families/{FAMILY}/assessments/sessions",
        json={"subject_person_id": str(uuid.uuid4())},
        headers=auth,
    )
    assert response.status_code == 400
    assert "idempotency" in response.text.lower()


def test_malformed_subject_person_id_is_rejected(client: TestClient) -> None:
    """The rejection the old fixture was accidentally relying on, now explicit."""
    auth = _auth(client)
    response = client.post(
        f"/families/{FAMILY}/assessments/sessions",
        json={"subject_person_id": "child-a"},
        headers={**auth, "idempotency-key": "malformed-1"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "valid_subject_person_id_required"


def test_ui03_openapi_is_closed_and_discriminates_scorecards(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    operation = spec["paths"]["/families/{family_id}/ui/03/growth-hypothesis"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema == {
        "$ref": "#/components/schemas/Ui03GrowthHypothesisProjectionResponse"
    }

    schemas = spec["components"]["schemas"]
    projection = schemas["Ui03GrowthHypothesisProjectionResponse"]
    hypothesis = schemas["Ui03GrowthHypothesisModel"]
    source_refs = schemas["Ui03SourceRefsModel"]
    named_actions = schemas["Ui03NamedActionsModel"]
    deterministic = schemas["Ui03DeterministicScorecardModel"]
    gateway = schemas["Ui03ModelGatewayScorecardModel"]

    assert projection["additionalProperties"] is False
    assert set(projection["properties"]) == UI03_TOP_LEVEL_KEYS
    assert set(projection["required"]) == UI03_TOP_LEVEL_KEYS
    assert hypothesis["additionalProperties"] is False
    assert set(hypothesis["properties"]) == UI03_HYPOTHESIS_KEYS
    assert set(hypothesis["required"]) == UI03_HYPOTHESIS_KEYS
    assert source_refs["additionalProperties"] is False
    assert set(source_refs["properties"]) == UI03_SOURCE_REF_KEYS
    assert set(source_refs["required"]) == UI03_SOURCE_REF_KEYS
    assert named_actions["additionalProperties"] is False
    assert set(named_actions["properties"]) == {"confirm", "dismiss"}
    assert set(named_actions["required"]) == {"confirm", "dismiss"}
    assert deterministic["additionalProperties"] is False
    assert deterministic["required"] == ["generator"]

    scorecard = hypothesis["properties"]["scorecard"]
    assert scorecard["discriminator"] == {
        "propertyName": "generator",
        "mapping": {
            "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC": (
                "#/components/schemas/Ui03DeterministicScorecardModel"
            ),
            "MODEL_GATEWAY": "#/components/schemas/Ui03ModelGatewayScorecardModel",
        },
    }
    assert {item["$ref"] for item in scorecard["oneOf"]} == {
        "#/components/schemas/Ui03DeterministicScorecardModel",
        "#/components/schemas/Ui03ModelGatewayScorecardModel",
    }
    gateway_keys = {
        "generator",
        "agent_run_ref",
        "provider_ref",
        "model_ref",
        "model_version",
        "prompt_version",
        "schema_version",
        "context_snapshot_ref",
        "input_refs",
        "draft_status",
        "human_task_ref",
        "review_status",
    }
    assert gateway["additionalProperties"] is False
    assert set(gateway["properties"]) == gateway_keys
    assert set(gateway["required"]) == gateway_keys
    assert gateway["properties"]["input_refs"] == {
        "items": {"type": "string"},
        "type": "array",
        "title": "Input Refs",
    }
    assert _object_keys(
        {name: schemas[name] for name in schemas if name.startswith("Ui03")}
    ).isdisjoint(FORBIDDEN_SCORE_KEYS)
