"""Real-PostgreSQL HTTP lifecycle for a governed multimodal draft."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, make_url, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.apps.family_api.main import create_app
from backend.intelligence.context_engine.contracts import (
    ContextScope,
    DataClass,
    StateObservation,
)
from backend.intelligence.context_engine.sql_store import (
    AsyncSqlContextBroker,
    ContextSnapshotObservationRow,
    ContextSnapshotRow,
)
from backend.intelligence.experience.api import MultimodalDraftRuntime
from backend.intelligence.experience.family_problem_understanding_contract import (
    FamilyConversationTurn,
)
from backend.intelligence.experience.family_problem_understanding_feedback import (
    FamilyUnderstandingFeedback,
    apply_parent_feedback_to_eval_spec,
    project_family_understanding_feedback,
    record_family_understanding_feedback,
)
from backend.intelligence.experience.family_problem_understanding_knowledge import (
    FamilyUnderstandingKnowledgeRetriever,
)
from backend.intelligence.experience.family_problem_understanding_preparation import (
    FamilyProblemUnderstandingPreparer,
)
from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import (
    MultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
)
from backend.intelligence.experience.run_http import RunScope
from backend.intelligence.experience.run_store import ExperienceRunRow
from backend.intelligence.experience.sql_run_ledger import (
    CommittedExperienceRunLedger,
    ExperienceRunInteractionRow,
    SessionPerCallExperienceRunLedger,
    SqlAlchemyExperienceRunLedger,
)
from backend.intelligence.knowledge.contracts import KnowledgeClaim, KnowledgeSource
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.model_gateway.contracts import StructuredRequest
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import (
    ModelDraftRow,
    SqlAlchemyModelDraftRegistry,
)
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import (
    FakeProvider,
    deterministic_provider,
)
from backend.intelligence.model_gateway.providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from backend.packages.contracts.evidence import Provenance
from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url

REPO_ROOT = Path(__file__).resolve().parents[3]
TENANT_ID = "tenant-s3-http"
FAMILY_ID = "family-s3-http"
SUBJECT_ID = "child-s3-http"
RUN_ID = "run-s3-http-delete"
PURPOSE = "family-understanding-multimodal"
PROVIDER_ID = "synthetic-http-provider"
POSTGRES_CONTAINER_ENV_VAR = "AIFAMILY_TEST_POSTGRES_CONTAINER"


@pytest.fixture
async def migrated_database_url() -> str:
    admin_url = postgres_test_url()
    if admin_url is None:
        pytest.skip(SKIP_REASON)
    database_name = f"s3_http_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        connect_args={"statement_cache_size": 0},
    )
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        await admin.dispose()
        database_url = (
            make_url(admin_url).set(database=database_name).render_as_string(hide_password=False)
        )
        migration = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, DATABASE_URL_ENV_VAR: database_url},
        )
        assert migration.returncode == 0, migration.stdout + migration.stderr
        yield database_url
    finally:
        await admin.dispose()
        cleanup_admin = create_async_engine(
            admin_url,
            isolation_level="AUTOCOMMIT",
            connect_args={"statement_cache_size": 0},
        )
        try:
            async with cleanup_admin.connect() as connection:
                await connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                    ),
                    {"database_name": database_name},
                )
                await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        finally:
            await cleanup_admin.dispose()


def _restart_postgres_if_requested(database_url: str) -> None:
    container_name = os.environ.get(POSTGRES_CONTAINER_ENV_VAR, "").strip()
    if not container_name:
        return
    restarted = subprocess.run(
        ["docker", "restart", container_name],
        capture_output=True,
        text=True,
    )
    assert restarted.returncode == 0, restarted.stdout + restarted.stderr
    url = make_url(database_url)
    for _ in range(60):
        ready = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "pg_isready",
                "-U",
                url.username or "",
                "-d",
                url.database or "",
            ],
            capture_output=True,
            text=True,
        )
        if ready.returncode == 0:
            return
        time.sleep(0.25)
    raise AssertionError(f"PostgreSQL container did not become ready: {container_name}")


def _scope() -> ContextScope:
    return ContextScope(
        tenant_id=TENANT_ID,
        region_id="CN",
        family_id=FAMILY_ID,
        subject_ids=(SUBJECT_ID,),
        purpose=PURPOSE,
        consent_version="consent.synthetic.v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref=f"delete:{TENANT_ID}:{FAMILY_ID}",
        correlation_id=f"correlation:{RUN_ID}",
        causation_id=f"causation:{RUN_ID}",
    )


def _observation() -> StateObservation:
    now = datetime.now(UTC)
    return StateObservation(
        observation_id=f"observation:{RUN_ID}",
        tenant_id=TENANT_ID,
        family_id=FAMILY_ID,
        subject_id=SUBJECT_ID,
        dimension="homework_transition",
        observed_value="晚间作业启动时容易发生拉扯",
        evidence_refs=(f"evidence:{RUN_ID}",),
        provenance="synthetic-http-e2e",
        observed_at=now,
        data_class=DataClass.SYNTHETIC,
        purpose=PURPOSE,
        consent_version="consent.synthetic.v1",
        consent_granted=True,
        region_id="CN",
        locale="zh-CN",
        deletion_ref=f"delete:{TENANT_ID}:{FAMILY_ID}",
        correlation_id=f"correlation:{RUN_ID}",
        causation_id=f"causation:{RUN_ID}",
        expires_at=now + timedelta(hours=1),
        retention_policy="synthetic-e2e-1h",
    )


def _provider_stack(*, dynamic: bool = False) -> tuple[FakeProvider, ModelGateway, object]:
    provider = (
        deterministic_provider(
            _dynamic_family_understanding_output,
            provider_id=PROVIDER_ID,
        )
        if dynamic
        else FakeProvider(
            {PURPOSE: _family_understanding_output()},
            provider_id=PROVIDER_ID,
        )
    )
    record = ProviderRecord(
        provider_id=PROVIDER_ID,
        vendor="aifamily-test",
        model="fake-multimodal",
        model_version="1.0",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        sub_delegates=False,
        security_assessment_ref="synthetic-only",
        processing_agreement_ref="synthetic-only",
        deletion_on_termination_committed=True,
        processing_region="local-test",
    )
    gateway = ModelGateway(
        {PROVIDER_ID: provider},
        environment="test",
        registry=ProviderRegistry((record,)),
    )
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id=PROVIDER_ID,
        vendor="aifamily-test",
        model="fake-multimodal",
        model_version="1.0",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
        security_assessment_ref="synthetic-only",
        processing_agreement_ref="synthetic-only",
        deletion_on_termination_committed=True,
    )
    return provider, gateway, profile


def _openai_compatible_provider_stack(
    captured_requests: list[dict[str, object]],
) -> tuple[OpenAICompatibleProvider, ModelGateway, object, httpx.AsyncClient]:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-live-key"
        body = json.loads(request.content)
        captured_requests.append(body)
        user_content = body["messages"][1]["content"]
        assert isinstance(user_content, list)
        payload = json.loads(user_content[0]["text"])
        turns = payload["conversation_turns"]
        latest = turns[-1]
        output = _family_understanding_output(
            text_ref=latest["input_ref"],
            expression=latest["text"],
        )
        return httpx.Response(
            200,
            json={
                "model": "vision-generative-2026-09-03",
                "choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}],
                "usage": {
                    "prompt_tokens": 321,
                    "completion_tokens": 456,
                    "total_tokens": 777,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        provider_id="openai-compatible-s3-livecheck",
        base_url="https://model.example.invalid/v1",
        api_key="test-live-key",
        model="vision-generative",
        client=client,
    )
    record = ProviderRecord(
        provider_id=provider.provider_id,
        vendor="openai-compatible-livecheck",
        model="vision-generative",
        model_version="2026-09-03",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        sub_delegates=False,
        security_assessment_ref="synthetic-contract-test",
        processing_agreement_ref="synthetic-contract-test",
        deletion_on_termination_committed=True,
        processing_region="mock-transport",
    )
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="test",
        registry=ProviderRegistry((record,)),
    )
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id=provider.provider_id,
        vendor="openai-compatible-livecheck",
        model="vision-generative",
        model_version="2026-09-03",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
        security_assessment_ref="synthetic-contract-test",
        processing_agreement_ref="synthetic-contract-test",
        deletion_on_termination_committed=True,
    )
    return provider, gateway, profile, client


def _family_understanding_output(
    *,
    text_ref: str = f"input:{RUN_ID}:concern",
    expression: str = "每天一到写作业就开始争吵",
) -> dict[str, object]:
    return {
        "understanding": {
            "lived_experience": f"你提到“{expression}”，家长和孩子都像被推入反复催促的拉扯。",
            "central_tension": "尽快开始作业的现实压力，与孩子进入任务所需的节奏发生冲突。",
            "care_intent": "家长既在意学习责任，也希望关系不被每天的催促消耗。",
        },
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "作业启动前的转换可能比作业本身更困难。",
                "rationale": "冲突集中在开始时刻，需要先区分转换困难与任务难度。",
                "evidence": [
                    {
                        "source_type": "PARENT_TEXT",
                        "source_ref": text_ref,
                        "observation": expression,
                    },
                    {
                        "source_type": "AUTHORIZED_IMAGE",
                        "source_ref": "media:authorized:family-scene",
                        "observation": "家长授权提供了与作业场景有关的图片。",
                    },
                ],
                "knowledge_refs": ["knowledge:task-transition-reviewed-v1"],
                "confidence": "MEDIUM",
                "disconfirming_evidence_needed": "需要了解已经顺利开始作业的例外时刻。",
            }
        ],
        "unknowns": [
            {
                "unknown_id": "U1",
                "description": "最近一次顺利开始作业时有什么不同",
                "why_it_matters": "这能区分环境转换问题与任务本身的困难",
                "related_hypothesis_ids": ["H1"],
            }
        ],
        "follow_up_questions": [
            {
                "question_id": "Q1",
                "question": "最近一次没有争吵就开始作业时，当时有什么不同？",
                "purpose": "寻找能够修正当前解释的真实例外",
                "answers_unknown_ids": ["U1"],
            }
        ],
        "strengths": [
            {
                "statement": "家长已经意识到反复催促正在消耗关系。",
                "evidence_refs": [text_ref],
                "why_it_matters": "这种觉察是重新理解互动循环的重要起点。",
            }
        ],
        "desired_change": {
            "statement": "希望孩子能更平稳地开始作业，家长不必反复催促。",
            "basis": "EXPLICIT",
            "observable_signs": ["催促次数减少", "开始作业前能够完成一次平静沟通"],
            "confirmation_question": "这是否是你最希望先看到的变化？",
        },
        "limitations": ["目前主要依据家长本轮表达，仍需孩子视角与例外情境来校正。"],
    }


def _dynamic_family_understanding_output(request: StructuredRequest) -> dict[str, object]:
    turns = request.payload.get("conversation_turns")
    if not isinstance(turns, (tuple, list)) or not turns:
        return _family_understanding_output()
    last_turn = turns[-1]
    if not isinstance(last_turn, dict):
        return _family_understanding_output()
    text_ref = last_turn.get("input_ref")
    expression = last_turn.get("text")
    if not isinstance(text_ref, str) or not isinstance(expression, str):
        return _family_understanding_output()
    return _family_understanding_output(text_ref=text_ref, expression=expression)


def _family_understanding_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": [
            "understanding",
            "hypotheses",
            "unknowns",
            "follow_up_questions",
            "strengths",
            "desired_change",
            "limitations",
        ],
        "properties": {
            "understanding": {"type": "object"},
            "hypotheses": {"type": "array", "minItems": 1},
            "unknowns": {"type": "array", "minItems": 1},
            "follow_up_questions": {"type": "array", "minItems": 1},
            "strengths": {"type": "array", "minItems": 1},
            "desired_change": {"type": "object"},
            "limitations": {"type": "array", "minItems": 1},
        },
    }


def _request_body(
    *,
    run_id: str = RUN_ID,
    prior_run_id: str | None = None,
    conversation_turns: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    text_input_ref = f"input:{run_id}:concern"
    media_ref = "media:authorized:family-scene"
    turns = conversation_turns or [
        {
            "input_ref": text_input_ref,
            "kind": "CONCERN",
            "text": "每天一到写作业就开始争吵",
            "created_at": "2026-09-03T09:00:00+08:00",
        }
    ]
    return {
        "run_id": run_id,
        "prompt_version": "family-understanding.v1",
        "schema_version": "family-understanding-output.v1",
        "payload": {
            "guardian_text": "每天一到写作业就开始争吵",
            "conversation_turns": turns,
            "prior_run_id": prior_run_id,
        },
        "output_schema": _family_understanding_schema(),
        "modalities": ["TEXT", "IMAGE"],
        "estimated_input_tokens": 256,
        "input_refs": [*(turn["input_ref"] for turn in turns), media_ref],
        "media_inputs": [
            {
                "media_type": "IMAGE",
                "uri": media_ref,
                "mime_type": "image/png",
                "sha256": "a" * 64,
            }
        ],
    }


class _RuntimeResolver:
    def __init__(self, runtime: MultimodalDraftRuntime) -> None:
        self._runtime = runtime

    async def resolve(self, family_id: str) -> MultimodalDraftRuntime:
        if family_id != self._runtime.scope.family_id:
            raise PermissionError("family_access_denied")
        return self._runtime


def _app(runtime: MultimodalDraftRuntime) -> FastAPI:
    return create_app(experience_runtime_resolver=_RuntimeResolver(runtime))


class _NeverCalledApplication:
    async def generate_draft(self, command: object) -> object:
        raise AssertionError("deleted replay must not invoke generation")


@pytest.mark.asyncio
async def test_multimodal_http_delete_survives_new_engine_and_session(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = AsyncSqlContextBroker(factory)
    await context.append(_observation())
    session = factory()
    registry = SqlAlchemyModelDraftRegistry(session)
    provider, gateway, profile = _provider_stack()
    application = ContextBoundMultimodalExperienceService(
        context=context,
        routed=RoutedMultimodalExperienceService(
            router=MultimodalRouter((profile,)),
            generation=MultimodalExperienceService(gateway, registry=registry),
        ),
        registry=registry,
    )
    runtime = MultimodalDraftRuntime(
        scope=_scope(),
        application=application,
        environment="test",
        run_ledger=CommittedExperienceRunLedger(SqlAlchemyExperienceRunLedger(session), session),
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(runtime)),
        base_url="http://aifamily.test",
    ) as client:
        invalid_body = _request_body()
        invalid_body["payload"] = {"parent_message": "每天一到写作业就开始争吵"}
        invalid = await client.post(
            f"/families/{FAMILY_ID}/experience/multimodal/drafts",
            headers={"Idempotency-Key": f"create:{RUN_ID}"},
            json=invalid_body,
        )
        assert invalid.status_code == 422
        assert invalid.json() == {"detail": "TEXT_OBSERVATION_REQUIRED"}
        assert len(provider.invocations) == 0
        for row_type in (
            ContextSnapshotRow,
            ContextSnapshotObservationRow,
            ExperienceRunRow,
            ModelDraftRow,
        ):
            assert await session.scalar(select(func.count()).select_from(row_type)) == 0

        created = await client.post(
            f"/families/{FAMILY_ID}/experience/multimodal/drafts",
            headers={"Idempotency-Key": f"create:{RUN_ID}"},
            json=_request_body(),
        )
        assert created.status_code == 200
        assert created.json()["output"] == _family_understanding_output()
        draft_id = created.json()["draft_id"]
        assert len(provider.invocations) == 1
        invocation = provider.invocations[0]
        assert invocation.payload["conversation_turns"] == (
            {
                "input_ref": f"input:{RUN_ID}:concern",
                "kind": "CONCERN",
                "text": "每天一到写作业就开始争吵",
                "created_at": "2026-09-03T09:00:00+08:00",
            },
        )
        assert invocation.payload["prior_run_id"] is None
        normalized = invocation.payload["normalized_observations"]
        assert normalized[0]["source_refs"] == (f"input:{RUN_ID}:concern",)
        assert normalized[1]["source_refs"] == ("media:authorized:family-scene",)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ModelDraftRow)
                .where(
                    ModelDraftRow.tenant_id == TENANT_ID,
                    ModelDraftRow.draft_id == draft_id,
                )
            )
            == 1
        )
        await session.rollback()

        deleted = await client.request(
            "DELETE",
            f"/families/{FAMILY_ID}/experience/multimodal/runs/{RUN_ID}",
            headers={"Idempotency-Key": f"delete:{RUN_ID}"},
            json={"reason": "家长要求删除本次草案"},
        )
        assert deleted.status_code == 200
        replay = await client.get(
            f"/families/{FAMILY_ID}/experience/multimodal/runs/{RUN_ID}/replay"
        )
        assert replay.status_code == 200
        assert replay.json()["deletion_state"] == "deleted"
        assert replay.json()["draft_payload"] is None
        assert replay.json()["artifact_refs"] == []
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ModelDraftRow)
                .where(
                    ModelDraftRow.tenant_id == TENANT_ID,
                    ModelDraftRow.draft_id == draft_id,
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ExperienceRunInteractionRow)
                .where(
                    ExperienceRunInteractionRow.tenant_id == TENANT_ID,
                    ExperienceRunInteractionRow.run_id == RUN_ID,
                )
            )
            == 1
        )
    await session.close()
    await engine.dispose()
    _restart_postgres_if_requested(migrated_database_url)

    restarted_engine = create_async_engine(migrated_database_url)
    restarted_factory = async_sessionmaker(restarted_engine, expire_on_commit=False)
    restarted_session: AsyncSession = restarted_factory()
    restarted_runtime = MultimodalDraftRuntime(
        scope=_scope(),
        application=_NeverCalledApplication(),  # type: ignore[arg-type]
        environment="test",
        run_ledger=CommittedExperienceRunLedger(
            SqlAlchemyExperienceRunLedger(restarted_session), restarted_session
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(restarted_runtime)),
        base_url="http://aifamily.test",
    ) as client:
        replay = await client.get(
            f"/families/{FAMILY_ID}/experience/multimodal/runs/{RUN_ID}/replay"
        )
        recreate = await client.post(
            f"/families/{FAMILY_ID}/experience/multimodal/drafts",
            headers={"Idempotency-Key": f"create:{RUN_ID}"},
            json=_request_body(),
        )
    assert replay.status_code == 200
    assert replay.json()["deletion_state"] == "deleted"
    assert recreate.status_code == 410
    assert recreate.json() == {"detail": "RUN_DELETED"}
    assert (
        await restarted_session.scalar(
            select(func.count())
            .select_from(ModelDraftRow)
            .where(ModelDraftRow.tenant_id == TENANT_ID)
        )
        == 0
    )
    await restarted_session.close()
    await restarted_engine.dispose()


@pytest.mark.asyncio
async def test_follow_up_regenerates_and_replays_after_postgres_restart(
    migrated_database_url: str,
) -> None:
    first_run_id = "run-s3-http-concern"
    follow_up_run_id = "run-s3-http-follow-up"
    concern_ref = f"input:{first_run_id}:concern"
    follow_up_ref = f"input:{follow_up_run_id}:follow-up"
    concern_text = "每天一到写作业就开始争吵"
    follow_up_text = "上周有一次我先陪他把第一道题读完，后面就没有再催。"
    turns = [
        {
            "input_ref": concern_ref,
            "kind": "CONCERN",
            "text": concern_text,
            "created_at": "2026-09-03T09:00:00+08:00",
        },
        {
            "input_ref": follow_up_ref,
            "kind": "FOLLOW_UP",
            "text": follow_up_text,
            "created_at": "2026-09-03T09:08:00+08:00",
        },
    ]

    engine = create_async_engine(migrated_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = AsyncSqlContextBroker(factory)
    await context.append(_observation())
    session = factory()
    registry = SqlAlchemyModelDraftRegistry(session)
    provider, gateway, profile = _provider_stack(dynamic=True)
    application = ContextBoundMultimodalExperienceService(
        context=context,
        routed=RoutedMultimodalExperienceService(
            router=MultimodalRouter((profile,)),
            generation=MultimodalExperienceService(gateway, registry=registry),
        ),
        registry=registry,
    )
    runtime = MultimodalDraftRuntime(
        scope=_scope(),
        application=application,
        environment="test",
        run_ledger=CommittedExperienceRunLedger(SqlAlchemyExperienceRunLedger(session), session),
    )

    async with AsyncClient(
        transport=ASGITransport(app=_app(runtime)),
        base_url="http://aifamily.test",
    ) as client:
        first = await client.post(
            f"/families/{FAMILY_ID}/experience/multimodal/drafts",
            headers={"Idempotency-Key": f"create:{first_run_id}"},
            json=_request_body(
                run_id=first_run_id,
                conversation_turns=[turns[0]],
            ),
        )
        assert first.status_code == 200, first.text
        assert concern_text in first.json()["output"]["understanding"]["lived_experience"]

        follow_up = await client.post(
            f"/families/{FAMILY_ID}/experience/multimodal/drafts",
            headers={"Idempotency-Key": f"create:{follow_up_run_id}"},
            json=_request_body(
                run_id=follow_up_run_id,
                prior_run_id=first_run_id,
                conversation_turns=turns,
            ),
        )
        assert follow_up.status_code == 200, follow_up.text
        follow_up_payload = follow_up.json()["output"]
        assert follow_up_text in follow_up_payload["understanding"]["lived_experience"]
        assert follow_up_payload["hypotheses"][0]["evidence"][0]["source_ref"] == follow_up_ref
        assert len(provider.invocations) == 2
        assert provider.invocations[1].payload["prior_run_id"] == first_run_id
        assert provider.invocations[1].payload["conversation_turns"] == tuple(turns)

        replay = await client.get(
            f"/families/{FAMILY_ID}/experience/multimodal/runs/{follow_up_run_id}/replay"
        )
        assert replay.status_code == 200
        assert replay.json()["draft_payload"] == follow_up_payload

    await session.close()
    await engine.dispose()
    _restart_postgres_if_requested(migrated_database_url)

    restarted_engine = create_async_engine(migrated_database_url)
    restarted_factory = async_sessionmaker(restarted_engine, expire_on_commit=False)
    restarted_session: AsyncSession = restarted_factory()
    restarted_runtime = MultimodalDraftRuntime(
        scope=_scope(),
        application=_NeverCalledApplication(),  # type: ignore[arg-type]
        environment="test",
        run_ledger=CommittedExperienceRunLedger(
            SqlAlchemyExperienceRunLedger(restarted_session), restarted_session
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=_app(restarted_runtime)),
        base_url="http://aifamily.test",
    ) as client:
        replay = await client.get(
            f"/families/{FAMILY_ID}/experience/multimodal/runs/{follow_up_run_id}/replay"
        )
    assert replay.status_code == 200
    assert replay.json()["deletion_state"] == "active"
    assert replay.json()["draft_payload"] == follow_up_payload
    await restarted_session.close()
    await restarted_engine.dispose()


@pytest.mark.asyncio
async def test_openai_compatible_generation_changes_with_follow_up_and_persists(
    migrated_database_url: str,
) -> None:
    first_run_id = "run-s3-openai-compatible-concern"
    follow_up_run_id = "run-s3-openai-compatible-follow-up"
    first_turn = {
        "input_ref": f"input:{first_run_id}:concern",
        "kind": "CONCERN",
        "text": "每天一到写作业就开始争吵",
        "created_at": "2026-09-03T10:00:00+08:00",
    }
    follow_up_turn = {
        "input_ref": f"input:{follow_up_run_id}:follow-up",
        "kind": "FOLLOW_UP",
        "text": "如果我先听他说今天最难的是哪一题，他会愿意坐下来。",
        "created_at": "2026-09-03T10:06:00+08:00",
    }
    captured_requests: list[dict[str, object]] = []
    provider, gateway, profile, provider_client = _openai_compatible_provider_stack(
        captured_requests
    )
    engine = create_async_engine(migrated_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    context = AsyncSqlContextBroker(factory)
    await context.append(_observation())
    session = factory()
    registry = SqlAlchemyModelDraftRegistry(session)
    application = ContextBoundMultimodalExperienceService(
        context=context,
        routed=RoutedMultimodalExperienceService(
            router=MultimodalRouter((profile,)),
            generation=MultimodalExperienceService(gateway, registry=registry),
        ),
        registry=registry,
    )
    runtime = MultimodalDraftRuntime(
        scope=_scope(),
        application=application,
        environment="test",
        run_ledger=CommittedExperienceRunLedger(SqlAlchemyExperienceRunLedger(session), session),
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=_app(runtime)),
            base_url="http://aifamily.test",
        ) as client:
            first = await client.post(
                f"/families/{FAMILY_ID}/experience/multimodal/drafts",
                headers={"Idempotency-Key": f"create:{first_run_id}"},
                json=_request_body(
                    run_id=first_run_id,
                    conversation_turns=[first_turn],
                ),
            )
            follow_up = await client.post(
                f"/families/{FAMILY_ID}/experience/multimodal/drafts",
                headers={"Idempotency-Key": f"create:{follow_up_run_id}"},
                json=_request_body(
                    run_id=follow_up_run_id,
                    prior_run_id=first_run_id,
                    conversation_turns=[first_turn, follow_up_turn],
                ),
            )
            replay = await client.get(
                f"/families/{FAMILY_ID}/experience/multimodal/runs/{follow_up_run_id}/replay"
            )

        assert first.status_code == 200, first.text
        assert follow_up.status_code == 200, follow_up.text
        assert replay.status_code == 200, replay.text
        assert first_turn["text"] in first.json()["output"]["understanding"]["lived_experience"]
        assert (
            follow_up_turn["text"]
            in follow_up.json()["output"]["understanding"]["lived_experience"]
        )
        assert first.json()["output"] != follow_up.json()["output"]
        assert replay.json()["draft_payload"] == follow_up.json()["output"]
        assert follow_up.json()["provenance"]["provider_id"] == provider.provider_id
        assert follow_up.json()["provenance"]["model"] == "vision-generative-2026-09-03"
        assert len(captured_requests) == 2
        request_body = captured_requests[1]
        assert request_body["model"] == "vision-generative"
        assert request_body["response_format"] == {"type": "json_object"}
        system_prompt = request_body["messages"][0]["content"]
        assert "use_case=family-understanding-multimodal" in system_prompt
        assert "prompt_version=family-understanding.v1" in system_prompt
        user_content = request_body["messages"][1]["content"]
        assert user_content[1] == {
            "type": "image_url",
            "image_url": {"url": "media:authorized:family-scene"},
        }
    finally:
        await session.close()
        await engine.dispose()
        await provider_client.aclose()


@pytest.mark.asyncio
async def test_postgres_replay_supplies_the_actual_prior_draft_to_follow_up(
    migrated_database_url: str,
) -> None:
    scope = RunScope(
        tenant_id=TENANT_ID,
        family_id=FAMILY_ID,
        subject_ids=("guardian-s3-http", SUBJECT_ID),
    )
    first_run_id = "run-family-understanding-memory-1"
    prior_draft = _family_understanding_output(
        text_ref=f"input:{first_run_id}:concern",
        expression="孩子每天写作业前都很难开始",
    )
    engine = create_async_engine(migrated_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ledger = SessionPerCallExperienceRunLedger(factory)
    await ledger.create_draft(
        scope=scope,
        run_id=first_run_id,
        request_ref="request:family-understanding-memory-1",
        draft_payload=prior_draft,
        idempotency_key="create:family-understanding-memory-1",
    )
    await record_family_understanding_feedback(
        ledger,
        scope=scope,
        run_id=first_run_id,
        signal="helpful",
        feedback=FamilyUnderstandingFeedback(
            understood_rating=4,
            felt_judged=False,
            willing_to_continue=True,
            correction_needed=True,
            correction_ref="input:family-understanding-memory-1:correction",
        ),
        idempotency_key="feedback:family-understanding-memory-1",
    )
    await engine.dispose()

    _restart_postgres_if_requested(migrated_database_url)
    restarted_engine = create_async_engine(migrated_database_url)
    restarted_factory = async_sessionmaker(restarted_engine, expire_on_commit=False)
    replay = await SessionPerCallExperienceRunLedger(restarted_factory).replay(
        scope=scope,
        run_id=first_run_id,
    )

    source = KnowledgeSource(
        source_id="source:task-transition-review",
        title="Task transition review",
        license_ref="license:reviewed",
        owner="knowledge-team",
        scope="shared",
        verified=True,
    )
    claim = KnowledgeClaim(
        claim_id="knowledge:task-transition-reviewed-v1",
        text="作业开始困难可能与活动转换、选择感或任务难度有关。",
        source_id=source.source_id,
        provenance=Provenance(level="E6", source_ref=source.source_id),
        scope="family_growth",
        status="PUBLISHED",
        allowed_purposes=("family_problem_understanding",),
        metadata={
            "version": "1.0",
            "chunk_ref": "chunk:task-transition",
            "applicability": "家庭学习任务开始阶段",
            "limitations": ("不能凭一次表达判断孩子能力",),
            "keywords": ("作业", "开始", "切换", "选择"),
        },
    )
    preparer = FamilyProblemUnderstandingPreparer(
        FamilyUnderstandingKnowledgeRetriever(
            KnowledgeRegistry(sources=(source,), claims=(claim,)),
            minimum_relevance=0.02,
        )
    )
    prepared = preparer.prepare_follow_up_from_replay(
        scope=scope,
        prior_replay=replay,
        run_id="run-family-understanding-memory-2",
        data_class="SYNTHETIC",
        context_snapshot_ref="context:family-understanding-memory-2",
        conversation_turns=(
            FamilyConversationTurn(
                input_ref=f"input:{first_run_id}:concern",
                kind="CONCERN",
                text="孩子每天写作业前都很难开始",
                created_at="2026-09-03T09:00:00+08:00",
            ),
            FamilyConversationTurn(
                input_ref="input:family-understanding-memory-2:follow-up",
                kind="FOLLOW_UP",
                text="周末让孩子自己选择科目时通常能开始",
                created_at="2026-09-03T09:10:00+08:00",
            ),
        ),
        knowledge_scope="family_growth",
    )

    assert replay.draft_payload == prior_draft
    assert prepared.request.payload["prior_run_id"] == first_run_id
    assert prepared.request.payload["prior_draft"] == prior_draft
    assert prepared.eval_spec.prior_hypothesis_statements == (
        "作业启动前的转换可能比作业本身更困难。",
    )
    feedback_projection = project_family_understanding_feedback(replay)
    assert feedback_projection.felt_understood_mean == 0.75
    assert feedback_projection.latest_correction_ref == (
        "input:family-understanding-memory-1:correction"
    )
    assert (
        apply_parent_feedback_to_eval_spec(
            prepared.eval_spec, feedback_projection
        ).parent_felt_understood
        == 0.75
    )
    await restarted_engine.dispose()
