"""Single-session repositories for ProductDefinition human adoption."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.platform.audit import AuditEvent, AuditRecorder

from ..domain.entities import ProductConcept, ProductDefinition
from ..domain.errors import ProductIntelligenceNotFoundError
from ..domain.zone_entities import ProductZoneAssessment
from . import sqlalchemy_models as product_models
from .fake_repository import FakeProductIntelligenceRepository
from .sqlalchemy_repository import SqlAlchemyProductIntelligenceRepository
from .zone_fake_repository import FakeZoneAssessmentRepository
from .zone_sqlalchemy_repository import SqlAlchemyZoneAssessmentRepository


class SqlAlchemyProductDefinitionAdoptionRepository:
    """Join concept, governed zone and definition persistence in one session."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._products = SqlAlchemyProductIntelligenceRepository(session)
        self._zones = SqlAlchemyZoneAssessmentRepository(session)

    async def load_product_concept(self, entity_id: str, tenant_scope: str) -> ProductConcept:
        return await self._products.load_product_concept(entity_id, tenant_scope)

    async def load_zone_assessment(
        self, entity_id: str, tenant_scope: str
    ) -> ProductZoneAssessment:
        return await self._zones.load_zone_assessment(entity_id, tenant_scope)

    async def load_product_definition(self, entity_id: str, tenant_scope: str) -> ProductDefinition:
        row = await self._session.get(product_models.ProductDefinitionRow, entity_id)
        if row is None or row.tenant_scope != tenant_scope:
            raise ProductIntelligenceNotFoundError("product_definition_not_found")
        return ProductDefinition(
            **{column.name: getattr(row, column.name) for column in row.__table__.columns}
        )

    async def create_product_definition_if_absent(
        self, entity: ProductDefinition
    ) -> tuple[ProductDefinition, bool]:
        try:
            existing = await self.load_product_definition(entity.id, entity.tenant_scope)
        except ProductIntelligenceNotFoundError:
            existing = None
        if existing is not None:
            return existing, False

        self._session.add(product_models.ProductDefinitionRow(**entity.model_dump()))
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            return await self.load_product_definition(entity.id, entity.tenant_scope), False
        return entity, True

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        return await recorder.flush(self._session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


@dataclass
class FakeProductDefinitionAdoptionRepository:
    """In-memory collaboration of the two canonical product repositories."""

    products: FakeProductIntelligenceRepository = field(
        default_factory=FakeProductIntelligenceRepository
    )
    zones: FakeZoneAssessmentRepository = field(default_factory=FakeZoneAssessmentRepository)
    audit_events: list[AuditEvent] = field(default_factory=list)
    commits: int = 0
    rollbacks: int = 0
    _uncommitted_definition_ids: set[str] = field(default_factory=set)
    _uncommitted_audit_count: int = 0

    async def load_product_concept(self, entity_id: str, tenant_scope: str) -> ProductConcept:
        return await self.products.load_product_concept(entity_id, tenant_scope)

    async def load_zone_assessment(
        self, entity_id: str, tenant_scope: str
    ) -> ProductZoneAssessment:
        return await self.zones.load_zone_assessment(entity_id, tenant_scope)

    async def load_product_definition(self, entity_id: str, tenant_scope: str) -> ProductDefinition:
        entity = self.products._product_definitions.get(entity_id)
        if entity is None or entity.tenant_scope != tenant_scope:
            raise ProductIntelligenceNotFoundError("product_definition_not_found")
        return entity

    async def create_product_definition_if_absent(
        self, entity: ProductDefinition
    ) -> tuple[ProductDefinition, bool]:
        existing = self.products._product_definitions.get(entity.id)
        if existing is not None:
            return existing, False
        self.products._product_definitions[entity.id] = entity
        self._uncommitted_definition_ids.add(entity.id)
        return entity, True

    async def flush_audit(self, recorder: AuditRecorder) -> int:
        pending = recorder.all_events()
        self.audit_events.extend(pending)
        self._uncommitted_audit_count += len(pending)
        return len(pending)

    async def commit(self) -> None:
        self.commits += 1
        self._uncommitted_definition_ids.clear()
        self._uncommitted_audit_count = 0

    async def rollback(self) -> None:
        for entity_id in self._uncommitted_definition_ids:
            self.products._product_definitions.pop(entity_id, None)
        if self._uncommitted_audit_count:
            del self.audit_events[-self._uncommitted_audit_count :]
        self._uncommitted_definition_ids.clear()
        self._uncommitted_audit_count = 0
        self.rollbacks += 1


__all__ = [
    "FakeProductDefinitionAdoptionRepository",
    "SqlAlchemyProductDefinitionAdoptionRepository",
]
