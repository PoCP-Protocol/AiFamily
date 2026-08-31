"""Platform persistence primitives: session factory + Unit of Work.

See governance/MIGRATION_MANIFEST.yaml capability `platform_persistence_uow`
and `packages_contracts_provenance`. This package is infrastructure, not
domain code — SQLAlchemy is allowed here per REPOSITORY_CONSTITUTION.md's
Wave 1 instructions (domain layers must not depend on SQLAlchemy directly;
platform/persistence *is* the persistence infrastructure itself).
"""

from __future__ import annotations

from backend.platform.persistence.atomic_mutation import (
    AtomicMutationResult,
    execute_atomic_mutation,
)
from backend.platform.persistence.session import get_engine, get_sessionmaker
from backend.platform.persistence.unit_of_work import SqlAlchemyUnitOfWork, UnitOfWork

__all__ = [
    "AtomicMutationResult",
    "SqlAlchemyUnitOfWork",
    "UnitOfWork",
    "execute_atomic_mutation",
    "get_engine",
    "get_sessionmaker",
]
