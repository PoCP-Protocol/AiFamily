"""Durable SQL adapter for the governed Schema Registry."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .contracts import SchemaDefinition
from .registry import (
    SchemaAlreadyRegistered,
    SchemaBindingError,
    SchemaNotFound,
    SchemaRegistry,
)
from .validator import SchemaValidator


class SchemaPersistenceBase(DeclarativeBase):
    """Metadata boundary for schema registry records."""


class SchemaDefinitionRow(SchemaPersistenceBase):
    __tablename__ = "ai_schema_definitions"

    schema_ref: Mapped[str] = mapped_column(String(256), primary_key=True)
    version: Mapped[str] = mapped_column(String(128), primary_key=True)
    use_case: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(128), nullable=False)
    required_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_refs_non_empty: Mapped[bool] = mapped_column(Boolean, nullable=False)
    forbidden_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    allowed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    enum_constraints: Mapped[dict[str, list[str]]] = mapped_column(JSON, nullable=False)
    boundary_labels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    human_gate_rule: Mapped[str] = mapped_column(String(32), nullable=False)
    json_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(128))
    change_reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    evidence_refs_field: Mapped[str] = mapped_column(String(128), nullable=False)
    visibility: Mapped[str] = mapped_column(String(64), nullable=False)
    write_back_target: Mapped[str] = mapped_column(String(128), nullable=False)
    validator_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    text_equivalent_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SqlAlchemySchemaRegistry:
    """Session-bound durable Schema Registry with strict resolution."""

    _TRANSITIONS = SchemaRegistry._TRANSITIONS

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._validator = SchemaValidator()

    async def register(self, definition: SchemaDefinition) -> SchemaDefinition:
        if not isinstance(definition, SchemaDefinition):
            raise TypeError("definition must be a SchemaDefinition")
        existing = await self._session.get(
            SchemaDefinitionRow, (definition.schema_ref, definition.version)
        )
        if existing is not None:
            raise SchemaAlreadyRegistered(
                f"SCHEMA_ALREADY_REGISTERED:{definition.schema_ref}:{definition.version}"
            )
        self._session.add(_schema_row(definition))
        await self._session.flush()
        return definition

    async def get(self, schema_ref: str, version: str) -> SchemaDefinition | None:
        row = await self._session.get(SchemaDefinitionRow, (schema_ref, version))
        return None if row is None else _schema_from_row(row)

    async def transition(
        self,
        schema_ref: str,
        version: str,
        status: str,
        *,
        effective_at: datetime | None = None,
        retired_at: datetime | None = None,
        reviewer: str | None = None,
        change_reason: str = "",
    ) -> SchemaDefinition:
        current = await self.get(schema_ref, version)
        if current is None:
            raise SchemaNotFound(f"SCHEMA_NOT_FOUND:{schema_ref}:{version}")
        if status not in self._TRANSITIONS[current.status]:
            raise ValueError(f"INVALID_SCHEMA_TRANSITION:{current.status}->{status}")
        registry = SchemaRegistry(definitions=(current,))
        updated = registry.transition(
            schema_ref,
            version,
            status,  # type: ignore[arg-type]
            effective_at=effective_at,
            retired_at=retired_at,
            reviewer=reviewer,
            change_reason=change_reason,
        )
        row = await self._session.get(SchemaDefinitionRow, (schema_ref, version))
        if row is None:  # pragma: no cover - guarded by get above
            raise SchemaNotFound(f"SCHEMA_NOT_FOUND:{schema_ref}:{version}")
        row.superseded = True
        await self.register(updated)
        return updated

    async def find(
        self,
        use_case: str,
        agent_id: str,
        schema_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> SchemaDefinition | None:
        instant = _aware(at or datetime.now(UTC))
        statement = select(SchemaDefinitionRow).where(
            SchemaDefinitionRow.use_case == use_case,
            SchemaDefinitionRow.agent_id == agent_id,
            SchemaDefinitionRow.status == "PUBLISHED",
            SchemaDefinitionRow.superseded.is_(False),
            SchemaDefinitionRow.effective_at <= instant,
        )
        if schema_ref is not None:
            statement = statement.where(SchemaDefinitionRow.schema_ref == schema_ref)
        if version is not None:
            statement = statement.where(SchemaDefinitionRow.version == version)
        statement = statement.where(
            (SchemaDefinitionRow.retired_at.is_(None))
            | (SchemaDefinitionRow.retired_at > instant)
        )
        rows = (await self._session.scalars(statement)).all()
        if len(rows) > 1:
            raise SchemaBindingError(f"AMBIGUOUS_EFFECTIVE_SCHEMA:{use_case}:{agent_id}")
        return None if not rows else _schema_from_row(rows[0])

    async def resolve(
        self,
        use_case: str,
        agent_id: str,
        schema_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> SchemaDefinition:
        if not use_case or not agent_id:
            raise SchemaBindingError("SCHEMA_BINDING_REQUIRED:use_case_and_agent_id")
        definition = await self.find(use_case, agent_id, schema_ref, version, at)
        if definition is None:
            raise SchemaNotFound(
                f"SCHEMA_NOT_FOUND_OR_NOT_EFFECTIVE:{use_case}:{agent_id}:"
                f"{schema_ref or '*'}:{version or '*'}"
            )
        return definition

    resolve_schema = resolve

    async def validate(
        self,
        output: dict[str, object],
        use_case: str,
        agent_id: str,
        schema_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> dict[str, object]:
        definition = await self.resolve(use_case, agent_id, schema_ref, version, at)
        return self._validator.validate(definition, output)

    validate_output = validate


def _schema_row(definition: SchemaDefinition) -> SchemaDefinitionRow:
    return SchemaDefinitionRow(
        schema_ref=definition.schema_ref,
        version=definition.version,
        use_case=definition.use_case,
        agent_id=definition.agent_id,
        object_type=definition.object_type,
        required_fields=list(definition.required_fields),
        evidence_refs_non_empty=definition.evidence_refs_non_empty,
        forbidden_fields=sorted(definition.forbidden_fields),
        allowed_fields=sorted(definition.allowed_fields),
        enum_constraints={key: list(values) for key, values in definition.enum_constraints.items()},
        boundary_labels=list(definition.boundary_labels),
        human_gate_rule=definition.human_gate_rule,
        json_schema=_thaw(definition.json_schema),
        status=definition.status,
        effective_at=definition.effective_at,
        retired_at=definition.retired_at,
        author=definition.author,
        reviewer=definition.reviewer,
        change_reason=definition.change_reason,
        evidence_refs_field=definition.evidence_refs_field,
        visibility=definition.visibility,
        write_back_target=definition.write_back_target,
        validator_ref=definition.validator_ref,
        text_equivalent_required=definition.text_equivalent_required,
    )


def _schema_from_row(row: SchemaDefinitionRow) -> SchemaDefinition:
    return SchemaDefinition(
        schema_ref=row.schema_ref,
        version=row.version,
        use_case=row.use_case,
        agent_id=row.agent_id,
        object_type=row.object_type,
        required_fields=tuple(row.required_fields),
        evidence_refs_non_empty=row.evidence_refs_non_empty,
        forbidden_fields=frozenset(row.forbidden_fields),
        allowed_fields=frozenset(row.allowed_fields),
        enum_constraints={key: tuple(values) for key, values in row.enum_constraints.items()},
        boundary_labels=tuple(row.boundary_labels),
        human_gate_rule=row.human_gate_rule,  # type: ignore[arg-type]
        json_schema=row.json_schema,
        status=row.status,  # type: ignore[arg-type]
        effective_at=None if row.effective_at is None else _aware(row.effective_at),
        retired_at=None if row.retired_at is None else _aware(row.retired_at),
        author=row.author,
        reviewer=row.reviewer,
        change_reason=row.change_reason,
        evidence_refs_field=row.evidence_refs_field,
        visibility=row.visibility,
        write_back_target=row.write_back_target,
        validator_ref=row.validator_ref,
        text_equivalent_required=row.text_equivalent_required,
    )


def _thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_thaw(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): _thaw(item) for key, item in value.items()}
    return value


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "SchemaDefinitionRow",
    "SchemaPersistenceBase",
    "SqlAlchemySchemaRegistry",
]
