"""Default composition-root HTTP proof for the vertical growth slice."""

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.apps.family_api.main import create_app
from backend.apps.family_api.production_vertical_family_growth_wiring import (
    ProductionVerticalFamilyGrowthComposition,
)
from backend.intelligence.agi_vertical_durable import DurableVerticalLedgerAdapter
from backend.intelligence.agi_vertical_runtime import EvaluationLedger, VerticalFamilyGrowthRuntime


class _DurablePort:
    durability_mode = "DURABLE"

    async def read(self, **kwargs):
        raise AssertionError("not called")


class _DurableBroker(_DurablePort):
    async def append(self, observation):
        raise AssertionError("not called")

    async def snapshot(self, *args, **kwargs):
        raise AssertionError("not called")

    async def delete_subject(self, *args, **kwargs):
        raise AssertionError("not called")


def test_create_app_accepts_explicit_production_composition(monkeypatch) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "production")
    runtime = VerticalFamilyGrowthRuntime(
        gateway=_DurablePort(),
        context=_DurablePort(),
        knowledge=_DurablePort(),
        feedback=_DurablePort(),
        ledger=EvaluationLedger(),
    )
    composition = ProductionVerticalFamilyGrowthComposition(
        environment="production",
        session_factory=async_sessionmaker(),
        runtime=runtime,
        context_broker=_DurableBroker(),
        durable_ledger=DurableVerticalLedgerAdapter(_DurablePort()),
        scope_factory=lambda family_id: __import__(
            "backend.intelligence.experience.run_http",
            fromlist=["RunScope"],
        ).RunScope(family_id, family_id, (f"subject:{family_id}",)),
    )

    app = create_app(production_vertical_family_growth_composition=composition)

    assert app.state.vertical_family_growth_runtime is not runtime


def test_default_test_composition_supports_draft_replay_isolation_and_delete(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIFAMILY_ENV", "test")
    client = TestClient(create_app())
    payload = {
        "family_need_id": "need-default-http",
        "path_id": "path-default-http",
        "run_id": "run-default-http",
        "knowledge_ref": "vertical-growth.v1",
    }

    created = client.post(
        "/families/family-default/growth/ai-drafts",
        json=payload,
    )
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "DRAFT"
    assert created.json()["provenance"]["use_case"] == "vertical_family_growth"

    replay = client.get("/families/family-default/growth/ai-drafts/run-default-http")
    assert replay.status_code == 200, replay.text
    assert replay.json()["run_id"] == payload["run_id"]

    cross_family = client.get("/families/other-family/growth/ai-drafts/run-default-http")
    assert cross_family.status_code == 404

    deleted = client.delete("/families/family-default/growth/ai-drafts/run-default-http")
    assert deleted.status_code == 204, deleted.text
    assert (
        client.get("/families/family-default/growth/ai-drafts/run-default-http").status_code == 404
    )
