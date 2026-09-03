from __future__ import annotations

from dataclasses import replace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.intelligence.experience.api import (
    MultimodalDraftRuntime,
    get_multimodal_draft_runtime,
    get_multimodal_draft_runtime_resolver,
    router,
)
from backend.intelligence.experience.run_http import InMemoryExperienceRunLedger
from backend.intelligence.experience.standard_assets import (
    build_family_experience_assets,
    family_experience_output_schema,
)
from backend.intelligence.experience.synthetic_runtime import (
    SyntheticRuntimeResolver,
    build_synthetic_runtime,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError

_ASSETS = build_family_experience_assets()


def _body(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "prompt_version": _ASSETS.prompt.version,
        "schema_version": _ASSETS.schema.version,
        "payload": {"expression": "今天我们在一次小步骤上合作。"},
        "output_schema": family_experience_output_schema(),
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


def test_draft_create_replays_without_a_second_application_invocation() -> None:
    base_runtime = build_synthetic_runtime(
        family_id="family-http",
        tenant_id="tenant-http",
        subject_ids=("guardian-http",),
    )

    class CountingApplication:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_draft(self, command):  # type: ignore[no-untyped-def]
            self.calls += 1
            return await base_runtime.application.generate_draft(command)

    application = CountingApplication()
    runtime: MultimodalDraftRuntime = replace(
        base_runtime,
        application=application,
        run_ledger=InMemoryExperienceRunLedger(),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime] = lambda: runtime

    with TestClient(app) as client:
        first = client.post(
            "/families/family-http/experience/multimodal/drafts",
            json=_body("run-http-preflight"),
            headers={"Idempotency-Key": "create-preflight"},
        )
        replay = client.post(
            "/families/family-http/experience/multimodal/drafts",
            json=_body("run-http-preflight"),
            headers={"Idempotency-Key": "create-preflight"},
        )
        conflict = client.post(
            "/families/family-http/experience/multimodal/drafts",
            json=_body("run-http-preflight") | {"payload": {"expression": "改过的表达"}},
            headers={"Idempotency-Key": "create-preflight"},
        )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert conflict.status_code == 409, conflict.text
    assert application.calls == 1


def test_provider_failure_releases_draft_preflight_for_safe_retry() -> None:
    base_runtime = build_synthetic_runtime(
        family_id="family-http",
        tenant_id="tenant-http",
        subject_ids=("guardian-http",),
    )

    class FlakyApplication:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_draft(self, command):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                raise ModelGatewayError("NETWORK_ERROR", "transient")
            return await base_runtime.application.generate_draft(command)

    application = FlakyApplication()
    runtime = replace(
        base_runtime,
        application=application,
        run_ledger=InMemoryExperienceRunLedger(),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_draft_runtime] = lambda: runtime

    with TestClient(app) as client:
        failed = client.post(
            "/families/family-http/experience/multimodal/drafts",
            json=_body("run-http-retry"),
            headers={"Idempotency-Key": "create-retry"},
        )
        retried = client.post(
            "/families/family-http/experience/multimodal/drafts",
            json=_body("run-http-retry"),
            headers={"Idempotency-Key": "create-retry"},
        )

    assert failed.status_code == 503
    assert retried.status_code == 200, retried.text
    assert application.calls == 2
