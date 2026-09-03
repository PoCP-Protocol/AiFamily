"""Request-safe SQL Prompt/Schema readers for family experience generation.

The SQL Registry adapters are intentionally session-bound.  A long-lived
``MultimodalContractRegistryBinding`` therefore cannot retain one adapter
created from a startup session.  These readers open a fresh read session for
every resolve call and return immutable value objects after the session closes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.prompt_registry.contracts import PromptBundle
from backend.intelligence.prompt_registry.sql_registry import SqlAlchemyPromptRegistry
from backend.intelligence.schema_registry.contracts import SchemaDefinition
from backend.intelligence.schema_registry.sql_registry import SqlAlchemySchemaRegistry

from .contract_binding import MultimodalContractRegistryBinding
from .execution_materials import SessionPerCallExecutionMaterialResolver
from .standard_contracts import build_family_experience_contract_binding


@dataclass(frozen=True, slots=True)
class SessionPerCallPromptRegistryReader:
    """Resolve a published PromptBundle without retaining an AsyncSession."""

    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")

    async def resolve(
        self,
        use_case: str,
        agent_id: str,
        prompt_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> PromptBundle:
        async with self.session_factory() as session:
            return await SqlAlchemyPromptRegistry(session).resolve(
                use_case=use_case,
                agent_id=agent_id,
                prompt_ref=prompt_ref,
                version=version,
                at=at,
            )


@dataclass(frozen=True, slots=True)
class SessionPerCallSchemaRegistryReader:
    """Resolve a published SchemaDefinition without retaining an AsyncSession."""

    session_factory: async_sessionmaker[AsyncSession]

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")

    async def resolve(
        self,
        use_case: str,
        agent_id: str,
        schema_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> SchemaDefinition:
        async with self.session_factory() as session:
            return await SqlAlchemySchemaRegistry(session).resolve(
                use_case=use_case,
                agent_id=agent_id,
                schema_ref=schema_ref,
                version=version,
                at=at,
            )


def build_sql_family_experience_contract_binding(
    *, session_factory: async_sessionmaker[AsyncSession]
) -> MultimodalContractRegistryBinding:
    """Build the canonical binding from request-safe SQL Registry readers."""

    return build_family_experience_contract_binding(
        prompt_registry=SessionPerCallPromptRegistryReader(session_factory),
        schema_registry=SessionPerCallSchemaRegistryReader(session_factory),
        material_resolver=SessionPerCallExecutionMaterialResolver(session_factory),
    )


__all__ = [
    "SessionPerCallPromptRegistryReader",
    "SessionPerCallSchemaRegistryReader",
    "build_sql_family_experience_contract_binding",
]
