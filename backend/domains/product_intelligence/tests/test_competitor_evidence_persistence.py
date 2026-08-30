from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.intelligence.product_management.product_factory_inputs import (
    CompetitorEvidenceCard,
)

from ..infrastructure import sqlalchemy_models as models


async def test_sqlalchemy_repository_persists_scoped_competitor_draft(sqlalchemy_repo) -> None:
    card = CompetitorEvidenceCard(
        evidence_id="competitor-evidence:test-001",
        competitor_ref="competitor:example",
        claim="公开资料显示其提供家庭提醒功能",
        source_refs=("source:public:one",),
        evidence_status="UNKNOWN",
        demand_ref="demand:test-001",
        source_type="PUBLIC",
        evidence_refs=("evidence:public:one",),
        assumptions=("资料仍需交叉验证",),
        unknowns=("近期变更未知",),
        next_validation="复核原始页面并记录日期",
        expires_at=datetime.now(UTC) + timedelta(days=7),
        provenance_ref="research-draft:test-001",
    )

    await sqlalchemy_repo.save_competitor_evidence(
        card,
        tenant_scope="tenant-a",
        created_by="human:reviewer",
    )

    result = await sqlalchemy_repo._session.execute(
        select(models.CompetitorEvidenceRow).where(
            models.CompetitorEvidenceRow.id == card.evidence_id
        )
    )
    row = result.scalar_one()
    assert row.status == "DRAFT"
    assert row.tenant_scope == "tenant-a"
    assert row.created_by == "human:reviewer"
    assert row.evidence_status == "UNKNOWN"
    assert row.source_refs == ["source:public:one"]

    loaded = await sqlalchemy_repo.load_competitor_evidence(
        card.evidence_id, "tenant-a"
    )
    assert loaded.claim == card.claim
    assert loaded.status == "DRAFT"
