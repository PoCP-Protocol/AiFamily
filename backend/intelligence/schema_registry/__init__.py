"""Provider-neutral Schema Registry public API."""

from .contracts import HumanGateRule, SchemaDefinition, SchemaStatus, SchemaVersion
from .registry import (
    SchemaAlreadyRegistered,
    SchemaBindingError,
    SchemaNotFound,
    SchemaRegistry,
    SchemaRegistryError,
)
from .sql_registry import SchemaDefinitionRow, SchemaPersistenceBase, SqlAlchemySchemaRegistry
from .validator import SchemaValidationError, SchemaValidator

__all__ = [
    "HumanGateRule",
    "SchemaAlreadyRegistered",
    "SchemaBindingError",
    "SchemaDefinition",
    "SchemaNotFound",
    "SchemaRegistry",
    "SchemaRegistryError",
    "SchemaStatus",
    "SchemaValidationError",
    "SchemaValidator",
    "SchemaVersion",
    "SchemaDefinitionRow",
    "SchemaPersistenceBase",
    "SqlAlchemySchemaRegistry",
]
