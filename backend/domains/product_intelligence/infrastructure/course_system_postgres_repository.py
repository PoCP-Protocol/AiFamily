"""PostgreSQL adapter for the versioned CourseSystem read model."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.course_system import CourseSystem
from ..domain.errors import ProductIntelligenceNotFoundError


class SqlAlchemyCourseSystemRepository:
    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def load_course_system(self, system_id: str, tenant_scope: str) -> CourseSystem:
        result = await self._connection.execute(
            text(
                """
                select * from course_system
                where tenant_scope=:tenant_scope and system_id=:system_id
                """
            ),
            {"tenant_scope": tenant_scope, "system_id": system_id},
        )
        row = result.mappings().first()
        if row is None:
            raise ProductIntelligenceNotFoundError("course_system_not_found")
        return CourseSystem(
            system_id=row["system_id"],
            tenant_scope=row["tenant_scope"],
            version=row["version"],
            product_package_version_ref=row["product_package_version_ref"],
            stages=tuple(row["stages"] or ()),
            bom=tuple(row["bom"] or ()),
        )

    async def save_course_system(self, system: CourseSystem) -> None:
        await self._connection.execute(
            text(
                """
                insert into course_system(
                  system_id, tenant_scope, version, product_package_version_ref, stages, bom
                ) values (
                  :system_id, :tenant_scope, :version, :product_package_version_ref, :stages, :bom
                )
                on conflict (tenant_scope, system_id) do update set
                  version=excluded.version,
                  product_package_version_ref=excluded.product_package_version_ref,
                  stages=excluded.stages,
                  bom=excluded.bom
                where course_system.version <= excluded.version
                """
            ),
            {
                "system_id": system.system_id,
                "tenant_scope": system.tenant_scope,
                "version": system.version,
                "product_package_version_ref": system.product_package_version_ref,
                "stages": json.dumps([stage.model_dump() for stage in system.stages]),
                "bom": json.dumps([line.model_dump() for line in system.bom]),
            },
        )


__all__ = ["SqlAlchemyCourseSystemRepository"]
