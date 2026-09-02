"""Real-PostgreSQL HTTP lifecycle for a governed multimodal draft."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from backend.intelligence.experience.run_store import ExperienceRunRow
from backend.intelligence.experience.sql_run_ledger import (
    CommittedExperienceRunLedger,
    ExperienceRunInteractionRow,
    SqlAlchemyExperienceRunLedger,
)
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provenance import (
    ModelDraftRow,
    SqlAlchemyModelDraftRegistry,
)
from backend.intelligence.model_gateway.provider_registry import (
    ProviderRecord,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.platform.persistence.session import DATABASE_URL_ENV_VAR
from tests.support.postgres import SKIP_REASON, postgres_test_url

REPO_ROOT = Path(__file__).resolve().parents[3]
TENANT_ID = "tenant-s3-http"
FAMILY_ID = "family-s3-http"
SUBJECT_ID = "child-s3-http"
RUN_ID = "run-s3-http-delete"
PURPOSE = "family-understanding-multimodal"
PROVIDER_ID = "synthetic-http-provider"


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
        async with admin.connect() as connection:
            await connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            await connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        await admin.dispose()


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


def _provider_stack() -> tuple[FakeProvider, ModelGateway, object]:
    provider = FakeProvider(
        {
            PURPOSE: {
                "headline": "我理解你们卡在晚间启动的反复拉扯",
                "next_step": "一起梳理触发点",
            }
        },
        provider_id=PROVIDER_ID,
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


def _request_body() -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "prompt_version": "family-understanding.v1",
        "schema_version": "family-understanding-output.v1",
        "payload": {"guardian_text": "每天一到写作业就开始争吵"},
        "output_schema": {
            "type": "object",
            "required": ["headline", "next_step"],
            "properties": {
                "headline": {"type": "string"},
                "next_step": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "modalities": ["TEXT", "IMAGE"],
        "estimated_input_tokens": 256,
        "input_refs": [f"evidence:{RUN_ID}"],
        "media_inputs": [
            {
                "media_type": "IMAGE",
                "uri": "https://assets.invalid/family-scene.png",
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
        draft_id = created.json()["draft_id"]
        assert len(provider.invocations) == 1
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
