"""Durable immutable store for atomic family-experience release sets."""

from __future__ import annotations

from typing import Protocol, cast

from sqlalchemy import JSON, Boolean, CheckConstraint, Index, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.model_gateway.contracts import DataClass

from .release_set import FamilyExperienceReleaseSet, FamilyExperienceReleaseSetError


class FamilyExperienceReleaseSetBase(DeclarativeBase):
    """Metadata boundary owned by the release-set adapter."""


class FamilyExperienceReleaseSetRow(FamilyExperienceReleaseSetBase):
    __tablename__ = "ai_family_experience_release_sets"
    __table_args__ = (
        CheckConstraint(
            "draft_only = true AND may_mutate_business_state = false",
            name="ck_ai_family_experience_release_sets_draft_boundary",
        ),
        Index(
            "ix_ai_family_experience_release_sets_scope",
            "environment",
            "use_case",
            "data_class",
        ),
    )

    release_set_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    use_case: Mapped[str] = mapped_column(String(256), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    bundle_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    routing_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    route_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    rate_card_version: Mapped[str] = mapped_column(String(128), nullable=False)
    rate_card_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    budget_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    budget_policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(256), nullable=False)
    prompt_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    safety_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    safety_policy_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    asset_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    may_mutate_business_state: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FamilyExperienceReleaseSetReader(Protocol):
    durability_mode: str

    async def get(self, release_set_id: str) -> FamilyExperienceReleaseSet | None: ...


class FamilyExperienceReleaseSetStore(FamilyExperienceReleaseSetReader, Protocol):
    async def append(
        self, release_set: FamilyExperienceReleaseSet
    ) -> FamilyExperienceReleaseSet: ...


class InMemoryFamilyExperienceReleaseSetStore:
    durability_mode = "IN_MEMORY"

    def __init__(self) -> None:
        self._values: dict[str, FamilyExperienceReleaseSet] = {}

    async def get(self, release_set_id: str) -> FamilyExperienceReleaseSet | None:
        return self._values.get(release_set_id)

    async def append(
        self, release_set: FamilyExperienceReleaseSet
    ) -> FamilyExperienceReleaseSet:
        _validate(release_set)
        existing = self._values.get(release_set.release_set_id)
        if existing is not None and existing != release_set:
            raise FamilyExperienceReleaseSetError("RELEASE_SET_ID_CONFLICT")
        self._values[release_set.release_set_id] = existing or release_set
        return existing or release_set


class SqlAlchemyFamilyExperienceReleaseSetStore:
    durability_mode = "DURABLE"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, release_set_id: str) -> FamilyExperienceReleaseSet | None:
        row = await self._session.get(FamilyExperienceReleaseSetRow, release_set_id)
        return None if row is None else _stored(row)

    async def append(
        self, release_set: FamilyExperienceReleaseSet
    ) -> FamilyExperienceReleaseSet:
        _validate(release_set)
        existing = await self.get(release_set.release_set_id)
        if existing is not None:
            if existing != release_set:
                raise FamilyExperienceReleaseSetError("RELEASE_SET_ID_CONFLICT")
            return existing
        self._session.add(_row(release_set))
        await self._session.flush()
        return release_set


class SessionPerCallFamilyExperienceReleaseSetReader:
    durability_mode = "DURABLE"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, release_set_id: str) -> FamilyExperienceReleaseSet | None:
        async with self._session_factory() as session:
            return await SqlAlchemyFamilyExperienceReleaseSetStore(session).get(
                release_set_id
            )


def _validate(release_set: FamilyExperienceReleaseSet) -> None:
    if not isinstance(release_set, FamilyExperienceReleaseSet):
        raise FamilyExperienceReleaseSetError("RELEASE_SET_REQUIRED")


def _row(value: FamilyExperienceReleaseSet) -> FamilyExperienceReleaseSetRow:
    return FamilyExperienceReleaseSetRow(
        release_set_id=value.release_set_id,
        environment=value.environment,
        use_case=value.use_case,
        data_class=value.data_class,
        provider_ids=list(value.provider_ids),
        bundle_ids=list(value.bundle_ids),
        routing_policy_version=value.routing_policy_version,
        route_config_digest=value.route_config_digest,
        rate_card_version=value.rate_card_version,
        rate_card_digest=value.rate_card_digest,
        budget_policy_version=value.budget_policy_version,
        budget_policy_digest=value.budget_policy_digest,
        agent_id=value.agent_id,
        prompt_ref=value.prompt_ref,
        prompt_version=value.prompt_version,
        schema_ref=value.schema_ref,
        schema_version=value.schema_version,
        safety_policy_version=value.safety_policy_version,
        safety_policy_digest=value.safety_policy_digest,
        knowledge_refs=list(value.knowledge_refs),
        asset_digest=value.asset_digest,
        runtime_config_digest=value.runtime_config_digest,
        draft_only=value.draft_only,
        may_mutate_business_state=value.may_mutate_business_state,
    )


def _stored(row: FamilyExperienceReleaseSetRow) -> FamilyExperienceReleaseSet:
    return FamilyExperienceReleaseSet(
        release_set_id=row.release_set_id,
        environment=row.environment,
        use_case=row.use_case,
        data_class=cast(DataClass, row.data_class),
        provider_ids=tuple(row.provider_ids),
        bundle_ids=tuple(row.bundle_ids),
        routing_policy_version=row.routing_policy_version,
        route_config_digest=row.route_config_digest,
        rate_card_version=row.rate_card_version,
        rate_card_digest=row.rate_card_digest,
        budget_policy_version=row.budget_policy_version,
        budget_policy_digest=row.budget_policy_digest,
        agent_id=row.agent_id,
        prompt_ref=row.prompt_ref,
        prompt_version=row.prompt_version,
        schema_ref=row.schema_ref,
        schema_version=row.schema_version,
        safety_policy_version=row.safety_policy_version,
        safety_policy_digest=row.safety_policy_digest,
        knowledge_refs=tuple(row.knowledge_refs),
        asset_digest=row.asset_digest,
        runtime_config_digest=row.runtime_config_digest,
        draft_only=row.draft_only,
        may_mutate_business_state=row.may_mutate_business_state,
    )


__all__ = [
    "FamilyExperienceReleaseSetBase",
    "FamilyExperienceReleaseSetReader",
    "FamilyExperienceReleaseSetRow",
    "FamilyExperienceReleaseSetStore",
    "InMemoryFamilyExperienceReleaseSetStore",
    "SessionPerCallFamilyExperienceReleaseSetReader",
    "SqlAlchemyFamilyExperienceReleaseSetStore",
]
