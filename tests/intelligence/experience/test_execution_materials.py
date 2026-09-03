from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.experience.execution_materials import (
    ExecutionMaterialBase,
    ExecutionMaterialError,
    InMemoryExecutionMaterialRegistry,
    KnowledgeExecutionMaterial,
    KnowledgeExecutionMaterialRow,
    SessionPerCallExecutionMaterialResolver,
    SqlAlchemyExecutionMaterialRegistry,
    SystemPolicyMaterial,
)

NOW = datetime(2026, 9, 1, 12, 30, tzinfo=UTC)


def _policy() -> SystemPolicyMaterial:
    return SystemPolicyMaterial.build(
        policy_ref="policy:family:v1",
        use_case="family_assistant_conversation",
        agent_id="parent_advisor",
        content="Only create a draft; never mutate family facts.",
        locale="zh-CN",
        status="PUBLISHED",
        reviewer="operator:policy",
        effective_at=NOW - timedelta(days=1),
    )


def _knowledge(marker: str) -> KnowledgeExecutionMaterial:
    return KnowledgeExecutionMaterial.build(
        knowledge_ref=f"knowledge:family:{marker}",
        use_case="family_assistant_conversation",
        content=f"Reviewed shared guidance {marker}.",
        source_ref=f"source:{marker}",
        license_ref="license:internal-reviewed",
        evidence_level="E3",
        status="PUBLISHED",
        reviewer="operator:knowledge",
        effective_at=NOW - timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_material_resolver_returns_exact_reviewed_order_and_digest() -> None:
    policy = _policy()
    first = _knowledge("a")
    second = _knowledge("b")
    registry = InMemoryExecutionMaterialRegistry(
        policies=(policy,),
        knowledge=(second, first),
    )

    resolved = await registry.resolve(
        system_policy_ref=policy.policy_ref,
        knowledge_refs=(first.knowledge_ref, second.knowledge_ref),
        use_case=policy.use_case,
        agent_id=policy.agent_id,
        at=NOW,
    )

    assert resolved.system_policy.content == policy.content
    assert resolved.knowledge == (first, second)
    assert len(resolved.material_digest) == 64


def test_private_or_unreviewed_material_cannot_become_executable() -> None:
    with pytest.raises(ExecutionMaterialError, match="FAMILY_PRIVATE"):
        replace(_knowledge("a"), scope="FAMILY_PRIVATE")  # type: ignore[arg-type]
    with pytest.raises(ExecutionMaterialError, match="REVIEW_REQUIRED"):
        SystemPolicyMaterial.build(
            policy_ref="policy:unreviewed",
            use_case="family_assistant_conversation",
            agent_id="parent_advisor",
            content="unreviewed",
            locale="zh-CN",
            status="PUBLISHED",
        )


@pytest.mark.asyncio
async def test_sql_resolver_detects_content_changed_without_digest() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ExecutionMaterialBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            registry = SqlAlchemyExecutionMaterialRegistry(session)
            await registry.register_policy(_policy())
            await registry.register_knowledge(_knowledge("a"))
        async with factory() as session, session.begin():
            row = await session.get(
                KnowledgeExecutionMaterialRow,
                "knowledge:family:a",
            )
            assert row is not None
            row.content = "tampered content"
        resolver = SessionPerCallExecutionMaterialResolver(factory)
        with pytest.raises(ExecutionMaterialError, match="DIGEST_MISMATCH"):
            await resolver.resolve(
                system_policy_ref="policy:family:v1",
                knowledge_refs=("knowledge:family:a",),
                use_case="family_assistant_conversation",
                agent_id="parent_advisor",
                at=NOW,
            )
    finally:
        await engine.dispose()
