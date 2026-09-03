"""Durable SQL adapter for the governed Prompt Registry.

The in-memory registry remains useful for deterministic unit tests.  This
adapter preserves the same immutable version and effective-window semantics
after restart; callers own the transaction and this module never executes a
prompt or reaches a model provider.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .contracts import PromptBundle
from .registry import (
    PromptAlreadyRegistered,
    PromptBindingError,
    PromptNotFound,
    PromptRegistry,
)


class PromptPersistenceBase(DeclarativeBase):
    """Metadata boundary for prompt registry records."""


class PromptBundleRow(PromptPersistenceBase):
    __tablename__ = "ai_prompt_bundles"

    prompt_ref: Mapped[str] = mapped_column(String(256), primary_key=True)
    version: Mapped[str] = mapped_column(String(128), primary_key=True)
    use_case: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    system_policy_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    knowledge_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    input_contract_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    output_schema_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    safety_policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    locale: Mapped[str] = mapped_column(String(32), nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SqlAlchemyPromptRegistry:
    """Session-bound durable Prompt Registry with fail-closed resolution."""

    _TRANSITIONS = PromptRegistry._TRANSITIONS

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(self, bundle: PromptBundle) -> PromptBundle:
        if not isinstance(bundle, PromptBundle):
            raise TypeError("bundle must be a PromptBundle")
        existing = await self._session.get(
            PromptBundleRow, (bundle.prompt_ref, bundle.version)
        )
        if existing is not None:
            raise PromptAlreadyRegistered(
                f"PROMPT_ALREADY_REGISTERED:{bundle.prompt_ref}:{bundle.version}"
            )
        self._session.add(_prompt_row(bundle))
        await self._session.flush()
        return bundle

    async def get(self, prompt_ref: str, version: str) -> PromptBundle | None:
        row = await self._session.get(PromptBundleRow, (prompt_ref, version))
        return None if row is None else _prompt_from_row(row)

    async def transition(
        self,
        prompt_ref: str,
        version: str,
        status: str,
        *,
        effective_at: datetime | None = None,
        retired_at: datetime | None = None,
        reviewer: str | None = None,
        change_reason: str = "",
    ) -> PromptBundle:
        current = await self.get(prompt_ref, version)
        if current is None:
            raise PromptNotFound(f"PROMPT_NOT_FOUND:{prompt_ref}:{version}")
        if status not in self._TRANSITIONS[current.status]:
            raise ValueError(f"INVALID_PROMPT_TRANSITION:{current.status}->{status}")
        # Reuse the in-memory lifecycle rules to keep both adapters identical.
        registry = PromptRegistry(bundles=(current,))
        updated = registry.transition(
            prompt_ref,
            version,
            status,  # type: ignore[arg-type]
            effective_at=effective_at,
            retired_at=retired_at,
            reviewer=reviewer,
            change_reason=change_reason,
        )
        row = await self._session.get(PromptBundleRow, (prompt_ref, version))
        if row is None:  # pragma: no cover - guarded by get above
            raise PromptNotFound(f"PROMPT_NOT_FOUND:{prompt_ref}:{version}")
        row.superseded = True
        await self.register(updated)
        return updated

    async def find(
        self,
        use_case: str,
        agent_id: str,
        prompt_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> PromptBundle | None:
        instant = _aware(at or datetime.now(UTC))
        statement = select(PromptBundleRow).where(
            PromptBundleRow.use_case == use_case,
            PromptBundleRow.agent_id == agent_id,
            PromptBundleRow.status == "PUBLISHED",
            PromptBundleRow.superseded.is_(False),
            PromptBundleRow.effective_at <= instant,
        )
        if prompt_ref is not None:
            statement = statement.where(PromptBundleRow.prompt_ref == prompt_ref)
        if version is not None:
            statement = statement.where(PromptBundleRow.version == version)
        statement = statement.where(
            (PromptBundleRow.retired_at.is_(None))
            | (PromptBundleRow.retired_at > instant)
        )
        rows = (await self._session.scalars(statement)).all()
        if len(rows) > 1:
            raise PromptBindingError(
                f"AMBIGUOUS_EFFECTIVE_PROMPT:{use_case}:{agent_id}:{prompt_ref or '*'}"
            )
        return None if not rows else _prompt_from_row(rows[0])

    async def resolve(
        self,
        use_case: str,
        agent_id: str,
        prompt_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> PromptBundle:
        if not use_case or not agent_id:
            raise PromptBindingError("PROMPT_BINDING_REQUIRED:use_case_and_agent_id")
        bundle = await self.find(use_case, agent_id, prompt_ref, version, at)
        if bundle is None:
            raise PromptNotFound(
                f"PROMPT_NOT_FOUND_OR_NOT_EFFECTIVE:{use_case}:{agent_id}:"
                f"{prompt_ref or '*'}:{version or '*'}"
            )
        return bundle

    resolve_prompt = resolve


def _prompt_row(bundle: PromptBundle) -> PromptBundleRow:
    return PromptBundleRow(
        prompt_ref=bundle.prompt_ref,
        version=bundle.version,
        use_case=bundle.use_case,
        agent_id=bundle.agent_id,
        template=bundle.template,
        system_policy_ref=bundle.system_policy_ref,
        knowledge_refs=list(bundle.knowledge_refs),
        input_contract_ref=bundle.input_contract_ref,
        output_schema_ref=bundle.output_schema_ref,
        safety_policy_version=bundle.safety_policy_version,
        locale=bundle.locale,
        author=bundle.author,
        reviewer=bundle.reviewer,
        status=bundle.status,
        effective_at=bundle.effective_at,
        retired_at=bundle.retired_at,
        change_reason=bundle.change_reason,
    )


def _prompt_from_row(row: PromptBundleRow) -> PromptBundle:
    return PromptBundle(
        prompt_ref=row.prompt_ref,
        version=row.version,
        use_case=row.use_case,
        agent_id=row.agent_id,
        template=row.template,
        system_policy_ref=row.system_policy_ref,
        knowledge_refs=tuple(row.knowledge_refs),
        input_contract_ref=row.input_contract_ref,
        output_schema_ref=row.output_schema_ref,
        safety_policy_version=row.safety_policy_version,
        locale=row.locale,
        author=row.author,
        reviewer=row.reviewer,
        status=row.status,  # type: ignore[arg-type]
        effective_at=None if row.effective_at is None else _aware(row.effective_at),
        retired_at=None if row.retired_at is None else _aware(row.retired_at),
        change_reason=row.change_reason,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = ["PromptBundleRow", "PromptPersistenceBase", "SqlAlchemyPromptRegistry"]
