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
