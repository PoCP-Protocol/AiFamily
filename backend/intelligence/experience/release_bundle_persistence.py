"""Durable metadata store for immutable family-experience release bundles."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, cast

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.model_gateway.contracts import DataClass

from .release_bundle import (
    FamilyExperienceReleaseBundle,
    FamilyExperienceReleaseBundleError,
)


class FamilyExperienceReleaseBundleBase(DeclarativeBase):
    """Metadata boundary owned by the family-experience bundle adapter."""


class FamilyExperienceReleaseBundleRow(FamilyExperienceReleaseBundleBase):
    __tablename__ = "ai_family_experience_release_bundles"
    __table_args__ = (
        CheckConstraint(
            "data_class IN ('SYNTHETIC', 'OPERATIONAL_TEXT', "
            "'FAMILY_PRIVATE_TEXT', 'MINOR_PERSONAL_DATA')",
            name="ck_ai_family_experience_bundles_data_class",
        ),
        CheckConstraint(
            "human_gate_rule = 'REVIEW_REQUIRED'",
            name="ck_ai_family_experience_bundles_human_gate",
        ),
        CheckConstraint(
            "draft_only = true AND may_mutate_business_state = false",
            name="ck_ai_family_experience_bundles_draft_boundary",
        ),
        Index(
            "uq_ai_family_experience_bundles_candidate_environment",
            "candidate_id",
            "environment",
            unique=True,
        ),
        Index("ix_ai_family_experience_bundles_control", "control_id"),
    )

    bundle_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(256), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    use_case: Mapped[str] = mapped_column(String(256), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(256), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    safety_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    routing_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    rate_card_version: Mapped[str] = mapped_column(String(128), nullable=False)
    budget_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    knowledge_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    report_ref: Mapped[str] = mapped_column(Text, nullable=False)
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_signature_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_signature_algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(256), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    human_gate_rule: Mapped[str] = mapped_column(String(32), nullable=False)
    draft_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    may_mutate_business_state: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FamilyExperienceReleaseBundleReader(Protocol):
    async def get(
        self, bundle_id: str
    ) -> FamilyExperienceReleaseBundle | None: ...

    async def get_for_candidate(
        self, candidate_id: str, environment: str
    ) -> FamilyExperienceReleaseBundle | None: ...

    async def list_for_use_case(
        self, environment: str, use_case: str
    ) -> tuple[FamilyExperienceReleaseBundle, ...]: ...


class FamilyExperienceReleaseBundleStore(FamilyExperienceReleaseBundleReader, Protocol):
    async def append(
        self, bundle: FamilyExperienceReleaseBundle
    ) -> FamilyExperienceReleaseBundle: ...


class InMemoryFamilyExperienceReleaseBundleStore:
    def __init__(self) -> None:
        self._by_id: dict[str, FamilyExperienceReleaseBundle] = {}
        self._by_candidate: dict[tuple[str, str], FamilyExperienceReleaseBundle] = {}

    async def append(
        self, bundle: FamilyExperienceReleaseBundle
    ) -> FamilyExperienceReleaseBundle:
        _validate_bundle(bundle)
        existing = self._by_id.get(bundle.bundle_id)
        candidate_existing = self._by_candidate.get(
            (bundle.candidate_id, bundle.environment)
        )
        if existing is not None and existing != bundle:
            raise FamilyExperienceReleaseBundleError("RELEASE_BUNDLE_ID_CONFLICT")
        if candidate_existing is not None and candidate_existing != bundle:
            raise FamilyExperienceReleaseBundleError("RELEASE_CANDIDATE_BUNDLE_CONFLICT")
        stored = existing or candidate_existing or bundle
        self._by_id[bundle.bundle_id] = stored
        self._by_candidate[(bundle.candidate_id, bundle.environment)] = stored
        return stored

    async def get(self, bundle_id: str) -> FamilyExperienceReleaseBundle | None:
        return self._by_id.get(bundle_id)

    async def get_for_candidate(
        self, candidate_id: str, environment: str
    ) -> FamilyExperienceReleaseBundle | None:
        return self._by_candidate.get((candidate_id, environment))

    async def list_for_use_case(
        self, environment: str, use_case: str
    ) -> tuple[FamilyExperienceReleaseBundle, ...]:
        return tuple(
            bundle
            for bundle in self._by_id.values()
            if bundle.environment == environment and bundle.use_case == use_case
        )


class SqlAlchemyFamilyExperienceReleaseBundleStore:
    """SQL metadata-only bundle store; caller owns commit and rollback."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self, bundle: FamilyExperienceReleaseBundle
    ) -> FamilyExperienceReleaseBundle:
        _validate_bundle(bundle)
        existing = await self.get(bundle.bundle_id)
        candidate_existing = await self.get_for_candidate(
            bundle.candidate_id, bundle.environment
        )
        if existing is not None and existing != bundle:
            raise FamilyExperienceReleaseBundleError("RELEASE_BUNDLE_ID_CONFLICT")
        if candidate_existing is not None and candidate_existing != bundle:
            raise FamilyExperienceReleaseBundleError("RELEASE_CANDIDATE_BUNDLE_CONFLICT")
        if existing is not None or candidate_existing is not None:
            return existing or cast(FamilyExperienceReleaseBundle, candidate_existing)
        self._session.add(_row(bundle))
        await self._session.flush()
        return bundle

    async def get(self, bundle_id: str) -> FamilyExperienceReleaseBundle | None:
        row = await self._session.scalar(
            select(FamilyExperienceReleaseBundleRow).where(
                FamilyExperienceReleaseBundleRow.bundle_id == bundle_id
            )
        )
        return None if row is None else _stored(row)

    async def get_for_candidate(
        self, candidate_id: str, environment: str
    ) -> FamilyExperienceReleaseBundle | None:
        row = await self._session.scalar(
            select(FamilyExperienceReleaseBundleRow).where(
                FamilyExperienceReleaseBundleRow.candidate_id == candidate_id,
                FamilyExperienceReleaseBundleRow.environment == environment,
            )
        )
        return None if row is None else _stored(row)

    async def list_for_use_case(
        self, environment: str, use_case: str
    ) -> tuple[FamilyExperienceReleaseBundle, ...]:
        rows = await self._session.scalars(
            select(FamilyExperienceReleaseBundleRow).where(
                FamilyExperienceReleaseBundleRow.environment == environment,
                FamilyExperienceReleaseBundleRow.use_case == use_case,
            )
        )
        return tuple(_stored(row) for row in rows)


class SessionPerCallFamilyExperienceReleaseBundleReader:
    """Read immutable bundles without retaining a startup AsyncSession."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def get(self, bundle_id: str) -> FamilyExperienceReleaseBundle | None:
        async with self._session_factory() as session:
            return await SqlAlchemyFamilyExperienceReleaseBundleStore(session).get(bundle_id)

    async def get_for_candidate(
        self, candidate_id: str, environment: str
    ) -> FamilyExperienceReleaseBundle | None:
        async with self._session_factory() as session:
            return await SqlAlchemyFamilyExperienceReleaseBundleStore(
                session
            ).get_for_candidate(candidate_id, environment)

    async def list_for_use_case(
        self, environment: str, use_case: str
    ) -> tuple[FamilyExperienceReleaseBundle, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyFamilyExperienceReleaseBundleStore(
                session
            ).list_for_use_case(environment, use_case)

def _validate_bundle(bundle: FamilyExperienceReleaseBundle) -> None:
    if not isinstance(bundle, FamilyExperienceReleaseBundle):
        raise FamilyExperienceReleaseBundleError("RELEASE_BUNDLE_REQUIRED")


def _row(bundle: FamilyExperienceReleaseBundle) -> FamilyExperienceReleaseBundleRow:
    return FamilyExperienceReleaseBundleRow(
        bundle_id=bundle.bundle_id,
        candidate_id=bundle.candidate_id,
        environment=bundle.environment,
        use_case=bundle.use_case,
        agent_id=bundle.agent_id,
        provider_id=bundle.provider_id,
        model=bundle.model,
        model_version=bundle.model_version,
        prompt_ref=bundle.prompt_ref,
        prompt_version=bundle.prompt_version,
        schema_ref=bundle.schema_ref,
        schema_version=bundle.schema_version,
        safety_policy_version=bundle.safety_policy_version,
        routing_policy_version=bundle.routing_policy_version,
        rate_card_version=bundle.rate_card_version,
        budget_policy_version=bundle.budget_policy_version,
        knowledge_refs=list(bundle.knowledge_refs),
        data_class=bundle.data_class,
        report_ref=bundle.report_ref,
        decision_id=bundle.decision_id,
        control_id=bundle.control_id,
        approval_signature_ref=bundle.approval_signature_ref,
        approval_signature_algorithm=bundle.approval_signature_algorithm,
        approved_by=bundle.approved_by,
        approved_at=bundle.approved_at,
        asset_digest=bundle.asset_digest,
        human_gate_rule=bundle.human_gate_rule,
        draft_only=bundle.draft_only,
        may_mutate_business_state=bundle.may_mutate_business_state,
    )


def _stored(row: FamilyExperienceReleaseBundleRow) -> FamilyExperienceReleaseBundle:
    approved_at = row.approved_at
    if approved_at.tzinfo is None or approved_at.utcoffset() is None:
        approved_at = approved_at.replace(tzinfo=UTC)
    return FamilyExperienceReleaseBundle(
        bundle_id=row.bundle_id,
        candidate_id=row.candidate_id,
        environment=row.environment,
        use_case=row.use_case,
        agent_id=row.agent_id,
        provider_id=row.provider_id,
        model=row.model,
        model_version=row.model_version,
        prompt_ref=row.prompt_ref,
        prompt_version=row.prompt_version,
        schema_ref=row.schema_ref,
        schema_version=row.schema_version,
        safety_policy_version=row.safety_policy_version,
        routing_policy_version=row.routing_policy_version,
        rate_card_version=row.rate_card_version,
        budget_policy_version=row.budget_policy_version,
        knowledge_refs=tuple(row.knowledge_refs),
        data_class=cast(DataClass, row.data_class),
        report_ref=row.report_ref,
        decision_id=row.decision_id,
        control_id=row.control_id,
        approval_signature_ref=row.approval_signature_ref,
        approval_signature_algorithm=row.approval_signature_algorithm,
        approved_by=row.approved_by,
        approved_at=approved_at,
        asset_digest=row.asset_digest,
        human_gate_rule=row.human_gate_rule,
        draft_only=row.draft_only,
        may_mutate_business_state=row.may_mutate_business_state,
    )


__all__ = [
    "FamilyExperienceReleaseBundleBase",
    "FamilyExperienceReleaseBundleReader",
    "FamilyExperienceReleaseBundleRow",
    "FamilyExperienceReleaseBundleStore",
    "InMemoryFamilyExperienceReleaseBundleStore",
    "SessionPerCallFamilyExperienceReleaseBundleReader",
    "SqlAlchemyFamilyExperienceReleaseBundleStore",
]
