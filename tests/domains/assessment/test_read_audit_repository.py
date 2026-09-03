"""Durable read-audit contract for the Assessment repository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.domains.assessment.infrastructure.sqlalchemy_repository import (
    SqlAlchemyAssessmentRepository,
)
from backend.platform.audit import AuditBase, read_events_for_subject


async def test_assessment_read_audit_joins_the_caller_connection_transaction():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(AuditBase.metadata.create_all)

        async with engine.connect() as connection:
            transaction = await connection.begin()
            repository = SqlAlchemyAssessmentRepository(connection)
            await repository.record_read_access(
                tenant_id="tenant-1",
                family_id="family-1",
                actor_id="guardian-1",
                action="assessment.ui03.read",
                resource_type="ASSESSMENT_PROJECTION",
                resource_id="UI-03:family-1",
                subject_person_id="child-1",
                accessed_fields=("assessment_response_set", "growth_hypothesis_evidence"),
                access_purpose="ASSESSMENT",
                reason="family growth hypothesis projection",
                correlation_id="corr-1",
                approval_ref="consent:ASSESSMENT:child-1",
            )
            await transaction.commit()

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            events = await read_events_for_subject(session, "child-1")

        assert len(events) == 1
        assert events[0].action == "assessment.ui03.read"
        assert events[0].tenant_id == "tenant-1"
        assert events[0].accessed_fields == (
            "assessment_response_set",
            "growth_hypothesis_evidence",
        )
    finally:
        await engine.dispose()
