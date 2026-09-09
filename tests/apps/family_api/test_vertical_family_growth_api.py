import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.family_api.vertical_family_growth_api import router
from backend.intelligence.agi_vertical_runtime import EvaluationLedgerEntry
from backend.intelligence.context_engine.contracts import ContextContractError
from backend.intelligence.experience.run_http import RunHttpError
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft


class _Runtime:
    def __init__(self) -> None:
        self.entries = {}

    async def run(self, **kwargs):
        assert kwargs["family_id"] == "family-a"
        entry = EvaluationLedgerEntry(
            family_need_id=kwargs["family_need_id"],
            path_id=kwargs["path_id"],
            run_id=kwargs["run_id"],
            context_snapshot_ref="ctx:run-1",
            draft=ModelDraft(
                output={"understanding": "作业启动阻力", "next_step": "十分钟启动", "path": []},
                provenance=AiProvenance(
                    "fake",
                    "model",
                    "v1",
                    "vertical-growth.v1",
                    "vertical-growth-draft.v1",
                    "ctx:run-1",
                    1,
                    "MINOR_PERSONAL_DATA",
                    "vertical_family_growth",
                ),
            ),
            feedback_refs=(),
            knowledge_ref=kwargs["knowledge_ref"],
            knowledge_version="v1",
            lineage_ref="lineage:1",
        )
        self.entries[entry.run_id] = entry
        return entry

    def replay(self, *, run_id: str, family_id: str):
        if family_id != "family-a" or run_id not in self.entries:
            from backend.intelligence.agi_vertical_runtime import VerticalRuntimeError

            raise VerticalRuntimeError("CONTEXT_SCOPE_MISMATCH")
        return self.entries[run_id]

    def delete(self, *, run_id: str, family_id: str):
        self.replay(run_id=run_id, family_id=family_id)
        del self.entries[run_id]


def test_missing_vertical_runtime_fails_closed() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/families/family-a/growth/ai-drafts",
        json={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "run_id": "run-1",
            "knowledge_ref": "claim:1",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "vertical_family_growth_runtime_not_configured"


def test_vertical_draft_route_returns_draft_and_provenance() -> None:
    app = FastAPI()
    app.state.vertical_family_growth_runtime = _Runtime()
    app.include_router(router)
    response = TestClient(app).post(
        "/families/family-a/growth/ai-drafts",
        json={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "run_id": "run-1",
            "knowledge_ref": "claim:1",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["output"]["next_step"] == "十分钟启动"
    assert body["provenance"]["use_case"] == "vertical_family_growth"


def test_context_contract_errors_fail_closed_at_http_boundary() -> None:
    class ContextFailingRuntime(_Runtime):
        async def run(self, **kwargs):
            raise ContextContractError("CONTEXT_SNAPSHOT_EXPIRED")

    app = FastAPI()
    app.state.vertical_family_growth_runtime = ContextFailingRuntime()
    app.include_router(router)
    response = TestClient(app).post(
        "/families/family-a/growth/ai-drafts",
        json={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "run_id": "run-1",
            "knowledge_ref": "claim:1",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "CONTEXT_SNAPSHOT_EXPIRED"


def test_vertical_draft_replay_delete_and_cross_family_fail_closed() -> None:
    app = FastAPI()
    runtime = _Runtime()
    app.state.vertical_family_growth_runtime = runtime
    app.include_router(router)
    client = TestClient(app)
    payload = {
        "family_need_id": "need-1",
        "path_id": "path-1",
        "run_id": "run-1",
        "knowledge_ref": "claim:1",
    }
    assert client.post("/families/family-a/growth/ai-drafts", json=payload).status_code == 200
    replay = client.get("/families/family-a/growth/ai-drafts/run-1")
    assert replay.status_code == 200
    assert replay.json()["status"] == "DRAFT"
    foreign = client.get("/families/family-b/growth/ai-drafts/run-1")
    assert foreign.status_code == 404
    deleted = client.delete("/families/family-a/growth/ai-drafts/run-1")
    assert deleted.status_code == 204
    assert client.get("/families/family-a/growth/ai-drafts/run-1").status_code == 404


def test_guardian_decision_route_preserves_scope_and_conflict_status() -> None:
    class DecisionRuntime(_Runtime):
        async def decide(self, *, run_id: str, family_id: str, decision):
            if family_id != "family-a" or run_id not in self.entries:
                raise RunHttpError("RUN_SCOPE_MISMATCH")
            if decision.family_need_id != "need-1" or decision.path_id != "path-1":
                raise RunHttpError("GUARDIAN_DECISION_SCOPE_MISMATCH")
            return self.entries[run_id]

    app = FastAPI()
    runtime = DecisionRuntime()
    app.state.vertical_family_growth_runtime = runtime
    app.include_router(router)
    client = TestClient(app)
    payload = {
        "family_need_id": "need-1",
        "path_id": "path-1",
        "run_id": "run-1",
        "knowledge_ref": "claim:1",
    }
    assert client.post("/families/family-a/growth/ai-drafts", json=payload).status_code == 200
    decision_path = "/families/family-a/growth/ai-drafts/run-1/decisions"
    accepted = client.post(
        decision_path,
        json={
            "decision_ref": "decision:1",
            "family_need_id": "need-1",
            "path_id": "path-1",
            "state": "EDIT",
            "edits": {"next_step": "十分钟启动"},
        },
    )
    assert accepted.status_code == 200, accepted.text

    conflict = client.post(
        decision_path,
        json={
            "decision_ref": "decision:1",
            "family_need_id": "other-need",
            "path_id": "path-1",
            "state": "REJECT",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "GUARDIAN_DECISION_SCOPE_MISMATCH"


def test_guardian_decision_route_accepts_explicit_revision_run() -> None:
    class RevisionRuntime(_Runtime):
        async def revise(self, *, run_id, next_run_id, family_id, decision):
            assert run_id == "run-1"
            assert next_run_id == "run-2"
            return await self.run(
                family_need_id=decision.family_need_id,
                path_id=decision.path_id,
                run_id=next_run_id,
                family_id=family_id,
                knowledge_ref="claim:1",
            )

    app = FastAPI()
    runtime = RevisionRuntime()
    app.state.vertical_family_growth_runtime = runtime
    app.include_router(router)
    client = TestClient(app)
    client.post(
        "/families/family-a/growth/ai-drafts",
        json={
            "family_need_id": "need-1",
            "path_id": "path-1",
            "run_id": "run-1",
            "knowledge_ref": "claim:1",
        },
    )
    response = client.post(
        "/families/family-a/growth/ai-drafts/run-1/decisions",
        json={
            "decision_ref": "decision:revision",
            "family_need_id": "need-1",
            "path_id": "path-1",
            "state": "EDIT",
            "next_run_id": "run-2",
            "edits": {"next_step": "视觉计时器"},
        },
    )
    assert response.status_code == 200
    assert response.json()["run_id"] == "run-2"


def test_vertical_replay_and_delete_accept_async_runtime_methods() -> None:
    """Durable PostgreSQL runtimes expose awaitable replay/delete methods."""

    class AsyncRuntime(_Runtime):
        async def replay(self, *, run_id: str, family_id: str):
            if family_id != "family-a" or run_id not in self.entries:
                from backend.intelligence.agi_vertical_runtime import VerticalRuntimeError

                raise VerticalRuntimeError("CONTEXT_SCOPE_MISMATCH")
            return self.entries[run_id]

        async def delete(self, *, run_id: str, family_id: str):
            if family_id != "family-a" or run_id not in self.entries:
                from backend.intelligence.agi_vertical_runtime import VerticalRuntimeError

                raise VerticalRuntimeError("CONTEXT_SCOPE_MISMATCH")
            del self.entries[run_id]

    app = FastAPI()
    runtime = AsyncRuntime()
    app.state.vertical_family_growth_runtime = runtime
    app.include_router(router)
    client = TestClient(app)
    payload = {
        "family_need_id": "need-1",
        "path_id": "path-1",
        "run_id": "run-async",
        "knowledge_ref": "claim:1",
    }
    assert client.post("/families/family-a/growth/ai-drafts", json=payload).status_code == 200
    assert client.get("/families/family-a/growth/ai-drafts/run-async").status_code == 200
    assert client.delete("/families/family-a/growth/ai-drafts/run-async").status_code == 204


@pytest.mark.parametrize(
    ("operation", "error_code", "expected_status"),
    [
        ("replay", "RUN_NOT_FOUND", 404),
        ("replay", "RUN_SCOPE_MISMATCH", 404),
        ("delete", "RUN_NOT_FOUND", 404),
        ("delete", "IDEMPOTENCY_REPLAY_MISMATCH", 409),
    ],
)
def test_durable_ledger_errors_are_mapped_to_http(
    operation: str, error_code: str, expected_status: int
) -> None:
    """Expected durable isolation/idempotency failures must not leak as 500."""

    class DurableErrorRuntime(_Runtime):
        async def replay(self, *, run_id: str, family_id: str):
            raise RunHttpError(error_code)

        async def delete(self, *, run_id: str, family_id: str):
            raise RunHttpError(error_code)

    app = FastAPI()
    app.state.vertical_family_growth_runtime = DurableErrorRuntime()
    app.include_router(router)
    client = TestClient(app)
    path = "/families/family-a/growth/ai-drafts/run-missing"
    response = client.get(path) if operation == "replay" else client.delete(path)
    assert response.status_code == expected_status, response.text
    assert response.json()["detail"] == error_code


@pytest.mark.parametrize("field", ["family_need_id", "path_id", "run_id", "knowledge_ref"])
def test_vertical_draft_route_rejects_blank_identity(field: str) -> None:
    app = FastAPI()
    app.state.vertical_family_growth_runtime = _Runtime()
    app.include_router(router)
    payload = {
        "family_need_id": "need-1",
        "path_id": "path-1",
        "run_id": "run-1",
        "knowledge_ref": "claim:1",
    }
    payload[field] = ""
    response = TestClient(app).post("/families/family-a/growth/ai-drafts", json=payload)
    assert response.status_code == 422
