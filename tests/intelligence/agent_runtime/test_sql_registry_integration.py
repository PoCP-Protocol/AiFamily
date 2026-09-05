from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.agent_runtime.runtime import AgentRuntime
from backend.intelligence.prompt_registry import PromptPersistenceBase, SqlAlchemyPromptRegistry
from backend.intelligence.schema_registry import SchemaPersistenceBase, SqlAlchemySchemaRegistry
from tests.intelligence.agent_runtime.test_runtime import (
    NOW,
    FakeGenerationPort,
    authorization,
    definition,
    registries,
    task,
)


@pytest.mark.asyncio
async def test_agent_runtime_resolves_durable_prompt_and_schema_registries() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(PromptPersistenceBase.metadata.create_all)
        await connection.run_sync(SchemaPersistenceBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        memory_prompts, memory_schemas = registries()
        prompt = memory_prompts.get("assessment-prompt", "assessment-v1")
        schema = memory_schemas.get("growth-schema", "growth-v1")
        assert prompt is not None and schema is not None
        async with factory() as session, session.begin():
            prompts = SqlAlchemyPromptRegistry(session)
            schemas = SqlAlchemySchemaRegistry(session)
            await prompts.register(prompt)
            await schemas.register(schema)
            port = FakeGenerationPort()
            runtime = AgentRuntime(
                port,
                [definition()],
                clock=lambda: NOW + timedelta(minutes=1),
                prompt_registry=prompts,
                schema_registry=schemas,
                require_registries=True,
            )
            result = await runtime.execute(
                task(output_schema={"type": "string"}, prompt_ref="assessment-prompt"),
                authorization(),
            )
        assert result.draft.status == "DRAFT"
        assert port.calls[0].output_schema["properties"]["explanation"]["type"] == "string"
    finally:
        await engine.dispose()
