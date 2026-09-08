"""PostgreSQL adapter for immutable course ReleaseBaseline manifests."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.intelligence.product_management.ipd_contracts import ArtifactStatus, ReleaseBaseline


def _json(value: object) -> str:
    return json.dumps(list(value) if isinstance(value, tuple) else value, sort_keys=True)


def _from_row(row) -> ReleaseBaseline:  # noqa: ANN001
    return ReleaseBaseline(
        release_id=row["release_id"],
        package_id=row["package_id"],
        package_version=row["package_version"],
        component_refs=tuple(row["component_refs"] or ()),
        skill_refs=tuple(row["skill_refs"] or ()),
        blueprint_version_id=row["blueprint_version_id"],
        model_refs=tuple(row["model_refs"] or ()),
        prompt_refs=tuple(row["prompt_refs"] or ()),
        schema_refs=tuple(row["schema_refs"] or ()),
        knowledge_refs=tuple(row["knowledge_refs"] or ()),
        migration_refs=tuple(row["migration_refs"] or ()),
        runbook_ref=row["runbook_ref"],
        rollback_ref=row["rollback_ref"],
        environment=row["environment"],
        evidence_refs=tuple(row["evidence_refs"] or ()),
        status=ArtifactStatus(row["status"]),
        generated_by=row["generated_by"],
        approved_by=row["approved_by"],
        human_gate_ref=row["human_gate_ref"],
        rollback_target_ref=row["rollback_target_ref"],
    )


class SqlAlchemyCourseReleaseBaselineRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def save(self, tenant_scope: str, baseline: ReleaseBaseline) -> None:
        values = {
            "tenant_scope": tenant_scope,
            "release_id": baseline.release_id,
            "package_id": baseline.package_id,
            "package_version": baseline.package_version,
            "status": baseline.status.value,
            "component_refs": _json(baseline.component_refs),
            "skill_refs": _json(baseline.skill_refs),
            "blueprint_version_id": baseline.blueprint_version_id,
            "model_refs": _json(baseline.model_refs),
            "prompt_refs": _json(baseline.prompt_refs),
            "schema_refs": _json(baseline.schema_refs),
            "knowledge_refs": _json(baseline.knowledge_refs),
            "migration_refs": _json(baseline.migration_refs),
            "evidence_refs": _json(baseline.evidence_refs),
            "runbook_ref": baseline.runbook_ref,
            "rollback_ref": baseline.rollback_ref,
            "rollback_target_ref": baseline.rollback_target_ref,
            "environment": baseline.environment,
            "generated_by": baseline.generated_by,
            "approved_by": baseline.approved_by,
            "human_gate_ref": baseline.human_gate_ref,
        }
        await self._connection.execute(
            text("""
            insert into course_release_baseline
              (release_id, tenant_scope, package_id, package_version, status, component_refs, skill_refs,  # noqa: E501
               blueprint_version_id, model_refs, prompt_refs, schema_refs, knowledge_refs, migration_refs,  # noqa: E501
               evidence_refs, runbook_ref, rollback_ref, rollback_target_ref, environment, generated_by,  # noqa: E501
               approved_by, human_gate_ref)
            values (:release_id, :tenant_scope, :package_id, :package_version, :status, :component_refs, :skill_refs,  # noqa: E501
                    :blueprint_version_id, :model_refs, :prompt_refs, :schema_refs, :knowledge_refs, :migration_refs,  # noqa: E501
                    :evidence_refs, :runbook_ref, :rollback_ref, :rollback_target_ref, :environment, :generated_by,  # noqa: E501
                    :approved_by, :human_gate_ref)
            on conflict (tenant_scope, release_id) do update set status=excluded.status,
              rollback_target_ref=excluded.rollback_target_ref, approved_by=excluded.approved_by,
              human_gate_ref=excluded.human_gate_ref, evidence_refs=excluded.evidence_refs
        """),
            values,
        )

    async def get(self, tenant_scope: str, release_id: str) -> ReleaseBaseline | None:
        result = await self._connection.execute(
            text(
                "select * from course_release_baseline where tenant_scope=:tenant_scope and release_id=:release_id"  # noqa: E501
            ),
            {"tenant_scope": tenant_scope, "release_id": release_id},
        )
        row = result.mappings().first()
        return _from_row(row) if row else None


class ConnectionScopedCourseReleaseBaselineRepository:
    def __init__(self, engine) -> None:  # noqa: ANN001
        self._engine = engine

    async def save(self, tenant_scope: str, baseline: ReleaseBaseline) -> None:
        async with self._engine.begin() as connection:
            await SqlAlchemyCourseReleaseBaselineRepository(connection).save(tenant_scope, baseline)

    async def get(self, tenant_scope: str, release_id: str) -> ReleaseBaseline | None:
        async with self._engine.begin() as connection:
            return await SqlAlchemyCourseReleaseBaselineRepository(connection).get(
                tenant_scope, release_id
            )


__all__ = [
    "ConnectionScopedCourseReleaseBaselineRepository",
    "SqlAlchemyCourseReleaseBaselineRepository",
]
