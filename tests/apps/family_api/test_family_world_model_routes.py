"""Smoke test for the Family World Model demo HTTP surface.

End-to-end against real PostgreSQL: statements -> conflict detection ->
hypothesis (FakeProvider-backed AgentRuntime, per
`tests/intelligence/context_engine/test_belief_engine.py`'s `_fake_runtime`
pattern) -> unknown -> clarification -> resolution -> belief state. Proves
the router's own wiring (DB session dependency, repository construction,
kernel call sequence, response shape) — not the kernel's own logic, which is
already covered by `tests/family_journeys/test_family_scene_001.py`.
"""

from __future__ import annotations

import importlib

import httpx
import pytest
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from backend.apps.family_api.family_world_model_routes import (
    get_hypothesis_agent_runtime,
    get_unknown_agent_runtime,
    get_world_model_connection,
)
from backend.apps.family_api.main import create_app
from backend.intelligence.agent_runtime.contracts import AgentDefinition
from backend.intelligence.agent_runtime.gateway_port import ModelGatewayExecutionPort
from backend.intelligence.agent_runtime.runtime import AgentRuntime
from backend.intelligence.context_engine.belief_engine import HYPOTHESIS_USE_CASE
from backend.intelligence.context_engine.unknown_engine import UNKNOWN_USE_CASE
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.safety.runtime import SafetyRuntime
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

_TARGET_PREDICATE = "child.parent_communication"
_ALLOWED_PREDICATES = (_TARGET_PREDICATE, "child.school_engagement")
_AGENT_ID = "family_world_model_cognition"


async def _apply_migrations(engine: AsyncEngine) -> None:
    def _run_upgrade(sync_connection, migration_module) -> None:
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        context = MigrationContext.configure(sync_connection, opts={"target_metadata": None})
        with Operations.context(context):
            migration_module.upgrade()

    for name in (
        "0080_ai_family_world_atoms",
        "0081_ai_family_world_conflicts",
        "0082_ai_family_world_atoms_projection_identity",
        "0083_ai_family_world_atoms_belief_metadata",
        "0084_ai_family_world_unknowns",
    ):
        module = importlib.import_module(f"database.migrations.versions.{name}")
        async with engine.begin() as connection:
            await connection.run_sync(lambda c, m=module: _run_upgrade(c, m))


def _fake_agent_runtime_factory(
    responses: dict[str, dict[str, object]], *, use_case: str
) -> AgentRuntime:
    """Mirrors `test_belief_engine.py`'s `_fake_runtime` helper: a real
    `AgentRuntime` backed by `FakeProvider` — no real LLM API call. Returns
    only the runtime: the route itself builds a fresh `AgentAuthorization`
    scoped to the request's own `family_id` (see
    `family_world_model_routes._build_authorization`)."""

    provider = FakeProvider(responses)
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="staging",
        registry=ProviderRegistry(
            (
                ProviderRecord(
                    provider_id=provider.provider_id,
                    vendor="aifamily-test",
                    model="fake",
                    model_version="1",
                    status="INTERNAL_APPROVED",
                    approved_environments=("staging",),
                    sub_delegates=False,
                    minor_data_allowed=True,
                    private_text_allowed=True,
                    security_assessment_ref="test",
                    processing_agreement_ref="test",
                    deletion_on_termination_committed=True,
                ),
            )
        ),
        safety_runtime=SafetyRuntime(),
    )
    definition = AgentDefinition(
        agent_id=_AGENT_ID,
        name="Family World Model Cognition (test)",
        allowed_use_cases=frozenset({use_case}),
        context_policy="test-context-policy",
        safety_policy="test-safety-policy",
        human_handoff_policy="test-handoff-policy",
        budget_policy="test-budget-policy",
    )
    return AgentRuntime(
        ModelGatewayExecutionPort(gateway, provider.provider_id),
        [definition],
    )


def _connection_override_factory(session_factory: async_sessionmaker):
    async def _override_connection():
        async with session_factory() as session:
            connection = await session.connection()
            try:
                yield connection
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override_connection


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_family_world_model_routes_end_to_end_over_http() -> None:
    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

        app = create_app()
        app.dependency_overrides[get_world_model_connection] = _connection_override_factory(
            session_factory
        )
        app.dependency_overrides[get_hypothesis_agent_runtime] = lambda: (
            _fake_agent_runtime_factory(
                {
                    HYPOTHESIS_USE_CASE: {
                        "statement": "母子沟通分歧可能源于批评先于倾听的互动习惯",
                        "support_level": "MODERATE",
                        "contradiction_level": "WEAK",
                        "uncertainty": "HIGH",
                        "evidence_atom_ids": [],  # patched per-request below
                    }
                },
                use_case=HYPOTHESIS_USE_CASE,
            )
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            family_id = "family-route-test-1"

            # --- Step 1: submit structured statements -> conflict detection
            submit_response = await client.post(
                f"/families/{family_id}/world-model/statements",
                json={
                    "statements": [
                        {
                            "speaker": "mother",
                            "epistemic_kind": "PERSPECTIVE",
                            "predicate": _TARGET_PREDICATE,
                            "text": "妈妈认为孩子最近完全不愿意沟通",
                            "subject_ids": ["child-1", "mother-1"],
                        },
                        {
                            "speaker": "child",
                            "epistemic_kind": "SELF_REPORT",
                            "predicate": _TARGET_PREDICATE,
                            "text": "孩子说自己愿意聊，但妈妈总是先批评",
                            "subject_ids": ["child-1"],
                        },
                    ]
                },
            )
            assert submit_response.status_code == 201, submit_response.text
            submit_body = submit_response.json()
            assert len(submit_body["atoms"]) == 2
            assert len(submit_body["conflicts"]) == 1
            mother_atom_id = next(
                a["atom_id"] for a in submit_body["atoms"] if a["asserted_by"] == "mother"
            )
            child_atom_id = next(
                a["atom_id"] for a in submit_body["atoms"] if a["asserted_by"] == "child"
            )
            for item in submit_body["atoms"]:
                assert item["epistemic_kind"] in ("PERSPECTIVE", "SELF_REPORT")

            # Re-override with the real evidence atom ids now known.
            app.dependency_overrides[get_hypothesis_agent_runtime] = lambda: (
                _fake_agent_runtime_factory(
                    {
                        HYPOTHESIS_USE_CASE: {
                            "statement": "母子沟通分歧可能源于批评先于倾听的互动习惯",
                            "support_level": "MODERATE",
                            "contradiction_level": "WEAK",
                            "uncertainty": "HIGH",
                            "evidence_atom_ids": [mother_atom_id, child_atom_id],
                        }
                    },
                    use_case=HYPOTHESIS_USE_CASE,
                )
            )

            # --- Step 2: generate hypothesis ------------------------------
            hypothesis_response = await client.post(
                f"/families/{family_id}/world-model/hypothesis",
                json={
                    "subject_ids": ["child-1", "mother-1"],
                    "target_predicate": _TARGET_PREDICATE,
                    "evidence_atom_ids": [mother_atom_id, child_atom_id],
                },
            )
            assert hypothesis_response.status_code == 201, hypothesis_response.text
            hypothesis_body = hypothesis_response.json()["hypothesis"]
            assert hypothesis_body["epistemic_kind"] == "HYPOTHESIS"
            assert hypothesis_body["support_level"] == "MODERATE"
            assert hypothesis_body["contradiction_level"] == "WEAK"
            assert hypothesis_body["uncertainty"] == "HIGH"
            hypothesis_atom_id = hypothesis_body["atom_id"]

            # --- Step 3: generate unknown ----------------------------------
            app.dependency_overrides[get_unknown_agent_runtime] = lambda: (
                _fake_agent_runtime_factory(
                    {
                        UNKNOWN_USE_CASE: {
                            "question": "孩子认为改善沟通最需要从哪一步开始？",
                            "why_it_matters": "直接了解孩子的期待比第三方猜测更可靠",
                            "target_predicate": _TARGET_PREDICATE,
                            "decision_impact": "HIGH",
                            "answerability": "MEDIUM",
                            "urgency": "MEDIUM",
                            "preferred_source": "PARENT_CHILD_INTERVIEW",
                            "blocking_hypothesis_ids": [hypothesis_atom_id],
                        }
                    },
                    use_case=UNKNOWN_USE_CASE,
                )
            )
            unknown_response = await client.post(
                f"/families/{family_id}/world-model/unknown",
                json={
                    "subject_ids": ["child-1", "mother-1"],
                    "hypothesis_atom_ids": [hypothesis_atom_id],
                    "allowed_target_predicates": list(_ALLOWED_PREDICATES),
                },
            )
            assert unknown_response.status_code == 201, unknown_response.text
            unknown_body = unknown_response.json()["unknown"]
            assert unknown_body is not None
            assert unknown_body["status"] == "OPEN"
            unknown_id = unknown_body["unknown_id"]

            # --- Step 4: resolve unknown with a new clarification ----------
            resolve_response = await client.post(
                f"/families/{family_id}/world-model/unknown/{unknown_id}/resolve",
                json={
                    "clarification": {
                        "speaker": "mother",
                        "epistemic_kind": "OTHER_REPORT",
                        "predicate": _TARGET_PREDICATE,
                        "text": "妈妈说其实一谈学习才会不愿聊",
                        "subject_ids": ["child-1", "mother-1"],
                    }
                },
            )
            assert resolve_response.status_code == 200, resolve_response.text
            resolve_body = resolve_response.json()
            assert resolve_body["unknown"]["status"] == "RESOLVED"

            # --- Step 5: belief state read ----------------------------------
            belief_response = await client.get(
                f"/families/{family_id}/world-model/belief-state",
                params={"subject_ids": "child-1,mother-1"},
            )
            assert belief_response.status_code == 200, belief_response.text
            belief_body = belief_response.json()
            hypothesis_ids = {h["atom_id"] for h in belief_body["hypotheses"]}
            assert hypothesis_atom_id in hypothesis_ids
            hypothesis_item = next(
                h for h in belief_body["hypotheses"] if h["atom_id"] == hypothesis_atom_id
            )
            assert hypothesis_item["epistemic_kind"] == "HYPOTHESIS"
            assert hypothesis_item["support_level"] == "MODERATE"
            # The resolved Unknown must not appear as still-open.
            assert belief_body["effective_open_unknowns"] == []
            perspective_ids = {p["atom_id"] for p in belief_body["perspectives"]}
            self_report_ids = {s["atom_id"] for s in belief_body["self_reports"]}
            assert mother_atom_id in perspective_ids
            assert child_atom_id in self_report_ids


@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_hypothesis_endpoint_fails_closed_without_real_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a real model provider configured, the endpoint must return a
    clear 503 rather than silently using a fake provider (task constraint)."""

    monkeypatch.delenv("AIFAMILY_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("AIFAMILY_MODEL_BASE_URL", raising=False)

    async with postgres_schema_engine(MetaData()) as engine:
        await _apply_migrations(engine)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

        app = create_app()
        app.dependency_overrides[get_world_model_connection] = _connection_override_factory(
            session_factory
        )
        # No override for get_hypothesis_agent_runtime: exercises the real
        # `build_real_agent_runtime`, which must fail closed with 503 when
        # AIFAMILY_MODEL_API_KEY/AIFAMILY_MODEL_BASE_URL are unset.

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            family_id = "family-route-test-503"

            submit_response = await client.post(
                f"/families/{family_id}/world-model/statements",
                json={
                    "statements": [
                        {
                            "speaker": "self",
                            "epistemic_kind": "SELF_REPORT",
                            "predicate": _TARGET_PREDICATE,
                            "text": "我说了一句话",
                            "subject_ids": ["child-1"],
                        }
                    ]
                },
            )
            assert submit_response.status_code == 201, submit_response.text
            atom_id = submit_response.json()["atoms"][0]["atom_id"]

            response = await client.post(
                f"/families/{family_id}/world-model/hypothesis",
                json={
                    "subject_ids": ["child-1"],
                    "target_predicate": _TARGET_PREDICATE,
                    "evidence_atom_ids": [atom_id],
                },
            )
            assert response.status_code == 503, response.text
            assert "world_model_no_real_model_provider_configured" in response.json()["detail"]
