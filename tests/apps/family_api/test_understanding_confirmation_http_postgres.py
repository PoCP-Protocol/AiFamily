from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.apps.family_api.sqlalchemy_understanding_snapshots import (
    SqlAlchemyUnderstandingDraftSnapshots,
)
from backend.apps.family_api.understanding_review import ConfirmUnderstandingApplication
from backend.domains.assessment.application.reviewed_understanding_signals import (
    RecordReviewedUnderstandingService,
)
from backend.domains.assessment.infrastructure.sqlalchemy_reviewed_understanding_signals import (
    SqlAlchemyReviewedUnderstandingSignals,
)
from backend.intelligence.family_understanding.api import (
    AuthorizedReviewContext,
    ViewedUnderstandingView,
    create_family_understanding_router,
)
from backend.intelligence.family_understanding.snapshot import UnderstandingDraftSnapshot
from backend.platform.authorization.policy import PolicyEngine, PolicyRule
from backend.platform.authorization.review_receipts import (
    REVIEW_ACTION,
    REVIEW_RESOURCE_TYPE,
    ReviewReceiptIssuer,
)
from backend.platform.identity.context import ActorType
from tests.support.postgres import SKIP_REASON, postgres_test_url

TENANT = "a1000000-0000-4000-8000-000000000001"
FAMILY = "a2000000-0000-4000-8000-000000000001"
OTHER_FAMILY = "a2000000-0000-4000-8000-000000000002"
GUARDIAN = "a3000000-0000-4000-8000-000000000001"
NOW = datetime.now(UTC)


class Contexts:
    async def resolve(self, **_):
        raise AssertionError("generation route is not part of this contract")

    async def resolve_for_review(self, *, family_id: str):
        if family_id != FAMILY:
            return None
        return AuthorizedReviewContext(
            tenant_id=TENANT,
            family_id=FAMILY,
            actor_id=GUARDIAN,
            subject_person_id=GUARDIAN,
            consent_ref="consent-effective-1",
        )


class Views:
    calls = 0

    async def record_view(self, command):
        self.calls += 1
        return ViewedUnderstandingView(
            view_event_ref=command.view_event_ref,
            status="VIEWED",
            scope_ref=f"family://{TENANT}/{FAMILY}/problem-understanding",
            artifact_ref=command.artifact_ref,
            artifact_version=command.artifact_version,
            provenance_ref=command.provenance_ref,
            viewed_at=NOW,
        )


def snapshot() -> UnderstandingDraftSnapshot:
    return UnderstandingDraftSnapshot(
        tenant_id=TENANT,
        family_id=FAMILY,
        understanding_run_ref="http-understanding-run-v1",
        artifact_ref="http-artifact-v1",
        artifact_version=1,
        prior_artifact_ref=None,
        provenance_ref="air-provenance:v1:sha256:http-v1",
        subject_person_id=GUARDIAN,
        desired_change="希望晚饭后的沟通少一点争吵。",
        need_type="PARENT_CHILD_COMMUNICATION",
        required_capability_keys=("FAMILY_COMMUNICATION",),
        evidence_refs=("guardian-input-http-1",),
        source_refs=("guardian-input-http-1",),
        knowledge_refs=("knowledge-reviewed-http-1",),
        provider_id="approved-provider",
        model="understanding-model",
        model_version="2026-09",
        prompt_version="problem-understanding-v1",
        schema_version="family_problem_understanding.v1",
        context_snapshot_ref="context-http-v1",
        expires_at=NOW + timedelta(days=1),
    )


async def _delete_fixture(connection) -> None:
    await connection.execute(
        text("DELETE FROM assessment_reviewed_understanding_signals WHERE tenant_id=:tenant"),
        {"tenant": UUID(TENANT)},
    )
    await connection.execute(
        text("DELETE FROM family_understanding_draft_snapshots WHERE tenant_id=:tenant"),
        {"tenant": UUID(TENANT)},
    )
    await connection.execute(
        text("DELETE FROM persons WHERE person_id=:guardian"), {"guardian": UUID(GUARDIAN)}
    )
    await connection.execute(
        text("DELETE FROM families WHERE family_id IN (:family,:other_family)"),
        {"family": UUID(FAMILY), "other_family": UUID(OTHER_FAMILY)},
    )
    await connection.execute(
        text("DELETE FROM tenants WHERE tenant_id=:tenant"), {"tenant": UUID(TENANT)}
    )


@pytest.mark.asyncio
async def test_real_http_confirmation_is_exact_idempotent_and_restart_readable() -> None:
    database_url = postgres_test_url()
    if database_url is None:
        pytest.skip(SKIP_REASON)
    engine = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await _delete_fixture(connection)
            await connection.execute(
                text(
                    "INSERT INTO tenants(tenant_id,tenant_ref,display_name,tenant_type) "
                    "VALUES (:tenant,'HTTP-CONFIRM','HTTP confirm','INTERNAL_SANDBOX')"
                ),
                {"tenant": UUID(TENANT)},
            )
            await connection.execute(
                text(
                    "INSERT INTO families(family_id,display_name) VALUES "
                    "(:family,'HTTP family'),(:other_family,'Other family')"
                ),
                {"family": UUID(FAMILY), "other_family": UUID(OTHER_FAMILY)},
            )
            await connection.execute(
                text(
                    "INSERT INTO persons(person_id,family_id,person_type,parent_role,display_name) "
                    "VALUES (:guardian,:family,'PARENT','GUARDIAN','测试家长')"
                ),
                {"guardian": UUID(GUARDIAN), "family": UUID(FAMILY)},
            )

        async with sessions() as session:
            snapshots = SqlAlchemyUnderstandingDraftSnapshots(session)
            signals = SqlAlchemyReviewedUnderstandingSignals(session)
            await snapshots.save(snapshot())
            await session.commit()

            policy = PolicyEngine()
            policy.register(
                PolicyRule(
                    action=REVIEW_ACTION,
                    resource_type=REVIEW_RESOURCE_TYPE,
                    allowed_actor_types=frozenset({ActorType.HUMAN}),
                    human_only=True,
                )
            )
            confirmations = ConfirmUnderstandingApplication(
                snapshots,
                ReviewReceiptIssuer(policy, signing_key=b"http-confirmation-key-32-bytes!!"),
                RecordReviewedUnderstandingService(signals),
                confirmation_replays=signals,
                clock=lambda: NOW,
            )
            views = Views()
            app = FastAPI()
            app.include_router(
                create_family_understanding_router(
                    object(),  # generation is deliberately outside this HTTP contract
                    Contexts(),
                    view_application=views,
                    confirmation_application=confirmations,
                    review_contexts=Contexts(),
                )
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                body = {
                    "artifact_version": 1,
                    "provenance_ref": snapshot().provenance_ref,
                    "view_event_ref": "view-http-v1",
                }
                viewed = await client.post(
                    f"/v1/families/{FAMILY}/understanding-drafts/{snapshot().artifact_ref}/views",
                    json=body,
                )
                before = await session.scalar(
                    text(
                        "SELECT count(*) FROM assessment_reviewed_understanding_signals "
                        "WHERE tenant_id=:tenant"
                    ),
                    {"tenant": UUID(TENANT)},
                )
                confirmed = await client.post(
                    f"/v1/families/{FAMILY}/understanding-drafts/"
                    f"{snapshot().artifact_ref}/confirmations",
                    json=body,
                )
                replay = await client.post(
                    f"/v1/families/{FAMILY}/understanding-drafts/"
                    f"{snapshot().artifact_ref}/confirmations",
                    json=body,
                )
                stale = await client.post(
                    f"/v1/families/{FAMILY}/understanding-drafts/"
                    f"{snapshot().artifact_ref}/confirmations",
                    json={**body, "artifact_version": 2},
                )
                cross_family = await client.post(
                    f"/v1/families/{OTHER_FAMILY}/understanding-drafts/"
                    f"{snapshot().artifact_ref}/confirmations",
                    json=body,
                )
            await session.commit()

            assert viewed.status_code == 200
            assert viewed.json()["status"] == "VIEWED"
            assert "receipt_ref" not in viewed.json()
            assert before == 0
            assert confirmed.status_code == replay.status_code == 200
            assert confirmed.json()["receipt_ref"] == replay.json()["receipt_ref"]
            assert stale.status_code == 409
            assert cross_family.status_code == 403

        await engine.dispose()
        restarted = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
        try:
            restarted_sessions = async_sessionmaker(restarted, expire_on_commit=False)
            async with restarted_sessions() as session:
                loaded = await SqlAlchemyReviewedUnderstandingSignals(session).load_viewed_signal(
                    tenant_id=TENANT,
                    family_id=FAMILY,
                    assessment_session_id=None,
                    understanding_run_ref=snapshot().understanding_run_ref,
                    human_gate_receipt_ref=confirmed.json()["receipt_ref"],
                )
                assert loaded is not None
                assert loaded.reviewed_draft_ref == snapshot().artifact_ref
                assert loaded.understanding_run_ref == snapshot().understanding_run_ref

                await session.execute(
                    text(
                        "UPDATE family_understanding_draft_snapshots SET status='REVOKED',"
                        "revoked_at=now(),revocation_ref='consent-withdrawn' "
                        "WHERE tenant_id=:tenant"
                    ),
                    {"tenant": UUID(TENANT)},
                )
                await session.commit()
                revoked_confirmations = ConfirmUnderstandingApplication(
                    SqlAlchemyUnderstandingDraftSnapshots(session),
                    ReviewReceiptIssuer(policy, signing_key=b"http-confirmation-key-32-bytes!!"),
                    RecordReviewedUnderstandingService(
                        SqlAlchemyReviewedUnderstandingSignals(session)
                    ),
                    confirmation_replays=SqlAlchemyReviewedUnderstandingSignals(session),
                    clock=lambda: NOW,
                )
                revoked_app = FastAPI()
                revoked_app.include_router(
                    create_family_understanding_router(
                        object(),
                        Contexts(),
                        confirmation_application=revoked_confirmations,
                        review_contexts=Contexts(),
                    )
                )
                async with AsyncClient(
                    transport=ASGITransport(app=revoked_app), base_url="http://test"
                ) as client:
                    revoked = await client.post(
                        f"/v1/families/{FAMILY}/understanding-drafts/"
                        f"{snapshot().artifact_ref}/confirmations",
                        json={
                            "artifact_version": 1,
                            "provenance_ref": snapshot().provenance_ref,
                            "view_event_ref": "view-after-revocation",
                        },
                    )
                assert revoked.status_code == 409
        finally:
            await restarted.dispose()
    finally:
        await engine.dispose()
        cleanup = create_async_engine(database_url, connect_args={"statement_cache_size": 0})
        try:
            async with cleanup.begin() as connection:
                await _delete_fixture(connection)
        finally:
            await cleanup.dispose()
