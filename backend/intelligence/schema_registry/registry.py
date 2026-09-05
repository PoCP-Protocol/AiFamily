"""Fail-closed, provider-neutral Schema Registry."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from .contracts import SchemaDefinition, SchemaStatus
from .validator import SchemaValidationError, SchemaValidator


class SchemaRegistryError(RuntimeError):
    """Base error for schema lookup and lifecycle failures."""


class SchemaNotFound(SchemaRegistryError):
    """Raised when no effective, correctly bound schema exists."""


class SchemaAlreadyRegistered(SchemaRegistryError):
    """Raised when a schema version identity is registered twice."""


class SchemaBindingError(SchemaRegistryError):
    """Raised when use-case/agent binding is missing or ambiguous."""


class SchemaRegistry:
    _TRANSITIONS: dict[SchemaStatus, frozenset[SchemaStatus]] = {
        "DRAFT": frozenset({"REVIEW", "RETIRED"}),
        "REVIEW": frozenset({"PUBLISHED", "RETIRED"}),
        "PUBLISHED": frozenset({"RETIRED"}),
        "RETIRED": frozenset(),
    }

    def __init__(self, *, definitions: tuple[SchemaDefinition, ...] = ()) -> None:
        self._definitions: dict[tuple[str, str], SchemaDefinition] = {}
        self._superseded: set[tuple[str, str]] = set()
        self._validator = SchemaValidator()
        for definition in definitions:
            self.register(definition)

    def register(self, definition: SchemaDefinition) -> SchemaDefinition:
        key = (definition.schema_ref, definition.version)
        if key in self._definitions:
            raise SchemaAlreadyRegistered(
                f"SCHEMA_ALREADY_REGISTERED:{definition.schema_ref}:{definition.version}"
            )
        self._definitions[key] = definition
        return definition

    def get(self, schema_ref: str, version: str) -> SchemaDefinition | None:
        return self._definitions.get((schema_ref, version))

    def transition(
        self,
        schema_ref: str,
        version: str,
        status: SchemaStatus,
        *,
        effective_at: datetime | None = None,
        retired_at: datetime | None = None,
        reviewer: str | None = None,
        change_reason: str = "",
    ) -> SchemaDefinition:
        current = self.get(schema_ref, version)
        if current is None:
            raise SchemaNotFound(f"SCHEMA_NOT_FOUND:{schema_ref}:{version}")
        if status not in self._TRANSITIONS[current.status]:
            raise SchemaRegistryError(f"INVALID_SCHEMA_TRANSITION:{current.status}->{status}")
        if status == "PUBLISHED" and effective_at is None:
            effective_at = datetime.now(UTC)
        new_version = f"{version}.{status.lower()}"
        while (schema_ref, new_version) in self._definitions:
            new_version = f"{new_version}.1"
        updated = replace(
            current,
            version=new_version,
            status=status,
            effective_at=effective_at if effective_at is not None else current.effective_at,
            retired_at=retired_at,
            reviewer=reviewer if reviewer is not None else current.reviewer,
            change_reason=change_reason,
        )
        self._superseded.add((schema_ref, version))
        return self.register(updated)

    def find(
        self,
        use_case: str,
        agent_id: str,
        schema_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> SchemaDefinition | None:
        instant = at if at is not None else datetime.now(UTC)
        candidates = [
            definition
            for definition in self._definitions.values()
            if definition.use_case == use_case
            and definition.agent_id == agent_id
            and (schema_ref is None or definition.schema_ref == schema_ref)
            and (version is None or definition.version == version)
            and (definition.schema_ref, definition.version) not in self._superseded
            and definition.effective_at_time(instant)
        ]
        if len(candidates) > 1:
            raise SchemaBindingError(f"AMBIGUOUS_EFFECTIVE_SCHEMA:{use_case}:{agent_id}")
        return candidates[0] if candidates else None

    def resolve(
        self,
        use_case: str,
        agent_id: str,
        schema_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> SchemaDefinition:
        if not use_case or not agent_id:
            raise SchemaBindingError("SCHEMA_BINDING_REQUIRED:use_case_and_agent_id")
        definition = self.find(
            use_case=use_case,
            agent_id=agent_id,
            schema_ref=schema_ref,
            version=version,
            at=at,
        )
        if definition is None:
            raise SchemaNotFound(
                f"SCHEMA_NOT_FOUND_OR_NOT_EFFECTIVE:{use_case}:{agent_id}:"
                f"{schema_ref or '*'}:{version or '*'}"
            )
        return definition

    resolve_schema = resolve

    def validate(
        self,
        output: dict[str, object],
        use_case: str,
        agent_id: str,
        schema_ref: str | None = None,
        version: str | None = None,
        at: datetime | None = None,
    ) -> dict[str, object]:
        definition = self.resolve(
            use_case=use_case,
            agent_id=agent_id,
            schema_ref=schema_ref,
            version=version,
            at=at,
        )
        return self._validator.validate(definition, output)

    validate_output = validate


__all__ = ["SchemaValidationError"]
