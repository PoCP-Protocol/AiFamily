"""Real SQLAlchemy repository implementing
`application/zone_ports.py::ZoneAssessmentRepositoryPort`. Same style as
`sqlalchemy_repository.py`: tenant-scoped load (raises
`ProductIntelligenceNotFoundError` for both "wrong id" and "right id, wrong
tenant" — never distinguishable, per PR-001R item 3), `save_*` only
`merge()`s+`flush()`es (never commits — see `unit_of_work.py`).

`dimension_assessments` serialization: `DimensionAssessment.assessed_at` is
a `datetime`. `ProductZoneAssessment.model_dump()` (Python mode) would keep
those as live `datetime` objects nested inside a `list[dict]`, which is not
JSON-serializable by the plain `json` module SQLAlchemy's generic `JSON`
type uses under the hood for SQLite — inserting that would fail with
`TypeError: Object of type datetime is not JSON serializable` the moment a
real (non-empty) score is saved. `model_dump(mode="json")` on each
`DimensionAssessment` converts `datetime`/etc. to JSON-safe primitives
(ISO-8601 strings) up front, and `DimensionAssessment(**d)` on load parses
the ISO string back into a `datetime` via pydantic's own coercion — so the
round trip is exact without this module hand-rolling a datetime codec.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.errors import ProductIntelligenceNotFoundError, ProductIntelligenceValidationError
from ..domain.zone_entities import DimensionAssessment, ProductZoneAssessment, ZonePolicyVersion
from . import zone_sqlalchemy_models as m


def _dump_zone_assessment(entity: ProductZoneAssessment) -> dict:
    payload = entity.model_dump(exclude={"dimension_assessments"})
    payload["dimension_assessments"] = [d.model_dump(mode="json") for d in entity.dimension_assessments]
    return payload


def _load_zone_assessment(row: object) -> ProductZoneAssessment:
    data = _row_to_dict(row)
    data["dimension_assessments"] = [DimensionAssessment(**d) for d in data["dimension_assessments"]]
    return ProductZoneAssessment(**data)


def _dump_zone_policy_version(entity: ZonePolicyVersion) -> dict:
    # `ZonePolicyVersion` itself has no `datetime`-nested-in-list field
    # (only `effective_from`, a top-level datetime column, which the
    # ORM's `DateTime(timezone=True)` column type accepts directly) — a
    # plain `model_dump()` is sufficient here, unlike `dimension_assessments`
    # above. `id` is required by the ORM row's primary key but is not a
    # field on `ZonePolicyVersion` itself; callers key it by `policy_id`.
    payload = entity.model_dump()
    payload["id"] = f"{entity.policy_id}:{entity.version}"
    return payload


def _load_zone_policy_version(row: object) -> ZonePolicyVersion:
    data = _row_to_dict(row)
    data.pop("id", None)
    return ZonePolicyVersion(**data)


class SqlAlchemyZoneAssessmentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save_zone_assessment(self, entity: ProductZoneAssessment) -> None:
        await self._merge(m.ProductZoneAssessmentRow(**_dump_zone_assessment(entity)))

    async def load_zone_assessment(self, entity_id: str, tenant_scope: str) -> ProductZoneAssessment:
        row = await self._session.get(m.ProductZoneAssessmentRow, entity_id)
        if row is None or row.tenant_scope != tenant_scope:
            raise ProductIntelligenceNotFoundError("zone_assessment_not_found")
        return _load_zone_assessment(row)

    async def load_active_zone_policy_version(self, tenant_scope: str | None = None) -> ZonePolicyVersion:
        # NOT tenant-scoped in V0 — see `application/zone_ports.py` module
        # docstring "Tenancy judgment call". `tenant_scope` is accepted for
        # call-site symmetry only and must not be used to filter here.
        #
        # Closure fix (chief-architect review): previously took `.first()`
        # over ALL rows with `status == "ACTIVE"` regardless of `policy_id`,
        # silently picking an arbitrary one if more than one ever existed.
        # V0 ships exactly one policy lineage in practice, but "fail closed
        # on a data inconsistency" beats "silently return a random row" —
        # this now groups by `policy_id` and fails loudly if any single
        # `policy_id` has more than one ACTIVE row, rather than only
        # detecting cross-policy_id duplicates. The real backstop against
        # this ever happening at all is the partial unique index added by
        # `0060_product_zone_engine_canonical_cleanup.sql`
        # (`uq_zone_policy_active_per_id`, `WHERE status = 'ACTIVE'`); this
        # check exists for defense in depth (e.g. a backend not yet migrated
        # to that index, or a direct DB write that bypassed it).
        result = await self._session.execute(
            select(m.ZonePolicyVersionRow).where(m.ZonePolicyVersionRow.status == "ACTIVE")
        )
        rows = list(result.scalars().all())
        if not rows:
            raise ProductIntelligenceNotFoundError("zone_policy_version_not_found")

        by_policy_id: dict[str, list[object]] = {}
        for row in rows:
            by_policy_id.setdefault(row.policy_id, []).append(row)
        for policy_id, policy_rows in by_policy_id.items():
            if len(policy_rows) > 1:
                raise ProductIntelligenceValidationError("multiple_active_policy_versions_for_policy_id")

        return _load_zone_policy_version(rows[0])

    async def save_zone_policy_version(self, entity: ZonePolicyVersion) -> None:
        await self._merge(m.ZonePolicyVersionRow(**_dump_zone_policy_version(entity)))

    async def _merge(self, row: object) -> None:
        await self._session.merge(row)
        await self._session.flush()


def _row_to_dict(row: object) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
