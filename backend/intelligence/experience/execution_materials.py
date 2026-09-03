"""Reviewed, content-addressed policy and knowledge supplied to model execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MaterialStatus = Literal["DRAFT", "REVIEW", "PUBLISHED", "RETIRED"]


class ExecutionMaterialError(ValueError):
    """A policy or knowledge material is not eligible for model execution."""


@dataclass(frozen=True, slots=True)
class SystemPolicyMaterial:
    policy_ref: str
    use_case: str
    agent_id: str
    content: str
    locale: str
    status: MaterialStatus
    reviewer: str | None
    effective_at: datetime | None
    retired_at: datetime | None
    content_digest: str

    def __post_init__(self) -> None:
        required = (
            self.policy_ref,
            self.use_case,
            self.agent_id,
            self.content,
            self.locale,
            self.content_digest,
        )
        if not all(value.strip() for value in required):
            raise ExecutionMaterialError("SYSTEM_POLICY_MATERIAL_FIELDS_REQUIRED")
        _validate_lifecycle(
            self.status,
            self.reviewer,
            self.effective_at,
            self.retired_at,
        )
        if self.content_digest != _system_policy_digest(self):
            raise ExecutionMaterialError("SYSTEM_POLICY_MATERIAL_DIGEST_MISMATCH")

    @classmethod
    def build(
        cls,
        *,
        policy_ref: str,
        use_case: str,
        agent_id: str,
        content: str,
        locale: str,
        status: MaterialStatus,
        reviewer: str | None = None,
        effective_at: datetime | None = None,
        retired_at: datetime | None = None,
    ) -> SystemPolicyMaterial:
        digest = _canonical_digest(
            {
                "policy_ref": policy_ref,
                "use_case": use_case,
                "agent_id": agent_id,
                "content": content,
                "locale": locale,
            }
        )
        return cls(
            policy_ref=policy_ref,
            use_case=use_case,
            agent_id=agent_id,
            content=content,
            locale=locale,
            status=status,
            reviewer=reviewer,
            effective_at=effective_at,
            retired_at=retired_at,
            content_digest=digest,
        )

    def is_effective(self, at: datetime) -> bool:
        return _is_effective(self.status, self.effective_at, self.retired_at, at)


@dataclass(frozen=True, slots=True)
class KnowledgeExecutionMaterial:
    knowledge_ref: str
    use_case: str
    content: str
    source_ref: str
    license_ref: str
    evidence_level: str
    scope: Literal["SHARED"]
    status: MaterialStatus
    reviewer: str | None
    effective_at: datetime | None
    retired_at: datetime | None
    content_digest: str

    def __post_init__(self) -> None:
        required = (
            self.knowledge_ref,
            self.use_case,
            self.content,
            self.source_ref,
            self.license_ref,
            self.evidence_level,
            self.content_digest,
        )
        if not all(value.strip() for value in required):
            raise ExecutionMaterialError("KNOWLEDGE_MATERIAL_FIELDS_REQUIRED")
        if self.scope != "SHARED":
            raise ExecutionMaterialError("FAMILY_PRIVATE_KNOWLEDGE_NOT_ALLOWED")
        _validate_lifecycle(
            self.status,
            self.reviewer,
            self.effective_at,
            self.retired_at,
        )
        if self.content_digest != _knowledge_digest(self):
            raise ExecutionMaterialError("KNOWLEDGE_MATERIAL_DIGEST_MISMATCH")

    @classmethod
    def build(
        cls,
        *,
        knowledge_ref: str,
        use_case: str,
        content: str,
        source_ref: str,
        license_ref: str,
        evidence_level: str,
        status: MaterialStatus,
        reviewer: str | None = None,
        effective_at: datetime | None = None,
        retired_at: datetime | None = None,
    ) -> KnowledgeExecutionMaterial:
        digest = _canonical_digest(
            {
                "knowledge_ref": knowledge_ref,
                "use_case": use_case,
                "content": content,
                "source_ref": source_ref,
                "license_ref": license_ref,
                "evidence_level": evidence_level,
                "scope": "SHARED",
            }
        )
        return cls(
            knowledge_ref=knowledge_ref,
            use_case=use_case,
            content=content,
            source_ref=source_ref,
            license_ref=license_ref,
            evidence_level=evidence_level,
            scope="SHARED",
            status=status,
            reviewer=reviewer,
            effective_at=effective_at,
            retired_at=retired_at,
            content_digest=digest,
        )

    def is_effective(self, at: datetime) -> bool:
        return _is_effective(self.status, self.effective_at, self.retired_at, at)


@dataclass(frozen=True, slots=True)
class ResolvedExecutionMaterials:
    system_policy: SystemPolicyMaterial
    knowledge: tuple[KnowledgeExecutionMaterial, ...]
    material_digest: str


class ExecutionMaterialResolver(Protocol):
    durability_mode: str

    async def resolve(
        self,
        *,
        system_policy_ref: str,
        knowledge_refs: tuple[str, ...],
        use_case: str,
        agent_id: str,
        at: datetime | None = None,
    ) -> ResolvedExecutionMaterials: ...


class InMemoryExecutionMaterialRegistry:
    durability_mode = "IN_MEMORY"

    def __init__(
        self,
        *,
        policies: tuple[SystemPolicyMaterial, ...] = (),
        knowledge: tuple[KnowledgeExecutionMaterial, ...] = (),
    ) -> None:
        self._policies = {item.policy_ref: item for item in policies}
        self._knowledge = {item.knowledge_ref: item for item in knowledge}
        if len(self._policies) != len(policies) or len(self._knowledge) != len(knowledge):
            raise ExecutionMaterialError("EXECUTION_MATERIAL_IDENTITY_CONFLICT")

    async def get_policy(self, policy_ref: str) -> SystemPolicyMaterial | None:
        return self._policies.get(policy_ref)

    async def get_knowledge(
        self, knowledge_ref: str
    ) -> KnowledgeExecutionMaterial | None:
        return self._knowledge.get(knowledge_ref)

    async def register_policy(self, material: SystemPolicyMaterial) -> None:
        if material.policy_ref in self._policies:
            raise ExecutionMaterialError("SYSTEM_POLICY_ALREADY_REGISTERED")
        self._policies[material.policy_ref] = material

    async def register_knowledge(self, material: KnowledgeExecutionMaterial) -> None:
        if material.knowledge_ref in self._knowledge:
            raise ExecutionMaterialError("KNOWLEDGE_MATERIAL_ALREADY_REGISTERED")
        self._knowledge[material.knowledge_ref] = material

    async def resolve(self, **values) -> ResolvedExecutionMaterials:
        return _resolve_materials(self._policies, self._knowledge, **values)


class ExecutionMaterialBase(DeclarativeBase):
    """Metadata for immutable reviewed execution materials."""


class SystemPolicyMaterialRow(ExecutionMaterialBase):
    __tablename__ = "ai_system_policy_materials"

    policy_ref: Mapped[str] = mapped_column(String(256), primary_key=True)
    use_case: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(256))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class KnowledgeExecutionMaterialRow(ExecutionMaterialBase):
    __tablename__ = "ai_knowledge_execution_materials"

    knowledge_ref: Mapped[str] = mapped_column(String(256), primary_key=True)
    use_case: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    license_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(256))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class SqlAlchemyExecutionMaterialRegistry:
    durability_mode = "DURABLE"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_policy(self, policy_ref: str) -> SystemPolicyMaterial | None:
        row = await self._session.get(SystemPolicyMaterialRow, policy_ref)
        return _stored_policy(row) if row is not None else None

    async def get_knowledge(
        self, knowledge_ref: str
    ) -> KnowledgeExecutionMaterial | None:
        row = await self._session.get(KnowledgeExecutionMaterialRow, knowledge_ref)
        return _stored_knowledge(row) if row is not None else None

    async def register_policy(self, material: SystemPolicyMaterial) -> None:
        if await self._session.get(SystemPolicyMaterialRow, material.policy_ref):
            raise ExecutionMaterialError("SYSTEM_POLICY_ALREADY_REGISTERED")
        self._session.add(_policy_row(material))
        await self._session.flush()

    async def register_knowledge(self, material: KnowledgeExecutionMaterial) -> None:
        if await self._session.get(KnowledgeExecutionMaterialRow, material.knowledge_ref):
            raise ExecutionMaterialError("KNOWLEDGE_MATERIAL_ALREADY_REGISTERED")
        self._session.add(_knowledge_row(material))
        await self._session.flush()

    async def resolve(
        self,
        *,
        system_policy_ref: str,
        knowledge_refs: tuple[str, ...],
        use_case: str,
        agent_id: str,
        at: datetime | None = None,
    ) -> ResolvedExecutionMaterials:
        policy_row = await self._session.get(SystemPolicyMaterialRow, system_policy_ref)
        if policy_row is None:
            raise ExecutionMaterialError("SYSTEM_POLICY_NOT_FOUND")
        rows = tuple(
            (
                await self._session.scalars(
                    select(KnowledgeExecutionMaterialRow).where(
                        KnowledgeExecutionMaterialRow.knowledge_ref.in_(knowledge_refs)
                    )
                )
            ).all()
        )
        return _resolve_materials(
            {system_policy_ref: _stored_policy(policy_row)},
            {row.knowledge_ref: _stored_knowledge(row) for row in rows},
            system_policy_ref=system_policy_ref,
            knowledge_refs=knowledge_refs,
            use_case=use_case,
            agent_id=agent_id,
            at=at,
        )


class SessionPerCallExecutionMaterialResolver:
    durability_mode = "DURABLE"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(self, **values) -> ResolvedExecutionMaterials:
        async with self._session_factory() as session:
            return await SqlAlchemyExecutionMaterialRegistry(session).resolve(**values)


def _resolve_materials(
    policies: dict[str, SystemPolicyMaterial],
    knowledge: dict[str, KnowledgeExecutionMaterial],
    *,
    system_policy_ref: str,
    knowledge_refs: tuple[str, ...],
    use_case: str,
    agent_id: str,
    at: datetime | None = None,
) -> ResolvedExecutionMaterials:
    instant = at or datetime.now(UTC)
    policy = policies.get(system_policy_ref)
    if policy is None:
        raise ExecutionMaterialError("SYSTEM_POLICY_NOT_FOUND")
    if (
        policy.use_case != use_case
        or policy.agent_id != agent_id
        or not policy.is_effective(instant)
    ):
        raise ExecutionMaterialError("SYSTEM_POLICY_NOT_EFFECTIVE")
    resolved = []
    for ref in knowledge_refs:
        material = knowledge.get(ref)
        if material is None:
            raise ExecutionMaterialError("KNOWLEDGE_MATERIAL_NOT_FOUND")
        if material.use_case != use_case or not material.is_effective(instant):
            raise ExecutionMaterialError("KNOWLEDGE_MATERIAL_NOT_EFFECTIVE")
        resolved.append(material)
    digest = _aggregate_digest(policy, tuple(resolved))
    return ResolvedExecutionMaterials(policy, tuple(resolved), digest)


def _validate_lifecycle(status, reviewer, effective_at, retired_at) -> None:
    if status not in {"DRAFT", "REVIEW", "PUBLISHED", "RETIRED"}:
        raise ExecutionMaterialError("EXECUTION_MATERIAL_STATUS_INVALID")
    if status == "PUBLISHED" and (not reviewer or effective_at is None):
        raise ExecutionMaterialError("PUBLISHED_EXECUTION_MATERIAL_REVIEW_REQUIRED")
    for value in (effective_at, retired_at):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ExecutionMaterialError("EXECUTION_MATERIAL_TIME_MUST_BE_AWARE")
    if retired_at is not None and effective_at is not None and retired_at <= effective_at:
        raise ExecutionMaterialError("EXECUTION_MATERIAL_WINDOW_INVALID")


def _is_effective(status, effective_at, retired_at, at) -> bool:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ExecutionMaterialError("EXECUTION_MATERIAL_TIME_MUST_BE_AWARE")
    return (
        status == "PUBLISHED"
        and effective_at is not None
        and effective_at <= at
        and (retired_at is None or at < retired_at)
    )


def _canonical_digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _system_policy_digest(value: SystemPolicyMaterial) -> str:
    return _canonical_digest(
        {
            "policy_ref": value.policy_ref,
            "use_case": value.use_case,
            "agent_id": value.agent_id,
            "content": value.content,
            "locale": value.locale,
        }
    )


def _knowledge_digest(value: KnowledgeExecutionMaterial) -> str:
    return _canonical_digest(
        {
            "knowledge_ref": value.knowledge_ref,
            "use_case": value.use_case,
            "content": value.content,
            "source_ref": value.source_ref,
            "license_ref": value.license_ref,
            "evidence_level": value.evidence_level,
            "scope": value.scope,
        }
    )


def _aggregate_digest(
    policy: SystemPolicyMaterial,
    knowledge: tuple[KnowledgeExecutionMaterial, ...],
) -> str:
    return _canonical_digest(
        {
            "system_policy_digest": policy.content_digest,
            "knowledge_digests": [item.content_digest for item in knowledge],
        }
    )


def execution_material_digest(
    policy: SystemPolicyMaterial,
    knowledge: tuple[KnowledgeExecutionMaterial, ...],
) -> str:
    """Return the ordered content digest embedded in a PromptExecutionPlan."""

    return _aggregate_digest(policy, knowledge)


def _policy_row(value: SystemPolicyMaterial) -> SystemPolicyMaterialRow:
    return SystemPolicyMaterialRow(
        **{name: getattr(value, name) for name in value.__dataclass_fields__}
    )


def _knowledge_row(value: KnowledgeExecutionMaterial) -> KnowledgeExecutionMaterialRow:
    return KnowledgeExecutionMaterialRow(
        **{name: getattr(value, name) for name in value.__dataclass_fields__}
    )


def _stored_policy(row: SystemPolicyMaterialRow) -> SystemPolicyMaterial:
    return SystemPolicyMaterial(
        policy_ref=row.policy_ref,
        use_case=row.use_case,
        agent_id=row.agent_id,
        content=row.content,
        locale=row.locale,
        status=row.status,  # type: ignore[arg-type]
        reviewer=row.reviewer,
        effective_at=_db_time(row.effective_at),
        retired_at=_db_time(row.retired_at),
        content_digest=row.content_digest,
    )


def _stored_knowledge(row: KnowledgeExecutionMaterialRow) -> KnowledgeExecutionMaterial:
    return KnowledgeExecutionMaterial(
        knowledge_ref=row.knowledge_ref,
        use_case=row.use_case,
        content=row.content,
        source_ref=row.source_ref,
        license_ref=row.license_ref,
        evidence_level=row.evidence_level,
        scope=row.scope,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        reviewer=row.reviewer,
        effective_at=_db_time(row.effective_at),
        retired_at=_db_time(row.retired_at),
        content_digest=row.content_digest,
    )


def _db_time(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


__all__ = [
    "ExecutionMaterialBase",
    "ExecutionMaterialError",
    "ExecutionMaterialResolver",
    "execution_material_digest",
    "InMemoryExecutionMaterialRegistry",
    "KnowledgeExecutionMaterial",
    "KnowledgeExecutionMaterialRow",
    "ResolvedExecutionMaterials",
    "SessionPerCallExecutionMaterialResolver",
    "SqlAlchemyExecutionMaterialRegistry",
    "SystemPolicyMaterial",
    "SystemPolicyMaterialRow",
]
