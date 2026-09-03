"""End-to-end registry wiring for the context-bound multimodal draft path."""

from __future__ import annotations

from dataclasses import replace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    DataClass,
)
from backend.intelligence.context_engine.store import ContextBroker
from backend.intelligence.experience.multimodal_application import (
    RoutedMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_context_application import (
    ContextBoundMultimodalCommand,
    ContextBoundMultimodalExperienceService,
)
from backend.intelligence.experience.multimodal_generation import MultimodalExperienceService
from backend.intelligence.experience.multimodal_routing import (
    QWEN_MULTIMODAL_CANDIDATE,
    MultimodalRouter,
    MultimodalRouteRequest,
)
from backend.intelligence.model_gateway.provenance import (
    ModelDraftNotFound,
    ModelDraftRegistryBase,
    ModelDraftRegistryError,
    ModelDraftRow,
    SqlAlchemyModelDraftRegistry,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.model_gateway.test_fail_closed import build

TENANT = "tenant-multimodal-registry"
FAMILY = "family-multimodal-registry"
CHILD = "child-multimodal-registry"
PURPOSE = "family-image-summary"
CORRELATION = "correlation-multimodal-registry"


@pytest_asyncio.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(ModelDraftRegistryBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _scope(*, subjects: tuple[str, ...] = (CHILD,)) -> ContextScope:
    return ContextScope(
        tenant_id=TENANT,
        region_id="CN",
        family_id=FAMILY,
        subject_ids=subjects,
        purpose=PURPOSE,
        consent_version="consent-multimodal-registry.v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref="delete:multimodal-registry",
        correlation_id=CORRELATION,
        causation_id="causation-multimodal-registry",
    )


def _command(
    scope: ContextScope,
    *,
    run_id: str = "run-multimodal-registry-001",
    model_draft_subject_id: str | None = None,
) -> ContextBoundMultimodalCommand:
    return ContextBoundMultimodalCommand(
        run_id=run_id,
        route_request=MultimodalRouteRequest(
            use_case=PURPOSE,
            data_class="SYNTHETIC",
            modalities=("TEXT", "IMAGE"),
            environment="test",
            estimated_input_tokens=128,
        ),
        scope=scope,
        prompt_version="prompt.multimodal-registry.v1",
        schema_version="schema.multimodal-registry.v1",
        payload={"media_ref": "fixture:image-multimodal-registry"},
        output_schema={
            "type": "object",
            "required": ["headline"],
            "properties": {"headline": {"type": "string"}},
        },
        model_draft_subject_id=model_draft_subject_id,
    )


def _service(
    session: AsyncSession,
    provider: FakeProvider,
    *,
    context: ContextBroker | None = None,
) -> ContextBoundMultimodalExperienceService:
    profile = replace(
        QWEN_MULTIMODAL_CANDIDATE,
        provider_id="fake-deterministic",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        approved_data_classes=frozenset({"SYNTHETIC"}),
        sub_delegates=False,
        security_assessment_ref="synthetic-test-only",
        processing_agreement_ref="synthetic-test-only",
        deletion_on_termination_committed=True,
    )
    routed = RoutedMultimodalExperienceService(
        router=MultimodalRouter((profile,)),
        generation=MultimodalExperienceService(
            build(provider),
            registry=SqlAlchemyModelDraftRegistry(session),
        ),
    )
    registry = SqlAlchemyModelDraftRegistry(session)
    return ContextBoundMultimodalExperienceService(
        context=context or ContextBroker(),
        routed=routed,
        registry=registry,
    )


@pytest.mark.asyncio
async def test_context_generation_saves_a_draft_that_a_new_session_can_resolve(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scope = _scope()
    provider = FakeProvider({PURPOSE: {"headline": "可供家庭确认的理解"}})
    async with session_factory() as session:
        result = await _service(session, provider).generate_draft(
            _command(scope, model_draft_subject_id=CHILD)
        )
        assert result.draft_id == "draft:run-multimodal-registry-001"
        assert result.provenance_ref == "model-draft:run-multimodal-registry-001"
        assert result.routed.experience.draft.may_mutate_business_state is False
        await session.commit()

    async with session_factory() as new_session:
        loaded = await SqlAlchemyModelDraftRegistry(new_session).resolve(
            result.provenance_ref,
            tenant_id=TENANT,
            family_id=FAMILY,
            subject_person_id=CHILD,
            purpose=PURPOSE,
            correlation_id=CORRELATION,
        )
        assert loaded == result.routed.experience.draft

        row = await new_session.scalar(
            select(ModelDraftRow).where(
                ModelDraftRow.tenant_id == TENANT,
                ModelDraftRow.draft_id == result.draft_id,
            )
        )
        assert row is not None
        assert row.status == "DRAFT"
        assert row.may_mutate_business_state is False

        with pytest.raises(ModelDraftNotFound):
            await SqlAlchemyModelDraftRegistry(new_session).resolve(
                result.provenance_ref,
                tenant_id="foreign-tenant",
                family_id=FAMILY,
                subject_person_id=CHILD,
                purpose=PURPOSE,
                correlation_id=CORRELATION,
            )


@pytest.mark.asyncio
async def test_retry_reuses_the_persisted_draft_and_original_context_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scope = _scope()
    context = ContextBroker()
    first_provider = FakeProvider({PURPOSE: {"headline": "第一次生成"}})
    command = _command(scope, model_draft_subject_id=CHILD, run_id="run-retry")

    async with session_factory() as session:
        first = await _service(session, first_provider, context=context).generate_draft(command)
        await session.commit()

    replay_provider = FakeProvider({PURPOSE: {"headline": "不应再次生成"}})
    async with session_factory() as new_session:
        replay = await _service(new_session, replay_provider, context=context).generate_draft(
            command
        )

    assert replay.draft_id == first.draft_id
    assert replay.provenance_ref == first.provenance_ref
    assert replay.routed.experience.draft == first.routed.experience.draft
    assert replay.snapshot.snapshot_ref == first.snapshot.snapshot_ref
    assert replay_provider.invocations == []


@pytest.mark.asyncio
async def test_changed_generation_contract_is_rejected_before_a_provider_retry(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scope = _scope()
    context = ContextBroker()
    command = _command(scope, model_draft_subject_id=CHILD, run_id="run-retry-mismatch")

    async with session_factory() as session:
        await _service(
            session,
            FakeProvider({PURPOSE: {"headline": "原始草案"}}),
            context=context,
        ).generate_draft(command)
        await session.commit()

    replay_provider = FakeProvider({PURPOSE: {"headline": "不应调用"}})
    changed = replace(command, prompt_version="prompt.changed.v2")
    async with session_factory() as new_session:
        with pytest.raises(ModelDraftRegistryError, match="REPLAY_MISMATCH"):
            await _service(new_session, replay_provider, context=context).generate_draft(changed)

    assert replay_provider.invocations == []


@pytest.mark.asyncio
async def test_retry_without_the_original_context_snapshot_fails_closed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scope = _scope()
    original_context = ContextBroker()
    command = _command(scope, model_draft_subject_id=CHILD, run_id="run-retry-no-context")

    async with session_factory() as session:
        await _service(
            session,
            FakeProvider({PURPOSE: {"headline": "需要原始上下文"}}),
            context=original_context,
        ).generate_draft(command)
        await session.commit()

    replay_provider = FakeProvider({PURPOSE: {"headline": "不应调用"}})
    async with session_factory() as new_session:
        with pytest.raises(ContextContractError, match="CONTEXT_SNAPSHOT_NOT_FOUND"):
            await _service(new_session, replay_provider, context=ContextBroker()).generate_draft(
                command
            )

    assert replay_provider.invocations == []


@pytest.mark.asyncio
async def test_registry_integration_does_not_auto_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    scope = _scope()
    provider = FakeProvider({PURPOSE: {"headline": "未提交草案"}})
    async with session_factory() as session:
        result = await _service(session, provider).generate_draft(
            _command(scope, model_draft_subject_id=CHILD, run_id="run-uncommitted")
        )
        await session.rollback()

    async with session_factory() as new_session:
        with pytest.raises(ModelDraftNotFound):
            await SqlAlchemyModelDraftRegistry(new_session).resolve(
                result.provenance_ref,
                tenant_id=TENANT,
                family_id=FAMILY,
                subject_person_id=CHILD,
                purpose=PURPOSE,
                correlation_id=CORRELATION,
            )


@pytest.mark.asyncio
async def test_multi_subject_context_requires_an_explicit_action_subject(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    provider = FakeProvider({PURPOSE: {"headline": "不会调用"}})
    scope = _scope(subjects=("guardian-multimodal-registry", CHILD))
    async with session_factory() as session:
        with pytest.raises(ValueError, match="model_draft_scope"):
            await _service(session, provider).generate_draft(_command(scope))

    assert provider.invocations == []


@pytest.mark.asyncio
async def test_registry_rejects_fact_shaped_output_before_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    provider = FakeProvider({PURPOSE: {"headline": "不应成为总分", "family_score": 99}})
    scope = _scope()
    async with session_factory() as session:
        service = _service(session, provider)
        command = _command(scope, model_draft_subject_id=CHILD, run_id="run-redline")
        command = replace(
            command,
            output_schema={
                "type": "object",
                "required": ["headline", "family_score"],
                "properties": {
                    "headline": {"type": "string"},
                    "family_score": {"type": "integer"},
                },
            },
        )
        with pytest.raises(ModelDraftRegistryError, match="cannot become a business fact"):
            await service.generate_draft(command)
        await session.rollback()

    async with session_factory() as new_session:
        assert (
            await new_session.scalar(
                select(ModelDraftRow).where(ModelDraftRow.draft_id == "draft:run-redline")
            )
            is None
        )
