from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.intelligence.experience.api import (
    get_multimodal_draft_runtime_resolver,
    router,
)
from backend.intelligence.experience.synthetic_runtime import SyntheticRuntimeResolver


def _body(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "prompt_version": "prompt.v1",
        "schema_version": "schema.v1",
        "payload": {"expression": "今天我们在一次小步骤上合作。"},
        "output_schema": {
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
        "modalities": ["TEXT"],
        "estimated_input_tokens": 64,
    }


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    resolver = SyntheticRuntimeResolver(
        tenant_id="tenant-run-routes", subject_ids=("guardian-run-routes",)
    )
    app.dependency_overrides[get_multimodal_draft_runtime_resolver] = lambda: resolver
    return TestClient(app)


def test_run_routes_record_interactions_and_scrub_deleted_replay() -> None:
    run_id = "run-http-001"
    with _client() as client:
        draft = client.post(
            "/families/family-http/experience/multimodal/drafts",
            json=_body(run_id),
            headers={"Idempotency-Key": "create-http-001"},
        )
        assert draft.status_code == 200, draft.text
        assert draft.json()["status"] == "DRAFT"

        decision = client.post(
            f"/families/family-http/experience/multimodal/runs/{run_id}/decisions",
            json={"decision": "confirm", "draft_version": "schema.v1"},
            headers={"Idempotency-Key": "decision-http-001"},
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["status"] == "recorded"

        feedback = client.post(
            f"/families/family-http/experience/multimodal/runs/{run_id}/feedback",
            json={"signal": "helpful", "draft_version": "schema.v1"},
            headers={"Idempotency-Key": "feedback-http-001"},
        )
        assert feedback.status_code == 200, feedback.text

        replay = client.get(
            f"/families/family-http/experience/multimodal/runs/{run_id}/replay"
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["status"] == "DRAFT"
        assert replay.json()["deletion_state"] == "active"
        assert len(replay.json()["entries"]) == 2
        assert replay.json()["draft_payload"]

        replayed_decision = client.post(
            f"/families/family-http/experience/multimodal/runs/{run_id}/decisions",
            json={"decision": "confirm", "draft_version": "schema.v1"},
            headers={"Idempotency-Key": "decision-http-001"},
        )
        assert replayed_decision.status_code == 200
        assert replayed_decision.json()["idempotency_replayed"] is True

        deleted = client.request(
            "DELETE",
            f"/families/family-http/experience/multimodal/runs/{run_id}",
            json={"reason": "用户请求删除体验记录"},
            headers={"Idempotency-Key": "delete-http-001"},
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["status"] == "deleted"

        deleted_replay = client.get(
            f"/families/family-http/experience/multimodal/runs/{run_id}/replay"
        )
        assert deleted_replay.status_code == 200
        assert deleted_replay.json()["deletion_state"] == "deleted"
        assert deleted_replay.json()["draft_payload"] is None
        assert deleted_replay.json()["artifact_refs"] == []

        after_delete = client.post(
            f"/families/family-http/experience/multimodal/runs/{run_id}/feedback",
            json={"signal": "helpful"},
            headers={"Idempotency-Key": "feedback-after-delete"},
        )
        assert after_delete.status_code == 410


def test_run_routes_require_idempotency_for_mutations_and_isolate_scope() -> None:
    run_id = "run-http-002"
    with _client() as client:
        draft = client.post(
            "/families/family-http/experience/multimodal/drafts",
            json=_body(run_id),
            headers={"Idempotency-Key": "create-http-002"},
        )
        assert draft.status_code == 200

        missing_key = client.post(
            f"/families/family-http/experience/multimodal/runs/{run_id}/decisions",
            json={"decision": "reject"},
        )
        assert missing_key.status_code == 422

        cross_scope = client.get(
            f"/families/other-family/experience/multimodal/runs/{run_id}/replay"
        )
        assert cross_scope.status_code == 403
