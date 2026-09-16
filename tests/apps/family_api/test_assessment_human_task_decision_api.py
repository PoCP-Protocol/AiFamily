from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.domains.assessment.api import dependencies, register_exception_handlers, router
from backend.domains.assessment.api.dependencies import FamilyContext

PATH = "/families/family-1/assessment/human-tasks/task-1/decisions"
AUTHORIZATION = {"Authorization": "Bearer guardian-session"}


class RecordingDecisionHandler:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def decide(self, task_id, *, outcome, reason, idempotency_key):
        self.calls.append(
            {
                "task_id": task_id,
                "outcome": outcome,
                "reason": reason,
                "idempotency_key": idempotency_key,
            }
        )
        return {
            "task_id": task_id,
            "decision_id": "assessment-decision:" + "a" * 64,
            "status": "DECIDED",
            "outcome": outcome,
            "reason": reason,
            "decided_at": "2026-09-17T08:00:00+00:00",
            "binding": None,
        }


def _client() -> tuple[TestClient, RecordingDecisionHandler]:
    app = FastAPI()
    app.include_router(router, prefix="/families")
    register_exception_handlers(app)
    handler = RecordingDecisionHandler()
    app.dependency_overrides[dependencies.get_family_context] = lambda: FamilyContext(
        "tenant-1",
        "family-1",
        "guardian-1",
    )
    app.dependency_overrides[dependencies.get_assessment_human_task_decision_handler] = lambda: (
        handler
    )
    return TestClient(app), handler


def test_decision_contract_accepts_only_outcome_reason_and_required_key() -> None:
    client, handler = _client()

    accepted = client.post(
        PATH,
        headers={**AUTHORIZATION, "Idempotency-Key": "mobile-decision-1"},
        json={"outcome": "ACCEPT", "reason": "  reviewed by guardian  "},
    )
    missing_key = client.post(PATH, headers=AUTHORIZATION, json={"outcome": "ACCEPT"})
    forged_scope = client.post(
        PATH,
        headers={**AUTHORIZATION, "Idempotency-Key": "forged"},
        json={"outcome": "ACCEPT", "scope_ref": "client-owned"},
    )
    reject_without_reason = client.post(
        PATH,
        headers={**AUTHORIZATION, "Idempotency-Key": "reject-no-reason"},
        json={"outcome": "REJECT"},
    )
    unsupported_outcome = client.post(
        PATH,
        headers={**AUTHORIZATION, "Idempotency-Key": "escalate"},
        json={"outcome": "ESCALATE", "reason": "not part of this contract"},
    )

    assert accepted.status_code == 200
    assert accepted.json()["binding"] is None
    assert handler.calls == [
        {
            "task_id": "task-1",
            "outcome": "ACCEPT",
            "reason": "reviewed by guardian",
            "idempotency_key": "mobile-decision-1",
        },
        {
            "task_id": "task-1",
            "outcome": "REJECT",
            "reason": None,
            "idempotency_key": "reject-no-reason",
        },
    ]
    assert missing_key.status_code == 422
    assert forged_scope.status_code == 422
    assert reject_without_reason.status_code == 200
    assert reject_without_reason.json()["reason"] is None
    assert unsupported_outcome.status_code == 422


def test_openapi_exposes_frozen_decision_path_and_server_binding() -> None:
    client, _ = _client()
    spec = client.get("/openapi.json").json()
    operation = spec["paths"]["/families/{family_id}/assessment/human-tasks/{task_id}/decisions"][
        "post"
    ]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    request_schema = spec["components"]["schemas"][request_ref.rsplit("/", 1)[-1]]
    key_parameter = next(
        item for item in operation["parameters"] if item["name"] == "Idempotency-Key"
    )
    authorization_parameter = next(
        item for item in operation["parameters"] if item["name"] == "Authorization"
    )
    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    response_schema = spec["components"]["schemas"][response_ref.rsplit("/", 1)[-1]]
    binding_ref = response_schema["properties"]["binding"]["anyOf"][0]["$ref"]
    binding_schema = spec["components"]["schemas"][binding_ref.rsplit("/", 1)[-1]]

    assert request_schema["additionalProperties"] is False
    assert set(request_schema["properties"]) == {"outcome", "reason"}
    assert key_parameter["required"] is True
    assert authorization_parameter["required"] is True
    assert set(binding_schema["required"]) == {
        "subject_person_id",
        "assessment_session_id",
        "hypothesis_ref",
        "scope_ref",
        "signal_version",
        "reviewed_draft_ref",
        "draft_version",
        "provenance_ref",
        "human_gate_receipt_ref",
    }
